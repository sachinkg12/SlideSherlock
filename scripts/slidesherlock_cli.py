#!/usr/bin/env python3
"""
SlideSherlock CLI — run the full pipeline from the command line.

Usage:
    slidesherlock run deck.pptx                          # draft preset, output to ./output/
    slidesherlock run deck.pptx --preset pro             # pro preset (vision + BGM)
    slidesherlock run deck.pptx --preset standard -o out/ --lang hi-IN
    slidesherlock doctor                                  # check system dependencies
    slidesherlock preset [draft|standard|pro]             # show/apply preset
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

# Add repo root and packages/core to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, "packages", "core"))
sys.path.insert(0, os.path.join(repo_root, "apps", "api"))


# ---------------------------------------------------------------------------
# Structured logger — produces both human-readable output and a JSON run log
# that can be aggregated across multiple runs for paper tables/figures.
# ---------------------------------------------------------------------------


class PipelineLogger:
    """
    Structured logger for CLI pipeline runs.

    Emits human-readable lines to stdout and accumulates a machine-readable
    JSON log at ``output_dir/run_log.json``.  The JSON log is designed for
    downstream aggregation (e.g. ``pandas.json_normalize``) when running the
    pipeline on a corpus of PPTXs to generate paper tables.

    JSON schema (``run_log.json``):
    {
      "run_id":       str,         # UUID for this CLI invocation
      "started_at":   str,         # ISO-8601 UTC
      "finished_at":  str,
      "input_file":   str,         # basename of the PPTX
      "input_bytes":  int,
      "preset":       str,
      "slide_count":  int,
      "variant":      str,         # e.g. "en"
      "pipeline_duration_s": float,
      "stages": {                  # keyed by stage name
        "<name>": {
          "status":      str,      # ok | skipped | failed
          "duration_s":  float,
          "metrics":     dict      # stage-specific (slide_count, pass_count, …)
        }
      },
      "output_video":  str | null, # path to final.mp4 on disk
      "output_bytes":  int | null,
      "doctor":        dict        # system dependency snapshot
    }
    """

    def __init__(self, run_id: str, output_dir: str, input_file: str, preset: str):
        self.run_id = run_id
        self.output_dir = output_dir
        self.input_file = input_file
        self.preset = preset
        self.started_at = datetime.now(timezone.utc)
        self.stages: Dict[str, Dict[str, Any]] = {}
        self.data: Dict[str, Any] = {
            "run_id": run_id,
            "started_at": self.started_at.isoformat(),
            "input_file": os.path.basename(input_file),
            "input_bytes": os.path.getsize(input_file),
            "preset": preset,
            "slide_count": 0,
            "variant": None,
            "pipeline_duration_s": 0.0,
            "stages": {},
            "output_video": None,
            "output_bytes": None,
            "doctor": None,
        }
        self._stage_start: float = 0.0

    # -- human-readable output -----------------------------------------------

    def header(self):
        print()
        print("=" * 64)
        print("  SlideSherlock Pipeline")
        print(f"  Input:  {os.path.basename(self.input_file)}")
        print(f"  Preset: {self.preset}")
        print(f"  Run ID: {self.run_id[:12]}...")
        print("=" * 64)
        print()

    def stage_start(self, name: str):
        self._stage_start = time.time()
        print(f"  [{_ts()}] ▶ {name.upper()}")

    def stage_detail(self, msg: str):
        print(f"           {msg}")

    def stage_end(self, name: str, result):
        elapsed = time.time() - self._stage_start
        status = result.status
        icon = "✓" if status == "ok" else ("–" if status == "skipped" else "✗")
        print(f"  [{_ts()}] {icon} {name.upper()} — {status} ({elapsed:.1f}s)")

        # Print key metrics inline
        m = result.metrics or {}
        highlights = _metric_highlights(name, m)
        if highlights:
            print(f"           {highlights}")
        print()

        # Accumulate for JSON
        self.stages[name] = {
            "status": status,
            "duration_s": round(elapsed, 3),
            "metrics": m,
        }

    def set_slide_count(self, n: int):
        self.data["slide_count"] = n

    def set_variant(self, v: str):
        self.data["variant"] = v

    def set_doctor(self, report: dict):
        self.data["doctor"] = report

    def summary(self, output_video: str | None):
        elapsed = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        self.data["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.data["pipeline_duration_s"] = round(elapsed, 3)
        self.data["stages"] = self.stages
        self.data["output_video"] = output_video

        if output_video and os.path.exists(output_video):
            self.data["output_bytes"] = os.path.getsize(output_video)

        # Human-readable summary
        print("-" * 64)
        print(f"  Pipeline finished in {elapsed:.1f}s")
        if output_video:
            sz_mb = (self.data["output_bytes"] or 0) / (1024 * 1024)
            print(f"  Output:  {output_video} ({sz_mb:.1f} MB)")
        print()

        # Stage timing table
        print("  Stage Timings:")
        for sname, sdata in self.stages.items():
            bar = "█" * max(1, int(sdata["duration_s"] / elapsed * 40)) if elapsed > 0 else ""
            pct = sdata["duration_s"] / elapsed * 100 if elapsed > 0 else 0
            print(f"    {sname:<12} {sdata['duration_s']:>7.1f}s  {pct:>5.1f}%  {bar}")
        print(f"    {'TOTAL':<12} {elapsed:>7.1f}s")
        print("-" * 64)
        print()

    def write_log(self):
        """Write run_log.json to output directory."""
        os.makedirs(self.output_dir, exist_ok=True)
        log_path = os.path.join(self.output_dir, "run_log.json")
        with open(log_path, "w") as f:
            json.dump(self.data, f, indent=2)
        print(f"  Run log: {log_path}")

    def write_metrics(self, metrics_data: dict):
        """Write pipeline metrics.json to output directory."""
        os.makedirs(self.output_dir, exist_ok=True)
        metrics_path = os.path.join(self.output_dir, "metrics.json")
        with open(metrics_path, "w") as f:
            json.dump(metrics_data, f, indent=2)
        print(f"  Metrics: {metrics_path}")


def _ts() -> str:
    """Short timestamp for log lines."""
    return datetime.now().strftime("%H:%M:%S")


def _metric_highlights(stage_name: str, m: dict) -> str:
    """Pick the most important metrics per stage for inline display."""
    parts = []
    if stage_name == "ingest":
        if "slide_count" in m:
            parts.append(f"{m['slide_count']} slides")
    elif stage_name == "evidence":
        if "evidence_count" in m:
            parts.append(f"{m['evidence_count']} evidence items")
    elif stage_name == "render":
        if "slide_count" in m:
            parts.append(f"{m['slide_count']} PNGs")
        if "pdf_size" in m:
            parts.append(f"PDF {m['pdf_size'] / 1024:.0f} KB")
    elif stage_name == "graph":
        if "unified_graph_count" in m:
            parts.append(f"{m['unified_graph_count']} unified graphs")
    elif stage_name in ("script", "script_en"):
        if "segment_count" in m:
            parts.append(f"{m['segment_count']} segments")
    elif stage_name in ("verify", "verify_en"):
        for key in ("pass_count", "rewrite_count", "remove_count"):
            if key in m:
                parts.append(f"{m[key]} {key.replace('_count', '').upper()}")
    elif stage_name in ("audio", "audio_en"):
        if "total_audio_duration_s" in m:
            parts.append(f"{m['total_audio_duration_s']:.1f}s audio")
    elif stage_name in ("video", "video_en"):
        if "total_duration" in m:
            parts.append(f"{m['total_duration']:.1f}s video")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    """Run full pipeline on a PPTX file (synchronous, no Redis/RQ needed)."""
    from dotenv import load_dotenv

    load_dotenv()

    pptx_path = os.path.abspath(args.pptx_path)
    if not os.path.exists(pptx_path):
        print(f"Error: file not found: {pptx_path}", file=sys.stderr)
        return 1
    if not pptx_path.lower().endswith(".pptx"):
        print(f"Error: expected .pptx file, got: {pptx_path}", file=sys.stderr)
        return 1

    preset = (args.preset or "draft").strip().lower()
    output_dir = os.path.abspath(args.output or "./output")
    run_id = str(uuid.uuid4())

    # Initialise logger
    logger = PipelineLogger(run_id, output_dir, pptx_path, preset)

    # Doctor check
    from doctor import run_doctor

    doctor_report = run_doctor()
    logger.set_doctor(doctor_report)
    if not doctor_report.get("all_required_ok"):
        print(
            "Error: missing required dependencies. Run 'slidesherlock doctor'.",
            file=sys.stderr,
        )
        return 1

    # Apply preset
    from presets import apply_preset, VALID_PRESETS

    if preset not in VALID_PRESETS:
        print(
            f"Error: unknown preset '{preset}'. Valid: {', '.join(VALID_PRESETS)}",
            file=sys.stderr,
        )
        return 1
    os.environ["SLIDESHERLOCK_PRESET"] = preset
    apply_preset(preset)

    logger.header()

    # DB + storage setup. Storage backend is selected via the OCP registry —
    # MinIO by default (existing flow), LocalFS when DATABASE_URL=sqlite://…
    # or STORAGE_BACKEND=local. Both call sites use the same .get/.put/.exists.
    from apps.api.database import SessionLocal, init_db
    from apps.api.models import Project, Job, JobStatus, Artifact
    from storage_backend import get_storage_backend

    init_db()  # no-op for postgres (alembic owns); create_all for sqlite
    db = SessionLocal()
    minio_client = get_storage_backend()

    try:
        # Create project + job in DB
        project = Project(name=os.path.basename(pptx_path), description=f"CLI run {run_id[:8]}")
        db.add(project)
        db.flush()

        job = Job(
            project_id=project.project_id,
            status="QUEUED",
            requested_language=getattr(args, "lang", None),
        )
        db.add(job)
        db.flush()
        job_id = job.job_id

        # Upload PPTX to MinIO
        input_path = f"jobs/{job_id}/input/deck.pptx"
        job.input_file_path = input_path
        db.commit()

        with open(pptx_path, "rb") as f:
            pptx_data = f.read()
        minio_client.put(
            input_path,
            pptx_data,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        print(f"  Uploaded {os.path.basename(pptx_path)} ({len(pptx_data) / 1024:.0f} KB)")
        print(f"  Job ID:  {job_id}")
        print()

        # Run pipeline synchronously with per-stage logging
        import tempfile
        from pipeline import (
            PipelineContext,
            StageResult,
            _run_stage,
            SHARED_STAGES,
            PER_VARIANT_STAGES,
        )

        # Update status
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        pipeline_start = time.time()

        # Load vision config
        vision_config: Dict[str, Any] = {}
        vision_enabled = True
        try:
            from vision_config import get_vision_config

            vision_config = get_vision_config(None)
            vision_enabled = vision_config.get("enabled", True)
        except ImportError:
            pass

        temp_dir = tempfile.mkdtemp(prefix=f"cli_{job_id[:8]}_")

        ctx = PipelineContext(
            job_id=job_id,
            project_id=project.project_id,
            minio_client=minio_client,
            db_session=db,
            config={"input_file_path": input_path},
            vision_config=vision_config,
            vision_enabled=vision_enabled,
            temp_dir=temp_dir,
        )

        # LLM provider — always use Stub for script/verify stages.
        # AI narration is handled by NarrateStage (reads ctx.config["ai_narration"]).
        try:
            from llm_provider import StubLLMProvider

            ctx.llm_provider = StubLLMProvider()
        except ImportError:
            pass

        # AI narration flag: set from --ai-narration flag or LLM_PROVIDER env var
        llm_mode = os.environ.get("LLM_PROVIDER", "auto").strip().lower()
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        ai_narration_requested = getattr(args, "ai_narration", False) or (
            llm_mode not in ("stub", "auto") and bool(api_key)
        )
        ctx.config["ai_narration"] = ai_narration_requested
        if ai_narration_requested:
            logger.stage_detail("AI narration: ON (NarrateStage will use GPT-4o)")
        else:
            logger.stage_detail("AI narration: OFF (template narration)")

        # ---- SHARED STAGES ----
        for stage in SHARED_STAGES:
            logger.stage_start(stage.name)
            result = _run_stage(stage, ctx)
            logger.stage_end(stage.name, result)

            if stage.name == "ingest":
                logger.set_slide_count(ctx.slide_count)

            if result.status == "failed":
                print(f"  Stage '{stage.name}' failed — continuing...")

        # ---- PER-VARIANT STAGES ----
        if ctx.output_variants and ctx.unified_graphs:
            for variant in ctx.output_variants:
                variant_id = variant.get("id", "en")
                ctx.variant = variant
                ctx.script_prefix = f"jobs/{job_id}/script/{variant_id}/"
                ctx.audio_prefix = f"jobs/{job_id}/audio/{variant_id}/"
                ctx.timeline_prefix = f"jobs/{job_id}/timing/{variant_id}/"
                ctx.timeline_path_prefix = f"jobs/{job_id}/timeline/{variant_id}/"
                ctx.overlay_prefix = f"jobs/{job_id}/overlays/{variant_id}/"
                ctx.output_prefix = f"jobs/{job_id}/output/{variant_id}/"

                # Reset per-variant state
                ctx.verified_script = None
                ctx.verify_report = []
                ctx.coverage = {}
                ctx.script_for_downstream = None
                ctx.narration_entries = []
                ctx.narration_entries_override = None
                ctx.per_slide_audio_paths = []
                ctx.per_slide_durations_dict = {}
                ctx.per_slide_notes_for_overlay = None
                ctx.translation_degraded = False
                ctx.slides_notes_and_text = []

                logger.set_variant(variant_id)
                print(f"  --- Variant: {variant_id} (lang={variant.get('lang')}) ---")
                print()

                # --dry-run: stop after verify (skip translate/narrate/audio/video)
                # --skip-av: skip only audio+video (keep narrate for hallucination experiments)
                if getattr(args, "dry_run", False):
                    dry_run_skip = {"translate", "narrate", "audio", "video"}
                elif getattr(args, "skip_av", False):
                    dry_run_skip = {"audio", "video"}
                else:
                    dry_run_skip = set()

                for stage in PER_VARIANT_STAGES:
                    if stage.name in dry_run_skip:
                        logger.stage_start(stage.name)
                        logger.stage_end(
                            stage.name, StageResult(status="skipped", metrics={"reason": "dry-run"})
                        )
                        continue
                    stage_key = f"{stage.name}_{variant_id}"
                    logger.stage_start(stage.name)
                    result = _run_stage(stage, ctx)
                    ctx.stage_results[stage_key] = result
                    logger.stage_end(stage_key, result)

        db.commit()

        # Write metrics.json to MinIO (same as pipeline.py)
        pipeline_elapsed_ms = int((time.time() - pipeline_start) * 1000)
        stages_metrics = {}
        for sname, sresult in ctx.stage_results.items():
            stages_metrics[sname] = {
                "status": sresult.status,
                "duration_ms": sresult.duration_ms,
                "metrics": sresult.metrics,
            }

        metrics_payload = {
            "job_id": job_id,
            "preset": preset,
            "pipeline_duration_ms": pipeline_elapsed_ms,
            "stages": stages_metrics,
            "created_at": datetime.now(timezone.utc).isoformat() + "Z",
        }

        metrics_path = f"jobs/{job_id}/metrics.json"
        minio_client.put(
            metrics_path,
            json.dumps(metrics_payload, indent=2).encode(),
            "application/json",
        )

        db.add(
            Artifact(
                artifact_id=str(uuid.uuid4()),
                project_id=project.project_id,
                job_id=job_id,
                artifact_type="metrics",
                storage_path=metrics_path,
                metadata_json=json.dumps({"type": "metrics", "stage": "pipeline"}),
                created_at=datetime.now(timezone.utc),
            )
        )

        job.status = JobStatus.RUNNING
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        # Download outputs to local output directory
        os.makedirs(output_dir, exist_ok=True)
        output_video = None

        for variant in ctx.output_variants or [{"id": "en"}]:
            vid = variant.get("id", "en")
            final_key = f"jobs/{job_id}/output/{vid}/final.mp4"
            try:
                data = minio_client.get(final_key)
                local_path = os.path.join(
                    output_dir,
                    f"final_{vid}.mp4" if len(ctx.output_variants) > 1 else "final.mp4",
                )
                with open(local_path, "wb") as f:
                    f.write(data)
                if output_video is None:
                    output_video = local_path
            except Exception:
                pass

        # Download metrics.json locally
        logger.write_metrics(metrics_payload)

        # Download paper-relevant artifacts from MinIO
        paper_data = {}
        for variant in ctx.output_variants or [{"id": "en"}]:
            vid = variant.get("id", "en")
            artifacts_to_download = {
                "verify_report": f"jobs/{job_id}/script/{vid}/verify_report.json",
                "coverage": f"jobs/{job_id}/script/{vid}/coverage.json",
                "evidence_index": f"jobs/{job_id}/evidence/index.json",
                "ai_narration": f"jobs/{job_id}/script/{vid}/ai_narration.json",
                "narration_per_slide": f"jobs/{job_id}/script/{vid}/narration_per_slide.json",
            }
            for name, key in artifacts_to_download.items():
                try:
                    data = minio_client.get(key)
                    parsed = json.loads(data.decode("utf-8"))
                    # Save locally
                    local_path = os.path.join(output_dir, f"{name}.json")
                    with open(local_path, "w") as f:
                        json.dump(parsed, f, indent=2)
                    paper_data[name] = parsed
                except Exception:
                    pass

        # Extract paper-relevant metrics into run_log
        if "coverage" in paper_data:
            cov = paper_data["coverage"]
            logger.data["coverage"] = {
                "total_claims": cov.get("total_claims", 0),
                "claims_with_evidence": cov.get("claims_with_evidence", 0),
                "pct_claims_with_evidence": cov.get("pct_claims_with_evidence", 0),
                "entities_total": cov.get("entities_total", 0),
                "entities_grounded": cov.get("entities_grounded", 0),
                "pct_entities_grounded": cov.get("pct_entities_grounded", 0),
                "pass": cov.get("pass", 0),
                "rewrite": cov.get("rewrite", 0),
                "remove": cov.get("remove", 0),
            }
        if "evidence_index" in paper_data:
            items = paper_data["evidence_index"].get("evidence_items", [])
            kinds: Dict[str, int] = {}
            for item in items:
                k = item.get("kind", "unknown")
                kinds[k] = kinds.get(k, 0) + 1
            logger.data["evidence"] = {
                "total_items": len(items),
                "kinds": kinds,
            }
        if "verify_report" in paper_data:
            decisions = paper_data["verify_report"].get("decisions", [])
            verdicts: Dict[str, int] = {}
            reasons_all: Dict[str, int] = {}
            for d in decisions:
                v = d.get("verdict", "unknown")
                verdicts[v] = verdicts.get(v, 0) + 1
                for r in d.get("reasons", []):
                    reasons_all[r] = reasons_all.get(r, 0) + 1
            logger.data["verify"] = {
                "total_decisions": len(decisions),
                "verdicts": verdicts,
                "iterations": paper_data["verify_report"].get("iterations", 1),
                "reason_distribution": reasons_all,
            }
        if "ai_narration" in paper_data:
            logger.data["ai_narration"] = {
                "slides_rewritten": paper_data["ai_narration"].get("ai_rewritten", 0),
                "slides_total": paper_data["ai_narration"].get("slide_count", 0),
            }

        # Generate evidence trail HTML report
        if (
            "evidence_index" in paper_data
            and "coverage" in paper_data
            and "verify_report" in paper_data
        ):
            try:
                from evidence_report import generate_evidence_report

                html = generate_evidence_report(
                    paper_data["evidence_index"],
                    paper_data["coverage"],
                    paper_data["verify_report"],
                )
                report_path = os.path.join(output_dir, "evidence_report.html")
                with open(report_path, "w") as f:
                    f.write(html)
            except Exception:
                pass

        # Summary
        logger.summary(output_video)
        logger.write_log()

        # Cleanup temp
        import shutil

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

        return 0

    except Exception as e:
        import traceback

        print(f"\nError: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1
    finally:
        db.close()


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run doctor checks."""
    from doctor import run_doctor, print_doctor_report

    report = run_doctor()
    print_doctor_report(report)

    if args.json:
        print()
        print(json.dumps(report, indent=2))

    return 0 if report.get("all_required_ok", False) else 1


def cmd_preset(args: argparse.Namespace) -> int:
    """Show or apply quality preset."""
    from presets import apply_preset, get_preset_env_vars, VALID_PRESETS

    preset = (args.preset or "").strip().lower()
    if not preset:
        print("Quality presets: draft | standard | pro")
        print("")
        print("  draft:    no vision, no bgm, cut transitions")
        print("  standard: notes overlay + crossfade + subtitles")
        print("  pro:      vision+merge + timeline actions + bgm ducking + loudness normalize")
        print("")
        print("Usage: slidesherlock preset <preset>")
        print("       SLIDESHERLOCK_PRESET=standard make worker")
        return 0
    if preset not in VALID_PRESETS:
        print(
            f"Unknown preset: {preset}. Valid: {', '.join(VALID_PRESETS)}",
            file=sys.stderr,
        )
        return 1
    if args.export:
        for k, v in get_preset_env_vars(preset).items():
            print(f"export {k}={v!r}")
        return 0
    apply_preset(preset)
    os.environ["SLIDESHERLOCK_PRESET"] = preset
    print(f"Applied preset: {preset}")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="slidesherlock",
        description="SlideSherlock — evidence-grounded presentation-to-video pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # run
    run_parser = subparsers.add_parser("run", help="Run full pipeline on a PPTX file")
    run_parser.add_argument("pptx_path", help="Path to the .pptx file")
    run_parser.add_argument(
        "--preset",
        "-p",
        default="draft",
        help="Quality preset: draft|standard|pro (default: draft)",
    )
    run_parser.add_argument(
        "--output",
        "-o",
        default="./output",
        help="Output directory (default: ./output)",
    )
    run_parser.add_argument(
        "--lang",
        "-l",
        default=None,
        help="Add language variants, comma-separated (e.g. hi-IN or hi-IN,es-ES,fr-FR)",
    )
    run_parser.add_argument(
        "--ai-narration",
        action="store_true",
        default=False,
        help="Enable AI narration (GPT-4o rewrite, requires OPENAI_API_KEY)",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run through verify stage then stop (no audio/video). Outputs metrics + evidence only.",
    )
    run_parser.add_argument(
        "--skip-av",
        action="store_true",
        default=False,
        help="Skip audio+video stages (keep narrate). For hallucination experiments.",
    )
    run_parser.set_defaults(func=cmd_run)

    # doctor
    doctor_parser = subparsers.add_parser("doctor", help="Check system dependencies")
    doctor_parser.add_argument("--json", "-j", action="store_true", help="Also print JSON report")
    doctor_parser.set_defaults(func=cmd_doctor)

    # preset
    preset_parser = subparsers.add_parser("preset", help="Show or apply quality preset")
    preset_parser.add_argument("preset", nargs="?", help="Preset name")
    preset_parser.add_argument("--export", "-e", action="store_true", help="Print export lines")
    preset_parser.set_defaults(func=cmd_preset)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
