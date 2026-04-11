"""API tests – health, CRUD, upload validation, progress, metrics, evidence trail."""

import io
import json
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient  # noqa: E402
from apps.api.main import app  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_project(name="Test Project", description="Test description"):
    response = client.post("/projects", json={"name": name, "description": description})
    assert response.status_code == 200
    return response.json()["project_id"]


def _create_job(project_id=None):
    if project_id is None:
        project_id = _create_project()
    response = client.post("/jobs", json={"project_id": project_id})
    assert response.status_code == 200
    return response.json()["job_id"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health():
    """Test health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def test_create_project():
    """Test project creation"""
    response = client.post(
        "/projects", json={"name": "Test Project", "description": "Test description"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "project_id" in data
    assert data["name"] == "Test Project"
    return data["project_id"]


def test_get_project():
    """Test getting a project"""
    project_id = _create_project()
    response = client.get(f"/projects/{project_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == project_id


def test_get_project_not_found():
    response = client.get("/projects/does-not-exist-xxx")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_create_project_description_optional():
    response = client.post("/projects", json={"name": "No Desc"})
    assert response.status_code == 200
    assert response.json()["name"] == "No Desc"


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def test_create_job():
    """Test job creation"""
    project_id = _create_project()
    response = client.post("/jobs", json={"project_id": project_id})
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["project_id"] == project_id
    assert data["status"] == "QUEUED"
    return data["job_id"]


def test_get_job():
    """Test getting a job"""
    job_id = _create_job()
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id


def test_get_job_not_found():
    response = client.get("/jobs/nonexistent-job-id")
    assert response.status_code == 404


def test_create_job_project_not_found():
    response = client.post("/jobs", json={"project_id": "ghost-project"})
    assert response.status_code == 404


def test_create_job_with_language():
    project_id = _create_project()
    response = client.post(
        "/jobs", json={"project_id": project_id, "requested_language": "hi-IN"}
    )
    assert response.status_code == 200
    assert response.json()["requested_language"] == "hi-IN"


# ---------------------------------------------------------------------------
# Upload PPTX – validation (no real MinIO needed for validation path)
# ---------------------------------------------------------------------------

def test_upload_pptx_rejects_non_pptx():
    job_id = _create_job()
    fake_file = io.BytesIO(b"not a pptx")
    response = client.post(
        f"/jobs/{job_id}/upload_pptx",
        files={"file": ("deck.txt", fake_file, "text/plain")},
    )
    assert response.status_code == 400
    assert "pptx" in response.json()["detail"].lower()


def test_upload_pptx_job_not_found():
    fake_file = io.BytesIO(b"data")
    response = client.post(
        "/jobs/nonexistent/upload_pptx",
        files={"file": ("deck.pptx", fake_file, "application/octet-stream")},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Progress endpoint
# ---------------------------------------------------------------------------

def test_get_job_progress_job_not_found():
    response = client.get("/jobs/ghost-job/progress")
    assert response.status_code == 404


def test_get_job_progress_returns_structure():
    """Progress endpoint returns the expected keys when MinIO is mocked."""
    job_id = _create_job()
    mock_minio = MagicMock()
    mock_minio.exists.return_value = False
    mock_minio.get.side_effect = Exception("no file")

    with patch("apps.api.main.MinIOClient", return_value=mock_minio):
        response = client.get(f"/jobs/{job_id}/progress")

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert "status" in data
    assert "stages" in data
    assert "percent" in data


# ---------------------------------------------------------------------------
# Evidence trail endpoint
# ---------------------------------------------------------------------------

def test_get_evidence_trail_job_not_found():
    response = client.get("/jobs/ghost/evidence-trail")
    assert response.status_code == 404


def test_get_evidence_trail_returns_structure():
    job_id = _create_job()
    mock_minio = MagicMock()
    mock_minio.get.side_effect = Exception("no manifest")

    with patch("apps.api.main.MinIOClient", return_value=mock_minio):
        response = client.get(f"/jobs/{job_id}/evidence-trail")

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["decisions"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# Metrics endpoint
# ---------------------------------------------------------------------------

def test_get_job_metrics_job_not_found():
    response = client.get("/jobs/ghost/metrics")
    assert response.status_code == 404


def test_get_job_metrics_not_available_yet():
    job_id = _create_job()
    mock_minio = MagicMock()
    mock_minio.get.side_effect = Exception("no metrics")

    with patch("apps.api.main.MinIOClient", return_value=mock_minio):
        response = client.get(f"/jobs/{job_id}/metrics")

    assert response.status_code == 404
    assert "metrics" in response.json()["detail"].lower()


def test_get_job_metrics_returns_shape():
    job_id = _create_job()
    metrics_payload = json.dumps({
        "pipeline_duration_ms": 5000,
        "stages": {
            "ingest": {"metrics": {"slide_count": 10}},
            "graph": {"metrics": {"unified_graph_count": 8}},
        },
    }).encode()

    mock_minio = MagicMock()
    mock_minio.get.side_effect = lambda path: (
        metrics_payload if "metrics.json" in path else (_ for _ in ()).throw(Exception("no file"))
    )

    with patch("apps.api.main.MinIOClient", return_value=mock_minio):
        response = client.get(f"/jobs/{job_id}/metrics")

    assert response.status_code == 200
    data = response.json()
    assert "slide_count" in data
    assert data["slide_count"] == 10
    assert data["total_duration_s"] == pytest.approx(5.0)
