"""TranslateStage: Translation of script and notes for l2 variants (per-variant)."""
from __future__ import annotations

import json
from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import PipelineContext, StageResult

try:
    from translator_provider import get_translator_provider
    from translation import (
        translate_script_segments,
        translate_notes_per_slide,
        verify_translated_script,
        derive_narration_from_script,
        build_translation_report,
    )
except ImportError:
    get_translator_provider = None  # type: ignore
    translate_script_segments = None  # type: ignore
    translate_notes_per_slide = None  # type: ignore
    verify_translated_script = None  # type: ignore
    derive_narration_from_script = None  # type: ignore
    build_translation_report = None  # type: ignore


class TranslateStage:
    name = "translate"

    def run(self, ctx: "PipelineContext") -> "StageResult":
        from pipeline import StageResult

        variant = ctx.variant or {}
        variant_id = variant.get("id", "en")
        target_lang = variant.get("lang", "en-US")
        notes_translate = variant.get("notes_translate", False)

        # Only runs for l2 variant with non-English target
        if variant_id != "l2" or (not notes_translate and target_lang == "en-US"):
            return StageResult(status="skipped", metrics={"reason": "not l2 or english"})

        if not (
            get_translator_provider
            and translate_script_segments
            and translate_notes_per_slide
            and verify_translated_script
            and derive_narration_from_script
            and build_translation_report
        ):
            ctx.translation_degraded = True
            return StageResult(status="skipped", metrics={"reason": "translation deps missing"})

        minio_client = ctx.minio_client
        job_id = ctx.job_id
        slide_count = ctx.slide_count
        script_prefix = ctx.script_prefix
        evidence_index = ctx.evidence_index
        unified_by_slide = ctx.unified_by_slide
        verified_script = ctx.verified_script

        # Build slides_notes_and_text (needed for translation)
        slides_notes_and_text: List[Tuple[str, str]] = []
        for i in range(slide_count):
            slide_num = f"{(i + 1):03d}"
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

        translator = get_translator_provider()
        translated_script, script_report, script_ok = translate_script_segments(
            verified_script, translator, "en-US", target_lang
        )
        script_verified_ok, _ = verify_translated_script(
            translated_script, evidence_index, unified_by_slide
        )
        if script_ok and script_verified_ok:
            ctx.script_for_downstream = translated_script
            minio_client.put(
                f"{script_prefix}script_translated.json",
                json.dumps(translated_script, indent=2).encode("utf-8"),
                "application/json",
            )
            ctx.narration_entries_override = derive_narration_from_script(
                translated_script, slide_count
            )
        else:
            ctx.translation_degraded = True

        notes_translated_list, notes_report = translate_notes_per_slide(
            slides_notes_and_text, translator, "en-US", target_lang
        )
        if notes_translate:
            ctx.per_slide_notes_for_overlay = notes_translated_list
            notes_clean = [
                {"slide_index": i + 1, "notes": n, "notes_clean": n}
                for i, (n, _) in enumerate(slides_notes_and_text)
            ]
            notes_tr = [
                {"slide_index": i + 1, "notes_translated": t}
                for i, t in enumerate(notes_translated_list)
            ]
            notes_prefix = f"jobs/{job_id}/notes/{variant_id}/"
            minio_client.put(
                f"{notes_prefix}notes_clean.json",
                json.dumps({"slides": notes_clean}, indent=2).encode("utf-8"),
                "application/json",
            )
            minio_client.put(
                f"{notes_prefix}notes_translated.json",
                json.dumps({"slides": notes_tr}, indent=2).encode("utf-8"),
                "application/json",
            )

        trans_report = build_translation_report(
            job_id,
            variant_id,
            target_lang,
            script_report,
            notes_report if notes_translate else [],
            script_verified_ok,
            ctx.translation_degraded,
        )
        minio_client.put(
            f"{script_prefix}translation_report.json",
            json.dumps(trans_report, indent=2).encode("utf-8"),
            "application/json",
        )
        print("  Translation: script_translated.json, notes, translation_report.json written")

        return StageResult(status="ok")
