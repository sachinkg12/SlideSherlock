"""VideoStage: Alignment, timeline, overlay rendering, compose final video (per-variant)."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import PipelineContext, StageResult

try:
    from alignment import build_alignment
except ImportError:
    build_alignment = None  # type: ignore

try:
    from timeline_builder import build_timeline
except ImportError:
    build_timeline = None  # type: ignore

try:
    from overlay_renderer import render_slide_with_overlay_mp4
except ImportError:
    render_slide_with_overlay_mp4 = None  # type: ignore

import subprocess as _subprocess

try:
    from composer import compose_video, concat_audio
except ImportError:
    compose_video = None  # type: ignore
    concat_audio = None  # type: ignore


def _get_mp4_duration(path: str) -> float:
    """Get exact duration of an MP4 via ffprobe."""
    try:
        r = _subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return float(r.stdout.strip()) if r.stdout.strip() else 0.0
    except Exception:
        return 0.0


def _pad_audio_to_duration(
    audio_path: str, target_dur: float, temp_dir: str, slide_index: int
) -> str:
    """Pad a WAV file with silence to exactly match target_dur. Returns path to padded file."""
    padded = os.path.join(temp_dir, f"slide_{slide_index:03d}_padded.wav")
    try:
        _subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                audio_path,
                "-af",
                f"apad=whole_dur={target_dur}",
                "-ar",
                "48000",
                "-ac",
                "1",
                padded,
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return padded
    except Exception:
        return audio_path


try:
    from notes_config import OnScreenNotesConfig, resolve_notes_font_for_variant
except ImportError:
    OnScreenNotesConfig = None  # type: ignore
    resolve_notes_font_for_variant = None  # type: ignore

try:
    from video_config import VideoConfig
except ImportError:
    VideoConfig = None  # type: ignore

try:
    from subtitle_generator import generate_srt_from_narration_and_alignment
except ImportError:
    generate_srt_from_narration_and_alignment = None  # type: ignore

try:
    from doctor import run_doctor
except ImportError:
    run_doctor = None  # type: ignore

try:
    from presets import get_current_preset
except ImportError:
    get_current_preset = None  # type: ignore


class VideoStage:
    name = "video"

    def run(self, ctx: "PipelineContext") -> "StageResult":
        from pipeline import StageResult

        try:
            from apps.api.models import Artifact
        except ImportError:
            from models import Artifact  # type: ignore

        if not (
            build_alignment and build_timeline and render_slide_with_overlay_mp4 and compose_video
        ):
            return StageResult(status="skipped", metrics={"reason": "video deps missing"})

        minio_client = ctx.minio_client
        db = ctx.db_session
        job_id = ctx.job_id
        variant = ctx.variant or {}
        variant_id = variant.get("id", "en")
        target_lang = variant.get("lang", "en-US")
        script_prefix = ctx.script_prefix
        timeline_prefix = ctx.timeline_prefix
        timeline_path_prefix = ctx.timeline_path_prefix
        overlay_prefix = ctx.overlay_prefix
        output_prefix = ctx.output_prefix
        slide_count = ctx.slide_count
        slide_metadata = ctx.slide_metadata
        unified_by_slide = ctx.unified_by_slide
        evidence_index = ctx.evidence_index
        script_for_downstream = ctx.script_for_downstream
        per_slide_durations_dict = ctx.per_slide_durations_dict
        per_slide_audio_paths = ctx.per_slide_audio_paths
        narration_entries = ctx.narration_entries
        per_slide_notes_for_overlay = ctx.per_slide_notes_for_overlay
        temp_dir = ctx.temp_dir
        coverage = ctx.coverage
        artifacts_written = []

        pipeline_start = time.time()
        try:
            alignment_payload = build_alignment(
                job_id,
                script_for_downstream,
                segment_timestamps=None,
                per_slide_durations=per_slide_durations_dict if per_slide_durations_dict else None,
            )
            slide_dimensions = {
                (i + 1): (slide_metadata[i]["width"], slide_metadata[i]["height"])
                for i in range(min(len(slide_metadata), slide_count))
            }
            # Image HIGHLIGHT/ZOOM actions
            images_index_for_timeline = None
            try:
                img_idx_data = minio_client.get(f"jobs/{job_id}/images/index.json")
                images_index_for_timeline = json.loads(img_idx_data.decode("utf-8"))
            except Exception:
                pass
            timeline_payload = build_timeline(
                job_id,
                script_for_downstream,
                alignment_payload,
                unified_by_slide,
                slide_dimensions,
                images_index=images_index_for_timeline,
                evidence_index=evidence_index,
            )
            timing_path = f"{timeline_prefix}alignment.json"
            timeline_path = f"{timeline_path_prefix}timeline.json"
            minio_client.put(
                timing_path,
                json.dumps(alignment_payload, indent=2).encode("utf-8"),
                "application/json",
            )
            minio_client.put(
                timeline_path,
                json.dumps(timeline_payload, indent=2).encode("utf-8"),
                "application/json",
            )
            artifacts_written.extend([timing_path, timeline_path])

            for path, payload, art_type in [
                (timing_path, alignment_payload, "alignment"),
                (timeline_path, timeline_payload, "timeline"),
            ]:
                raw = json.dumps(payload, indent=2).encode("utf-8")
                db.add(
                    Artifact(
                        artifact_id=str(uuid.uuid4()),
                        project_id=ctx.project_id,
                        job_id=job_id,
                        artifact_type=art_type,
                        storage_path=path,
                        sha256=hashlib.sha256(raw).hexdigest(),
                        size_bytes=str(len(raw)),
                        metadata_json=json.dumps({"type": art_type, "stage": "timeline"}),
                        created_at=datetime.utcnow(),
                    )
                )
            print(f"  Alignment + timeline written to jobs/{job_id}/timing/ and timeline/")

            actions_by_slide: Dict[int, List[Any]] = {}
            for a in timeline_payload.get("actions", []):
                si = a.get("slide_index", 0)
                actions_by_slide.setdefault(si, []).append(a)

            # Per-slide notes for on-screen display
            per_slide_notes: List[str] = []
            if per_slide_notes_for_overlay and len(per_slide_notes_for_overlay) >= slide_count:
                per_slide_notes = list(per_slide_notes_for_overlay[:slide_count])
            elif len(narration_entries) >= slide_count:
                per_slide_notes = [
                    narration_entries[i].get("narration_text", "") for i in range(slide_count)
                ]
            else:
                try:
                    nar_path = f"{script_prefix}narration_per_slide.json"
                    nar_data = minio_client.get(nar_path)
                    nar_payload = json.loads(nar_data.decode("utf-8"))
                    slides_list = nar_payload.get("slides", [])
                    per_slide_notes = [
                        s.get("narration_text", "") for s in slides_list[:slide_count]
                    ]
                except Exception:
                    per_slide_notes = [""] * slide_count
            while len(per_slide_notes) < slide_count:
                per_slide_notes.append("")

            notes_config = OnScreenNotesConfig.from_env() if OnScreenNotesConfig else None
            notes_font_path = (
                resolve_notes_font_for_variant(variant_id, target_lang)
                if resolve_notes_font_for_variant
                else os.environ.get("ON_SCREEN_NOTES_FONT_PATH")
            ) or None

            overlay_mp4_paths = []
            total_duration = 0.0
            slide_start = 0.0
            for slide_index in range(1, slide_count + 1):
                actions_slide = actions_by_slide.get(slide_index, [])
                audio_dur = per_slide_durations_dict.get(slide_index, 2.0)
                if actions_slide:
                    t_starts = [a.get("t_start", 0) for a in actions_slide]
                    t_ends = [a.get("t_end", 0) for a in actions_slide]
                    timeline_dur = max(t_ends) - min(t_starts) if t_starts and t_ends else 0.0
                    slide_dur = max(timeline_dur, audio_dur)
                    actions_slide = [
                        {
                            **a,
                            "t_start": a.get("t_start", 0) - slide_start,
                            "t_end": a.get("t_end", 0) - slide_start,
                        }
                        for a in actions_slide
                    ]
                else:
                    slide_dur = audio_dur
                total_duration += slide_dur
                slide_start += slide_dur
                slide_num = f"{slide_index:03d}"
                png_storage = f"jobs/{job_id}/render/slides/slide_{slide_num}.png"
                try:
                    png_data = minio_client.get(png_storage)
                except Exception as e:
                    print(f"  Warning: could not load {png_storage}: {e}")
                    continue
                out_mp4 = os.path.join(temp_dir, f"slide_{slide_num}_{variant_id}_overlay.mp4")
                notes_text = (
                    per_slide_notes[slide_index - 1] if slide_index <= len(per_slide_notes) else ""
                )
                render_slide_with_overlay_mp4(
                    png_data,
                    actions_slide,
                    slide_dur,
                    out_mp4,
                    notes_text=notes_text,
                    notes_config=notes_config,
                    notes_font_path=notes_font_path,
                )
                # Measure actual overlay duration (may differ from target due to FPS rounding)
                actual_overlay_dur = _get_mp4_duration(out_mp4)
                if (
                    actual_overlay_dur > 0
                    and per_slide_audio_paths
                    and slide_index <= len(per_slide_audio_paths)
                ):
                    audio_file = per_slide_audio_paths[slide_index - 1]
                    if audio_file and os.path.exists(audio_file):
                        padded = _pad_audio_to_duration(
                            audio_file, actual_overlay_dur, temp_dir, slide_index
                        )
                        per_slide_audio_paths[slide_index - 1] = padded

                overlay_storage = f"{overlay_prefix}slide_{slide_num}_overlay.mp4"
                with open(out_mp4, "rb") as f:
                    minio_client.put(overlay_storage, f.read(), "video/mp4")
                overlay_mp4_paths.append(out_mp4)
                artifacts_written.append(overlay_storage)
                db.add(
                    Artifact(
                        artifact_id=str(uuid.uuid4()),
                        project_id=ctx.project_id,
                        job_id=job_id,
                        artifact_type="overlay_mp4",
                        storage_path=overlay_storage,
                        metadata_json=json.dumps(
                            {
                                "type": "overlay",
                                "slide_index": slide_index,
                                "variant_id": variant_id,
                            }
                        ),
                        created_at=datetime.utcnow(),
                    )
                )
            print(f"  Overlays written to jobs/{job_id}/overlays/")

            deck_title = ""
            deck_subtitle = ""
            try:
                ppt1 = minio_client.get(f"jobs/{job_id}/ppt/slide_001.json")
                ppt1_data = json.loads(ppt1.decode("utf-8"))
                deck_title = (ppt1_data.get("slide_text") or ppt1_data.get("title") or "")[:200]
            except Exception:
                pass
            video_config = VideoConfig.from_env(deck_title, deck_subtitle) if VideoConfig else None
            per_slide_durs_list = [
                per_slide_durations_dict.get(i + 1, 2.0) for i in range(slide_count)
            ]
            srt_path: Optional[str] = None
            srt_local: Optional[str] = None
            if (
                video_config
                and getattr(video_config, "subtitles_enabled", False)
                and generate_srt_from_narration_and_alignment
            ):
                try:
                    fd, srt_local = tempfile.mkstemp(suffix=".srt")
                    os.close(fd)
                    offset = (
                        getattr(video_config, "intro_duration", 0.0)
                        if getattr(video_config, "intro_enabled", False)
                        else 0.0
                    )
                    nar_slides = narration_entries if narration_entries else []
                    if not nar_slides:
                        try:
                            nar_data = minio_client.get(f"{script_prefix}narration_per_slide.json")
                            nar_payload = json.loads(nar_data.decode("utf-8"))
                            nar_slides = nar_payload.get("slides", [])
                        except Exception:
                            pass
                    srt_content = generate_srt_from_narration_and_alignment(
                        nar_slides,
                        per_slide_durations_dict,
                        slide_count,
                        offset_seconds=offset,
                    )
                    with open(srt_local, "w", encoding="utf-8") as f:
                        f.write(srt_content)
                    srt_path = srt_local
                except Exception as e:
                    print(f"  Warning: SRT generation failed: {e}")
                    srt_path = None

            final_mp4_local = os.path.join(temp_dir, f"final_{variant_id}.mp4")
            compose_video(
                overlay_mp4_paths,
                total_duration,
                final_mp4_local,
                audio_path=None,
                per_slide_audio_paths=per_slide_audio_paths if per_slide_audio_paths else None,
                audio_sample_rate=48000,
                video_config=video_config,
                srt_path=srt_path,
                per_slide_durations=per_slide_durs_list,
                deck_title=deck_title,
                deck_subtitle=deck_subtitle,
            )
            final_storage = f"{output_prefix}final.mp4"
            with open(final_mp4_local, "rb") as f:
                final_data = f.read()
            minio_client.put(final_storage, final_data, "video/mp4")
            artifacts_written.append(final_storage)
            db.add(
                Artifact(
                    artifact_id=str(uuid.uuid4()),
                    project_id=ctx.project_id,
                    job_id=job_id,
                    artifact_type="final_video",
                    storage_path=final_storage,
                    sha256=hashlib.sha256(final_data).hexdigest(),
                    size_bytes=str(len(final_data)),
                    metadata_json=json.dumps({"type": "final_mp4", "stage": "compose"}),
                    created_at=datetime.utcnow(),
                )
            )
            print("  Composed output/final.mp4 written")

            if (
                srt_local
                and os.path.exists(srt_local)
                and video_config
                and getattr(video_config, "subtitles_enabled", False)
            ):
                try:
                    with open(srt_local, "r", encoding="utf-8") as f:
                        srt_data = f.read()
                    srt_storage = f"{output_prefix}final.srt"
                    minio_client.put(srt_storage, srt_data.encode("utf-8"), "text/plain")
                    db.add(
                        Artifact(
                            artifact_id=str(uuid.uuid4()),
                            project_id=ctx.project_id,
                            job_id=job_id,
                            artifact_type="subtitles_srt",
                            storage_path=srt_storage,
                            metadata_json=json.dumps({"type": "srt", "stage": "compose"}),
                            created_at=datetime.utcnow(),
                        )
                    )
                    print("  Wrote output/final.srt")
                except Exception as e:
                    print(f"  Warning: failed to upload SRT: {e}")
                finally:
                    try:
                        os.unlink(srt_local)
                    except Exception:
                        pass

            pipeline_elapsed = time.time() - pipeline_start
            # Write per-variant metrics (legacy format)
            _metrics = {  # noqa: F841
                "schema_version": "1.0",
                "job_id": job_id,
                "runtime_seconds": round(pipeline_elapsed, 2),
                "errors": [],
                "confidence_summary": {
                    "pct_claims_with_evidence": coverage.get("pct_claims_with_evidence"),
                    "pct_entities_grounded": coverage.get("pct_entities_grounded"),
                    "pass": coverage.get("pass"),
                    "rewrite": coverage.get("rewrite"),
                    "remove": coverage.get("remove"),
                },
                "slide_count": slide_count,
                "total_duration_seconds": total_duration,
            }
            # Note: the pipeline-level metrics.json is written by run_pipeline();
            # this is the legacy per-variant metrics that was in the original monolith.

            summary = {
                "schema_version": "1.0",
                "job_id": job_id,
                "duration_seconds": round(total_duration, 2),
                "slide_count": slide_count,
                "pass_rate": (coverage.get("pct_claims_with_evidence") or 0)
                if coverage.get("total_claims")
                else None,
                "provider_usage": {"llm": "stub", "tts": "local"},
            }
            summary_path = f"jobs/{job_id}/output/summary.json"
            minio_client.put(
                summary_path, json.dumps(summary, indent=2).encode("utf-8"), "application/json"
            )
            db.add(
                Artifact(
                    artifact_id=str(uuid.uuid4()),
                    project_id=ctx.project_id,
                    job_id=job_id,
                    artifact_type="summary",
                    storage_path=summary_path,
                    metadata_json=json.dumps({"type": "summary", "stage": "pipeline"}),
                    created_at=datetime.utcnow(),
                )
            )
            print(f"  Summary written to jobs/{job_id}/output/summary.json")

            # Diagnostics
            preset_used = get_current_preset() if get_current_preset else None
            diagnostics = {
                "schema_version": "1.0",
                "job_id": job_id,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "preset": preset_used,
            }
            if run_doctor:
                doctor_report = run_doctor()
                diagnostics["doctor"] = doctor_report
            diagnostics_path = f"jobs/{job_id}/output/diagnostics.json"
            minio_client.put(
                diagnostics_path,
                json.dumps(diagnostics, indent=2).encode("utf-8"),
                "application/json",
            )
            db.add(
                Artifact(
                    artifact_id=str(uuid.uuid4()),
                    project_id=ctx.project_id,
                    job_id=job_id,
                    artifact_type="diagnostics",
                    storage_path=diagnostics_path,
                    metadata_json=json.dumps({"type": "diagnostics", "stage": "pipeline"}),
                    created_at=datetime.utcnow(),
                )
            )
            print(f"  Diagnostics written to jobs/{job_id}/output/diagnostics.json")

        except Exception as e:
            import traceback

            print(f"  Warning: timeline/overlay/compose failed: {e}\n{traceback.format_exc()}")
            return StageResult(
                status="failed", artifacts_written=artifacts_written, metrics={"error": str(e)}
            )

        return StageResult(
            status="ok",
            artifacts_written=artifacts_written,
            metrics={"total_duration": total_duration},
        )
