"""
Tests for apps/api/worker.py: process_job (mocked DB + MinIO) and render_stage.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

# Project root on path so apps.api imports resolve
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, project_root)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_job(job_id="job-abc", status_val="QUEUED"):
    from apps.api.models import JobStatus

    job = MagicMock()
    job.job_id = job_id
    job.project_id = "proj-1"
    job.status = JobStatus.QUEUED
    job.error_message = None
    job.updated_at = datetime.utcnow()
    return job


# ---------------------------------------------------------------------------
# process_job
# ---------------------------------------------------------------------------

def test_process_job_marks_done_on_success():
    from apps.api.models import JobStatus
    from apps.api import worker as worker_module

    mock_job = _make_mock_job()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_job

    mock_minio = MagicMock()

    with patch.object(worker_module, "SessionLocal", return_value=mock_db), \
         patch("apps.api.worker.MinIOClient", return_value=mock_minio), \
         patch("time.sleep"):  # skip the dummy sleep
        worker_module.process_job("job-abc")

    assert mock_job.status == JobStatus.DONE
    mock_db.commit.assert_called()
    mock_db.close.assert_called_once()


def test_process_job_marks_failed_on_exception():
    from apps.api.models import JobStatus
    from apps.api import worker as worker_module

    mock_job = _make_mock_job()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_job
    # Force an exception mid-process
    mock_db.commit.side_effect = [None, RuntimeError("DB exploded"), None, None]

    with patch.object(worker_module, "SessionLocal", return_value=mock_db), \
         patch("apps.api.worker.MinIOClient", side_effect=RuntimeError("minio down")), \
         patch("time.sleep"):
        worker_module.process_job("job-abc")

    assert mock_job.status == JobStatus.FAILED
    assert mock_job.error_message is not None
    mock_db.close.assert_called_once()


def test_process_job_not_found_returns_early():
    from apps.api import worker as worker_module

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch.object(worker_module, "SessionLocal", return_value=mock_db), \
         patch("time.sleep"):
        worker_module.process_job("nonexistent-job")

    # No status mutations on a None job
    mock_db.close.assert_called_once()


def test_process_job_sets_processing_status_before_done():
    from apps.api.models import JobStatus
    from apps.api import worker as worker_module

    statuses_seen = []
    mock_job = _make_mock_job()

    original_setattr = object.__setattr__

    def track_status(obj, name, value):
        if name == "status":
            statuses_seen.append(value)
        mock_job.__dict__[name] = value

    mock_job.__setattr__ = track_status
    type(mock_job).status = property(
        lambda self: self.__dict__.get("status", JobStatus.QUEUED),
        lambda self, v: track_status(self, "status", v),
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_job

    with patch.object(worker_module, "SessionLocal", return_value=mock_db), \
         patch("apps.api.worker.MinIOClient", return_value=MagicMock()), \
         patch("time.sleep"):
        worker_module.process_job("job-abc")

    # PROCESSING should appear before DONE
    assert JobStatus.PROCESSING in statuses_seen
    done_idx = statuses_seen.index(JobStatus.DONE)
    proc_idx = statuses_seen.index(JobStatus.PROCESSING)
    assert proc_idx < done_idx


def test_process_job_uploads_artifact_to_minio():
    from apps.api import worker as worker_module

    mock_job = _make_mock_job()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_job
    mock_minio = MagicMock()

    with patch.object(worker_module, "SessionLocal", return_value=mock_db), \
         patch("apps.api.worker.MinIOClient", return_value=mock_minio), \
         patch("time.sleep"):
        worker_module.process_job("job-abc")

    mock_minio.put.assert_called_once()
    call_args = mock_minio.put.call_args
    assert "jobs/job-abc/" in call_args[0][0]


# ---------------------------------------------------------------------------
# render_stage
# ---------------------------------------------------------------------------

def test_render_stage_calls_run_pipeline():
    from apps.api import worker as worker_module

    mock_pipeline = MagicMock()
    with patch.dict("sys.modules", {"pipeline": mock_pipeline}):
        worker_module.render_stage("job-xyz")

    mock_pipeline.run_pipeline.assert_called_once_with("job-xyz")
