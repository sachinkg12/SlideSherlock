"""
Unit tests for pipeline.py — PipelineContext, StageResult, _run_stage, and run_pipeline orchestration.
"""
from __future__ import annotations

import os
import sys
import json
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline import PipelineContext, StageResult, _run_stage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_minio():
    m = MagicMock()
    m.put = MagicMock()
    return m


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(
        job_id="job-test",
        project_id="proj-1",
        input_file_path="jobs/job-test/input.pptx",
        config_json=None,
        status=None,
    )
    return db


@pytest.fixture
def basic_ctx(mock_minio, mock_db):
    return PipelineContext(
        job_id="job-test",
        project_id="proj-1",
        minio_client=mock_minio,
        db_session=mock_db,
    )


@pytest.fixture
def ok_stage():
    stage = MagicMock()
    stage.name = "ok_stage"
    stage.run.return_value = StageResult(status="ok", metrics={"count": 1})
    return stage


@pytest.fixture
def failing_stage():
    stage = MagicMock()
    stage.name = "bad_stage"
    stage.run.side_effect = RuntimeError("Something went wrong")
    return stage


@pytest.fixture
def skipped_stage():
    stage = MagicMock()
    stage.name = "skip_stage"
    stage.run.return_value = StageResult(status="skipped")
    return stage


# ---------------------------------------------------------------------------
# PipelineContext defaults
# ---------------------------------------------------------------------------


def test_pipeline_context_defaults():
    ctx = PipelineContext(job_id="j1", project_id="p1", minio_client=None, db_session=None)
    assert ctx.slide_count == 0
    assert ctx.slides_data == []
    assert ctx.stage_results == {}
    assert ctx.artifacts == {}
    assert ctx.vision_enabled is True
    assert ctx.translation_degraded is False
    assert ctx.narration_entries == []
    assert ctx.output_variants == []


def test_pipeline_context_config_override():
    ctx = PipelineContext(
        job_id="j2",
        project_id="p2",
        minio_client=None,
        db_session=None,
        config={"input_file_path": "jobs/j2/input.pptx"},
        vision_enabled=False,
    )
    assert ctx.config["input_file_path"] == "jobs/j2/input.pptx"
    assert ctx.vision_enabled is False


# ---------------------------------------------------------------------------
# StageResult
# ---------------------------------------------------------------------------


def test_stage_result_defaults():
    r = StageResult(status="ok")
    assert r.status == "ok"
    assert r.duration_ms == 0
    assert r.artifacts_written == []
    assert r.metrics == {}


def test_stage_result_with_metrics():
    r = StageResult(status="failed", metrics={"error": "timeout"}, duration_ms=2500)
    assert r.status == "failed"
    assert r.duration_ms == 2500
    assert r.metrics["error"] == "timeout"


# ---------------------------------------------------------------------------
# _run_stage
# ---------------------------------------------------------------------------


def test_run_stage_ok(basic_ctx, ok_stage):
    result = _run_stage(ok_stage, basic_ctx)
    assert result.status == "ok"
    assert result.duration_ms >= 0
    assert basic_ctx.stage_results["ok_stage"].status == "ok"


def test_run_stage_records_timing(basic_ctx, ok_stage):
    result = _run_stage(ok_stage, basic_ctx)
    # duration_ms is set (may be 0 on fast machines but should be non-negative)
    assert isinstance(result.duration_ms, int)
    assert result.duration_ms >= 0


def test_run_stage_failed_exception_caught(basic_ctx, failing_stage):
    result = _run_stage(failing_stage, basic_ctx)
    assert result.status == "failed"
    assert "Something went wrong" in result.metrics.get("error", "")
    assert basic_ctx.stage_results["bad_stage"].status == "failed"


def test_run_stage_skipped(basic_ctx, skipped_stage):
    result = _run_stage(skipped_stage, basic_ctx)
    assert result.status == "skipped"
    assert basic_ctx.stage_results["skip_stage"].status == "skipped"


def test_run_stage_stores_result_on_context(basic_ctx, ok_stage):
    _run_stage(ok_stage, basic_ctx)
    assert "ok_stage" in basic_ctx.stage_results


def test_run_stage_preserves_existing_results(basic_ctx, ok_stage, skipped_stage):
    _run_stage(ok_stage, basic_ctx)
    _run_stage(skipped_stage, basic_ctx)
    assert "ok_stage" in basic_ctx.stage_results
    assert "skip_stage" in basic_ctx.stage_results


# ---------------------------------------------------------------------------
# Per-variant state reset behavior (validated through context mutation)
# ---------------------------------------------------------------------------


def test_per_variant_state_fields_exist(basic_ctx):
    """All fields that are reset per variant are present on PipelineContext."""
    fields = [
        "verified_script",
        "verify_report",
        "coverage",
        "script_for_downstream",
        "narration_entries",
        "narration_entries_override",
        "per_slide_audio_paths",
        "per_slide_durations_dict",
        "per_slide_notes_for_overlay",
        "translation_degraded",
        "slides_notes_and_text",
    ]
    for f in fields:
        assert hasattr(basic_ctx, f), f"Missing field: {f}"


def test_context_variant_prefix_paths(basic_ctx):
    """Variant prefix paths default to empty strings and can be set."""
    assert basic_ctx.script_prefix == ""
    assert basic_ctx.audio_prefix == ""
    assert basic_ctx.overlay_prefix == ""
    basic_ctx.script_prefix = "jobs/job-test/script/en/"
    assert basic_ctx.script_prefix == "jobs/job-test/script/en/"


# ---------------------------------------------------------------------------
# run_pipeline integration (all heavy deps mocked)
# ---------------------------------------------------------------------------


def _make_mock_job(job_id="job-abc", input_path="jobs/job-abc/input.pptx", config_json=None):
    job = MagicMock()
    job.job_id = job_id
    job.project_id = "proj-1"
    job.input_file_path = input_path
    job.config_json = config_json
    job.status = None
    job.error_message = None
    job.updated_at = None
    return job


def _build_run_pipeline_patches(job, db, minio):
    """Return a dict of patches needed to exercise run_pipeline end-to-end."""
    return {
        "pipeline.get_storage_backend": MagicMock(return_value=minio),
        "pipeline.SessionLocal": MagicMock(return_value=db),
        "pipeline.Job": MagicMock(),
        "pipeline.JobStatus": MagicMock(PROCESSING="PROCESSING", RUNNING="RUNNING", FAILED="FAILED"),
        "pipeline.Artifact": MagicMock(),
        "pipeline.SHARED_STAGES": [],
        "pipeline.PER_VARIANT_STAGES": [],
    }


def _common_patches(db, minio, shared_stages=None, per_variant_stages=None):
    """Return the dict of patches for run_pipeline tests.

    pipeline.py imports get_storage_backend, SessionLocal, Job, JobStatus,
    Artifact, StubLLMProvider all *inside* run_pipeline() via local imports,
    so we patch the source modules rather than pipeline-level attributes.
    """
    patches = {
        "storage_backend.get_storage_backend": minio if callable(minio) else MagicMock(return_value=minio),
        "pipeline.SHARED_STAGES": shared_stages if shared_stages is not None else [],
        "pipeline.PER_VARIANT_STAGES": per_variant_stages if per_variant_stages is not None else [],
    }
    return patches


def test_run_pipeline_job_not_found():
    """run_pipeline exits cleanly when job is not in DB."""
    from pipeline import run_pipeline

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    fake_session_local = MagicMock(return_value=db)

    fake_models = MagicMock()
    fake_job_status = MagicMock()

    with patch.dict("sys.modules", {
        "storage_backend": MagicMock(get_storage_backend=MagicMock(return_value=MagicMock())),
        "apps.api.database": MagicMock(SessionLocal=fake_session_local),
        "apps.api.models": MagicMock(Job=MagicMock(), JobStatus=fake_job_status, Artifact=MagicMock()),
        "llm_provider": MagicMock(StubLLMProvider=MagicMock()),
        "presets": MagicMock(get_current_preset=MagicMock(return_value=None), apply_preset=MagicMock()),
        "vision_config": MagicMock(get_vision_config=MagicMock(return_value={})),
    }), patch("pipeline.SHARED_STAGES", []), patch("pipeline.PER_VARIANT_STAGES", []):
        run_pipeline("nonexistent-job")

    db.close.assert_called_once()


def test_run_pipeline_missing_input_file_marks_failed():
    """run_pipeline marks job as FAILED when input_file_path is missing."""
    from pipeline import run_pipeline

    job = _make_mock_job(input_path=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = job
    fake_session_local = MagicMock(return_value=db)

    fake_job_status = MagicMock()
    fake_job_status.PROCESSING = "PROCESSING"
    fake_job_status.FAILED = "FAILED"
    fake_job_status.RUNNING = "RUNNING"

    with patch.dict("sys.modules", {
        "storage_backend": MagicMock(get_storage_backend=MagicMock(return_value=MagicMock())),
        "apps.api.database": MagicMock(SessionLocal=fake_session_local),
        "apps.api.models": MagicMock(Job=MagicMock(), JobStatus=fake_job_status, Artifact=MagicMock()),
        "llm_provider": MagicMock(StubLLMProvider=MagicMock()),
        "presets": MagicMock(get_current_preset=MagicMock(return_value=None), apply_preset=MagicMock()),
        "vision_config": MagicMock(get_vision_config=MagicMock(return_value={})),
    }), patch("pipeline.SHARED_STAGES", []), patch("pipeline.PER_VARIANT_STAGES", []):
        run_pipeline("job-no-input")

    assert job.status == fake_job_status.FAILED
    db.close.assert_called_once()


def test_run_pipeline_no_variants_skips_per_variant_stages():
    """When ctx.output_variants is empty, per-variant stages never run."""
    from pipeline import run_pipeline

    job = _make_mock_job()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = job
    fake_session_local = MagicMock(return_value=db)

    shared_stage = MagicMock()
    shared_stage.name = "ingest"
    shared_stage.run.return_value = StageResult(status="ok")

    per_variant_stage = MagicMock()
    per_variant_stage.name = "script"
    per_variant_stage.run.return_value = StageResult(status="ok")

    fake_job_status = MagicMock()
    fake_job_status.PROCESSING = "PROCESSING"
    fake_job_status.RUNNING = "RUNNING"
    fake_job_status.FAILED = "FAILED"

    minio = MagicMock()

    with patch.dict("sys.modules", {
        "storage_backend": MagicMock(get_storage_backend=MagicMock(return_value=minio)),
        "apps.api.database": MagicMock(SessionLocal=fake_session_local),
        "apps.api.models": MagicMock(Job=MagicMock(), JobStatus=fake_job_status, Artifact=MagicMock()),
        "llm_provider": MagicMock(StubLLMProvider=MagicMock()),
        "presets": MagicMock(get_current_preset=MagicMock(return_value=None), apply_preset=MagicMock()),
        "vision_config": MagicMock(get_vision_config=MagicMock(return_value={})),
    }), patch("pipeline.SHARED_STAGES", [shared_stage]), \
        patch("pipeline.PER_VARIANT_STAGES", [per_variant_stage]), \
        patch("pipeline.tempfile.mkdtemp", return_value="/tmp/fake_dir"), \
        patch("pipeline.os.path.exists", return_value=False):
        run_pipeline("job-abc")

    shared_stage.run.assert_called_once()
    per_variant_stage.run.assert_not_called()


def test_run_pipeline_writes_metrics_json():
    """run_pipeline calls minio.put with metrics.json."""
    from pipeline import run_pipeline

    job = _make_mock_job()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = job
    fake_session_local = MagicMock(return_value=db)

    fake_job_status = MagicMock()
    fake_job_status.PROCESSING = "PROCESSING"
    fake_job_status.RUNNING = "RUNNING"
    fake_job_status.FAILED = "FAILED"

    minio = MagicMock()

    with patch.dict("sys.modules", {
        "storage_backend": MagicMock(get_storage_backend=MagicMock(return_value=minio)),
        "apps.api.database": MagicMock(SessionLocal=fake_session_local),
        "apps.api.models": MagicMock(Job=MagicMock(), JobStatus=fake_job_status, Artifact=MagicMock()),
        "llm_provider": MagicMock(StubLLMProvider=MagicMock()),
        "presets": MagicMock(get_current_preset=MagicMock(return_value=None), apply_preset=MagicMock()),
        "vision_config": MagicMock(get_vision_config=MagicMock(return_value={})),
    }), patch("pipeline.SHARED_STAGES", []), \
        patch("pipeline.PER_VARIANT_STAGES", []), \
        patch("pipeline.tempfile.mkdtemp", return_value="/tmp/fake_dir"), \
        patch("pipeline.os.path.exists", return_value=False):
        run_pipeline("job-abc")

    put_paths = [c.args[0] for c in minio.put.call_args_list]
    assert any("metrics.json" in p for p in put_paths), f"metrics.json not written; got: {put_paths}"


def test_run_pipeline_db_closed_on_exception():
    """DB session is always closed, even when an unhandled exception occurs."""
    from pipeline import run_pipeline

    db = MagicMock()
    # Simulate query crashing
    db.query.side_effect = Exception("DB connection lost")
    fake_session_local = MagicMock(return_value=db)

    with patch.dict("sys.modules", {
        "storage_backend": MagicMock(get_storage_backend=MagicMock(return_value=MagicMock())),
        "apps.api.database": MagicMock(SessionLocal=fake_session_local),
        "apps.api.models": MagicMock(Job=MagicMock(), JobStatus=MagicMock(), Artifact=MagicMock()),
        "llm_provider": MagicMock(StubLLMProvider=MagicMock()),
        "presets": MagicMock(get_current_preset=MagicMock(return_value=None), apply_preset=MagicMock()),
        "vision_config": MagicMock(get_vision_config=MagicMock(return_value={})),
    }), patch("pipeline.SHARED_STAGES", []), patch("pipeline.PER_VARIANT_STAGES", []):
        run_pipeline("job-crash")

    db.close.assert_called_once()
