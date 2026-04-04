"""AudioStage: Audio prepare, narration, per-slide audio (per-variant)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import PipelineContext, StageResult

try:
    from audio_config import AudioConfig
except ImportError:
    AudioConfig = None  # type: ignore

try:
    from audio_prepare import run_audio_prepare
except ImportError:
    run_audio_prepare = None  # type: ignore


class AudioStage:
    name = "audio"

    def run(self, ctx: "PipelineContext") -> "StageResult":
        from pipeline import StageResult

        try:
            from apps.api.models import Artifact
        except ImportError:
            from models import Artifact  # type: ignore

        if not run_audio_prepare or not AudioConfig:
            return StageResult(status="skipped", metrics={"reason": "audio deps missing"})

        minio_client = ctx.minio_client
        db = ctx.db_session
        job_id = ctx.job_id
        variant = ctx.variant or {}
        variant_id = variant.get("id", "en")
        voice_id = variant.get("voice_id", "default_en")
        target_lang = variant.get("lang", "en-US")
        script_prefix = ctx.script_prefix
        slide_count = ctx.slide_count
        unified_by_slide = ctx.unified_by_slide
        evidence_index = ctx.evidence_index

        # Build slides_notes_and_text
        slides_notes_and_text: List[Tuple[str, str]] = []
        for i in range(slide_count):
            slide_index = i + 1
            slide_num = f"{slide_index:03d}"
            ppt_path = f"jobs/{job_id}/ppt/slide_{slide_num}.json"
            notes, slide_text = "", ""
            try:
                ppt_data = minio_client.get(ppt_path)
                ppt_payload = json.loads(ppt_data.decode("utf-8"))
                notes = (ppt_payload.get("notes") or "").strip()
                slide_text = (ppt_payload.get("slide_text") or "").strip()
            except Exception:
                pass
            slides_notes_and_text.append((notes, slide_text))
        ctx.slides_notes_and_text = slides_notes_and_text

        # Log narration override status
        override = ctx.narration_entries_override
        if override:
            sources = [e.get("source_used", "?") for e in override[:3]]
            print(f"  [AudioStage] narration_entries_override: {len(override)} entries, sources={sources}...")
        else:
            print(f"  [AudioStage] narration_entries_override: None (using template)")

        try:
            config = AudioConfig.from_env()
            narration_entries, per_slide_audio, narration_payload = run_audio_prepare(
                job_id=job_id,
                slide_count=slide_count,
                minio_client=minio_client,
                temp_dir=ctx.temp_dir,
                config=config,
                slides_notes_and_text=slides_notes_and_text,
                unified_graphs_by_slide=unified_by_slide,
                tts_provider=None,
                evidence_index=evidence_index,
                llm_provider=ctx.llm_provider,
                variant_id=variant_id,
                voice_id=voice_id,
                lang=target_lang,
                narration_entries_override=ctx.narration_entries_override,
            )
            ctx.narration_entries = narration_entries
            ctx.per_slide_audio_paths = [p for p, _ in per_slide_audio]
            ctx.per_slide_durations_dict = {i + 1: dur for i, (_, dur) in enumerate(per_slide_audio)}

            db.add(Artifact(
                artifact_id=str(uuid.uuid4()),
                project_id=ctx.project_id,
                job_id=job_id,
                artifact_type="narration_per_slide",
                storage_path=f"{script_prefix}narration_per_slide.json",
                metadata_json=json.dumps({"type": "narration_per_slide", "stage": "audio_prepare", "variant_id": variant_id}),
                created_at=datetime.utcnow(),
            ))
            if minio_client.exists(f"{script_prefix}narration_blueprint.json"):
                db.add(Artifact(
                    artifact_id=str(uuid.uuid4()),
                    project_id=ctx.project_id,
                    job_id=job_id,
                    artifact_type="narration_blueprint",
                    storage_path=f"{script_prefix}narration_blueprint.json",
                    metadata_json=json.dumps({"type": "narration_blueprint", "stage": "audio_prepare"}),
                    created_at=datetime.utcnow(),
                ))
            print(f"  Audio prepare: jobs/{job_id}/audio/slide_*.wav, narration_per_slide.json, timing/slide_*_duration.json written")
        except Exception as e:
            import traceback
            print(f"  Warning: audio_prepare failed: {e}\n{traceback.format_exc()}")

        return StageResult(status="ok")
