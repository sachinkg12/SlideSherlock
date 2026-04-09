"""Pipeline orchestrator: Stage protocol, PipelineContext, and run_pipeline()."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol
import time
import json
import os
import tempfile
import sys

# Ensure packages/core is on the path
_core_dir = os.path.dirname(os.path.abspath(__file__))
if _core_dir not in sys.path:
    sys.path.insert(0, _core_dir)


# ---------------------------------------------------------------------------
# Stage protocol & data classes
# ---------------------------------------------------------------------------


class Stage(Protocol):
    name: str

    def run(self, ctx: "PipelineContext") -> "StageResult":
        ...


@dataclass
class PipelineContext:
    job_id: str
    project_id: str
    minio_client: Any
    db_session: Any
    config: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    variant: Optional[Dict[str, Any]] = None
    stage_results: Dict[str, "StageResult"] = field(default_factory=dict)

    # Shared data between stages
    slides_data: List[Dict[str, Any]] = field(default_factory=list)
    images_index: Optional[Dict[str, Any]] = None
    image_kinds: Optional[Dict[str, Any]] = None
    slide_count: int = 0
    slide_metadata: List[Dict[str, Any]] = field(default_factory=list)
    slides_pil: List[Any] = field(default_factory=list)  # PIL images from pdf2image
    output_variants: List[Dict[str, Any]] = field(default_factory=list)
    evidence_index: Dict[str, Any] = field(default_factory=dict)
    unified_graphs: List[Dict[str, Any]] = field(default_factory=list)
    unified_by_slide: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    vision_graphs_by_slide: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    temp_dir: str = ""

    # Vision config
    vision_config: Dict[str, Any] = field(default_factory=dict)
    vision_enabled: bool = True

    # Per-variant state (reset before each variant)
    verified_script: Optional[Any] = None
    verify_report: List[Dict[str, Any]] = field(default_factory=list)
    coverage: Dict[str, Any] = field(default_factory=dict)
    script_for_downstream: Optional[Any] = None
    narration_entries: List[Dict[str, Any]] = field(default_factory=list)
    narration_entries_override: Optional[List[Dict[str, Any]]] = None
    per_slide_audio_paths: List[str] = field(default_factory=list)
    per_slide_durations_dict: Dict[int, float] = field(default_factory=dict)
    per_slide_notes_for_overlay: Optional[List[str]] = None
    translation_degraded: bool = False
    slides_notes_and_text: List[Any] = field(default_factory=list)

    # LLM provider (shared across stages)
    llm_provider: Optional[Any] = None

    # Paths (set per variant)
    script_prefix: str = ""
    audio_prefix: str = ""
    timeline_prefix: str = ""
    timeline_path_prefix: str = ""
    overlay_prefix: str = ""
    output_prefix: str = ""


@dataclass
class StageResult:
    status: str  # "ok" | "skipped" | "failed"
    duration_ms: int = 0
    artifacts_written: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stage registry
# ---------------------------------------------------------------------------

from stages.ingest import IngestStage
from stages.evidence import EvidenceStage
from stages.render import RenderStage
from stages.graph import GraphStage
from stages.script import ScriptStage
from stages.verify import VerifyStage
from stages.translate import TranslateStage
from stages.narrate import NarrateStage
from stages.audio import AudioStage
from stages.video import VideoStage

SHARED_STAGES: List[Stage] = [
    IngestStage(),
    EvidenceStage(),
    RenderStage(),
    GraphStage(),
]

PER_VARIANT_STAGES: List[Stage] = [
    ScriptStage(),
    VerifyStage(),
    TranslateStage(),
    NarrateStage(),
    AudioStage(),
    VideoStage(),
]


def _run_stage(stage: Stage, ctx: PipelineContext) -> StageResult:
    """Run a single stage, capturing timing and errors."""
    t0 = time.time()
    try:
        result = stage.run(ctx)
    except Exception as e:
        import traceback

        print(f"  Stage '{stage.name}' FAILED: {e}\n{traceback.format_exc()}")
        result = StageResult(status="failed", metrics={"error": str(e)})
    elapsed_ms = int((time.time() - t0) * 1000)
    result.duration_ms = elapsed_ms
    ctx.stage_results[stage.name] = result
    return result


# ---------------------------------------------------------------------------
# run_pipeline — the new entry point (replaces render_stage monolith)
# ---------------------------------------------------------------------------


def run_pipeline(job_id: str):
    """Execute the full pipeline for a job."""
    # Storage backend is selected via the OCP registry. With no env vars set,
    # this returns MinIOClient (existing Docker/Postgres flow — unchanged).
    # If DATABASE_URL=sqlite://… or STORAGE_BACKEND=local, returns LocalFSBackend.
    from storage_backend import get_storage_backend

    # DB imports — try relative first (when loaded as part of apps.api package),
    # then fall back to absolute for standalone worker process.
    try:
        from apps.api.database import SessionLocal
        from apps.api.models import Job, JobStatus, Artifact
    except ImportError:
        # Running inside the apps.api package (relative import context)
        from database import SessionLocal  # type: ignore
        from models import Job, JobStatus, Artifact  # type: ignore

    # Apply quality preset if SLIDESHERLOCK_PRESET is set
    try:
        from presets import get_current_preset, apply_preset

        preset = get_current_preset()
        if preset:
            apply_preset(preset)
    except Exception:
        pass

    db = SessionLocal()
    job = None
    temp_dir = None
    pipeline_start = time.time()

    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            print(f"Job {job_id} not found")
            return

        if not job.input_file_path:
            raise Exception("Job has no input file path")

        # Update status to PROCESSING
        job.status = JobStatus.PROCESSING
        from datetime import datetime

        job.updated_at = datetime.utcnow()
        db.commit()

        print(f"Render stage: Processing job {job_id}...")
        print(f"  Input file: {job.input_file_path}")

        minio_client = get_storage_backend()

        # Load vision config
        vision_config: Dict[str, Any] = {}
        vision_enabled = True
        try:
            from vision_config import get_vision_config

            vision_config = get_vision_config(getattr(job, "config_json", None))
            vision_enabled = vision_config.get("enabled", True)
            mc = vision_config.get("min_confidence_for_specific_claims")
            if mc is not None:
                os.environ["VERIFIER_HEDGING_CONFIDENCE_THRESHOLD"] = str(mc)
                os.environ["VISION_SCRIPT_IMAGE_CONFIDENCE_THRESHOLD"] = str(mc)
        except ImportError:
            pass

        temp_dir = tempfile.mkdtemp(prefix=f"render_{job_id}_")
        print(f"  Using temp directory: {temp_dir}")

        # Build context
        ctx = PipelineContext(
            job_id=job_id,
            project_id=job.project_id,
            minio_client=minio_client,
            db_session=db,
            config={"input_file_path": job.input_file_path},
            vision_config=vision_config,
            vision_enabled=vision_enabled,
            temp_dir=temp_dir,
        )

        # Initialize LLM provider — check job config_json, then env, then default to stub
        llm_mode = os.environ.get("LLM_PROVIDER", "auto").strip().lower()
        # Job-level override from config_json (set by API when user toggles AI narration)
        try:
            job_config = json.loads(job.config_json) if job.config_json else {}
            if job_config.get("llm_provider"):
                llm_mode = job_config["llm_provider"]
        except Exception:
            pass

        api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        print(f"  [LLM init] llm_mode={llm_mode}, api_key={'set' if api_key else 'unset'}")

        # Script/verify stages always use Stub (fast, deterministic, no API calls).
        # AI narration happens in the dedicated NarrateStage (post-verify).
        try:
            from llm_provider import StubLLMProvider

            ctx.llm_provider = StubLLMProvider()
        except ImportError:
            pass

        # Store AI narration flag in config so NarrateStage can check it
        if llm_mode not in ("stub", "auto") and api_key:
            ctx.config["ai_narration"] = True
            print("  LLM provider: Stub (script) + AI narration enabled (NarrateStage)")
        else:
            ctx.config["ai_narration"] = False
            print("  LLM provider: Stub (template narration)")

        # ---- SHARED STAGES ----
        for stage in SHARED_STAGES:
            result = _run_stage(stage, ctx)
            if result.status == "failed":
                print(f"  Shared stage '{stage.name}' failed, continuing...")

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

                print(f"  Processing variant: {variant_id} (lang={variant.get('lang')})")

                for stage in PER_VARIANT_STAGES:
                    stage_key = f"{stage.name}_{variant_id}"
                    result = _run_stage(stage, ctx)
                    ctx.stage_results[stage_key] = result

        # Commit all artifacts
        db.commit()

        # Write metrics.json
        pipeline_elapsed_ms = int((time.time() - pipeline_start) * 1000)
        stages_metrics = {}
        for sname, sresult in ctx.stage_results.items():
            stages_metrics[sname] = {
                "status": sresult.status,
                "duration_ms": sresult.duration_ms,
                "metrics": sresult.metrics,
            }

        from datetime import datetime

        metrics_payload = {
            "job_id": job_id,
            "preset": None,
            "pipeline_duration_ms": pipeline_elapsed_ms,
            "stages": stages_metrics,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        try:
            from presets import get_current_preset

            metrics_payload["preset"] = get_current_preset()
        except Exception:
            pass

        metrics_path = f"jobs/{job_id}/metrics.json"
        metrics_json = json.dumps(metrics_payload, indent=2)
        minio_client.put(metrics_path, metrics_json.encode("utf-8"), "application/json")

        import uuid

        db.add(
            Artifact(
                artifact_id=str(uuid.uuid4()),
                project_id=job.project_id,
                job_id=job_id,
                artifact_type="metrics",
                storage_path=metrics_path,
                metadata_json=json.dumps({"type": "metrics", "stage": "pipeline"}),
                created_at=datetime.utcnow(),
            )
        )

        db.commit()

        print(f"Render stage: Job {job_id} completed successfully")
        print(f"  - Slides: {ctx.slide_count} PNG files")

        # Update status
        job.status = JobStatus.RUNNING
        job.updated_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        import traceback

        error_msg = f"Error in render stage for job {job_id}: {e}\n{traceback.format_exc()}"
        print(error_msg)
        if job:
            from datetime import datetime

            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        if temp_dir and os.path.exists(temp_dir):
            import shutil

            try:
                shutil.rmtree(temp_dir)
                print(f"  Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                print(f"  Warning: Failed to clean up temp directory: {e}")
        db.close()
