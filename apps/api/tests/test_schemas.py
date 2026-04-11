"""
Tests for apps/api/schemas.py: Pydantic models – validation, serialisation,
optional fields, and model_validate from ORM-like objects.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import pytest

project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, project_root)

from apps.api.models import JobStatus
from apps.api.schemas import (
    ProjectCreate,
    ProjectResponse,
    JobCreate,
    JobResponse,
    VisionConfigSchema,
    OutputVariantSchema,
    VariantStatusSchema,
)


NOW = datetime(2024, 1, 1, 12, 0, 0)


# ---------------------------------------------------------------------------
# ProjectCreate
# ---------------------------------------------------------------------------

def test_project_create_name_required():
    with pytest.raises(Exception):
        ProjectCreate()  # type: ignore[call-arg]


def test_project_create_description_optional():
    p = ProjectCreate(name="My Project")
    assert p.description is None


def test_project_create_full():
    p = ProjectCreate(name="Demo", description="A demo project")
    assert p.name == "Demo"
    assert p.description == "A demo project"


# ---------------------------------------------------------------------------
# ProjectResponse
# ---------------------------------------------------------------------------

def test_project_response_model_validate():
    class FakeProject:
        project_id = "proj-1"
        name = "Test"
        description = "Desc"
        created_at = NOW
        updated_at = NOW

    resp = ProjectResponse.model_validate(FakeProject())
    assert resp.project_id == "proj-1"
    assert resp.name == "Test"


def test_project_response_description_can_be_none():
    class FakeProject:
        project_id = "proj-2"
        name = "NullDesc"
        description = None
        created_at = NOW
        updated_at = NOW

    resp = ProjectResponse.model_validate(FakeProject())
    assert resp.description is None


# ---------------------------------------------------------------------------
# VisionConfigSchema
# ---------------------------------------------------------------------------

def test_vision_config_defaults():
    vc = VisionConfigSchema()
    assert vc.enabled is True
    assert vc.force_kind_by_slide is None
    assert vc.lang is None
    assert vc.min_confidence_for_specific_claims is None


def test_vision_config_partial():
    vc = VisionConfigSchema(enabled=False, lang="fr-FR")
    assert vc.enabled is False
    assert vc.lang == "fr-FR"


# ---------------------------------------------------------------------------
# JobCreate
# ---------------------------------------------------------------------------

def test_job_create_project_id_required():
    with pytest.raises(Exception):
        JobCreate()  # type: ignore[call-arg]


def test_job_create_optional_fields():
    jc = JobCreate(project_id="proj-1")
    assert jc.requested_language is None
    assert jc.config is None


def test_job_create_with_config():
    jc = JobCreate(project_id="p1", config={"vision": {"enabled": False}})
    assert jc.config == {"vision": {"enabled": False}}


# ---------------------------------------------------------------------------
# JobResponse
# ---------------------------------------------------------------------------

def _job_response_data(**kwargs):
    defaults = dict(
        job_id="job-1",
        project_id="proj-1",
        status=JobStatus.QUEUED,
        input_file_path=None,
        requested_language=None,
        error_message=None,
        output_variants=None,
        variant_statuses=None,
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(kwargs)
    return defaults


def test_job_response_basic():
    jr = JobResponse(**_job_response_data())
    assert jr.job_id == "job-1"
    assert jr.status == JobStatus.QUEUED


def test_job_response_status_done():
    jr = JobResponse(**_job_response_data(status=JobStatus.DONE))
    assert jr.status == JobStatus.DONE


def test_job_response_output_variants_optional():
    jr = JobResponse(**_job_response_data())
    assert jr.output_variants is None
    assert jr.variant_statuses is None


def test_job_response_with_variants():
    variants = [{"id": "en", "lang": "en-US", "voice_id": "v1", "notes_translate": False}]
    statuses = [{"variant_id": "en", "status": "ready", "output_url": "/path/to/video.mp4"}]
    jr = JobResponse(**_job_response_data(output_variants=variants, variant_statuses=statuses))
    assert len(jr.output_variants) == 1
    assert jr.variant_statuses[0]["variant_id"] == "en"


# ---------------------------------------------------------------------------
# OutputVariantSchema + VariantStatusSchema
# ---------------------------------------------------------------------------

def test_output_variant_schema():
    ov = OutputVariantSchema(id="hi", lang="hi-IN", voice_id="voice_hi", notes_translate=True)
    assert ov.id == "hi"
    assert ov.notes_translate is True


def test_variant_status_schema_output_url_optional():
    vs = VariantStatusSchema(variant_id="en", status="pending")
    assert vs.output_url is None


def test_variant_status_schema_ready():
    vs = VariantStatusSchema(variant_id="en", status="ready", output_url="/jobs/x/output/en/final.mp4")
    assert vs.status == "ready"
    assert "final.mp4" in vs.output_url
