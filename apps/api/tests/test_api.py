"""Basic API tests"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient  # noqa: E402
from apps.api.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    """Test health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
    project_id = test_create_project()
    response = client.get(f"/projects/{project_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == project_id


def test_create_job():
    """Test job creation"""
    project_id = test_create_project()
    response = client.post("/jobs", json={"project_id": project_id})
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["project_id"] == project_id
    assert data["status"] == "QUEUED"
    return data["job_id"]


def test_get_job():
    """Test getting a job"""
    job_id = test_create_job()
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
