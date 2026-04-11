"""Unit tests for stages/evidence.py (EvidenceStage)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from pipeline import PipelineContext, StageResult


def _make_ctx(with_slides=True):
    ctx = PipelineContext(
        job_id="job-evidence-test",
        project_id="proj-1",
        minio_client=MagicMock(),
        db_session=MagicMock(),
        config={},
        temp_dir="/tmp",
    )
    ctx.vision_enabled = False
    ctx.vision_config = {"lang": "en-US"}
    ctx.image_kinds = None

    if with_slides:
        ctx.slides_data = [
            {"slide_index": 1, "slide_text": "Slide 1", "notes": ""},
            {"slide_index": 2, "slide_text": "Slide 2", "notes": "Note"},
        ]
        ctx.images_index = {"images": []}
    else:
        ctx.slides_data = []
        ctx.images_index = None

    return ctx


def test_evidence_stage_name():
    from stages.evidence import EvidenceStage
    assert EvidenceStage.name == "evidence"


def test_evidence_skips_when_no_slides_data():
    """Returns skipped when ctx.slides_data is empty."""
    from stages.evidence import EvidenceStage

    ctx = _make_ctx(with_slides=False)

    stage = EvidenceStage()
    result = stage.run(ctx)

    assert result.status == "skipped"
    assert "no slides_data" in str(result.metrics.get("reason", ""))


def test_evidence_runs_build_evidence_index():
    """build_evidence_index is called when available and slides exist."""
    from stages.evidence import EvidenceStage

    ctx = _make_ctx()
    mock_build = MagicMock()

    with patch("stages.evidence.build_evidence_index", mock_build), \
         patch("stages.evidence.run_photo_understand", None), \
         patch("stages.evidence.run_diagram_understand", None):
        stage = EvidenceStage()
        result = stage.run(ctx)

    mock_build.assert_called_once_with(
        job_id="job-evidence-test",
        project_id="proj-1",
        slides_data=ctx.slides_data,
        db_session=ctx.db_session,
        minio_client=ctx.minio_client,
        ppt_artifact_ids_by_slide=None,
        images_index=ctx.images_index,
    )
    assert result.status == "ok"


def test_evidence_returns_ok_when_no_build_dep():
    """Returns ok even when build_evidence_index is None."""
    from stages.evidence import EvidenceStage

    ctx = _make_ctx()

    with patch("stages.evidence.build_evidence_index", None), \
         patch("stages.evidence.run_photo_understand", None), \
         patch("stages.evidence.run_diagram_understand", None):
        stage = EvidenceStage()
        result = stage.run(ctx)

    assert result.status == "ok"


def test_evidence_runs_photo_understand_when_vision_enabled():
    """run_photo_understand is called when vision is enabled and images exist."""
    from stages.evidence import EvidenceStage

    ctx = _make_ctx()
    ctx.vision_enabled = True
    ctx.images_index = {"images": [{"image_id": "img1", "slide_index": 1}]}
    ctx.image_kinds = {"img1": "PHOTO"}

    mock_photo = MagicMock(return_value={"evidence_count": 1})

    with patch("stages.evidence.build_evidence_index", MagicMock()), \
         patch("stages.evidence.run_photo_understand", mock_photo), \
         patch("stages.evidence.run_diagram_understand", None):
        stage = EvidenceStage()
        result = stage.run(ctx)

    mock_photo.assert_called_once()
    assert result.status == "ok"


def test_evidence_runs_diagram_understand_when_vision_enabled():
    """run_diagram_understand is called when vision is enabled and images exist."""
    from stages.evidence import EvidenceStage

    ctx = _make_ctx()
    ctx.vision_enabled = True
    ctx.images_index = {"images": [{"image_id": "img1", "slide_index": 1}]}
    ctx.image_kinds = {"img1": "DIAGRAM"}

    mock_diagram = MagicMock(return_value={"evidence_count": 2})

    with patch("stages.evidence.build_evidence_index", MagicMock()), \
         patch("stages.evidence.run_photo_understand", None), \
         patch("stages.evidence.run_diagram_understand", mock_diagram):
        stage = EvidenceStage()
        result = stage.run(ctx)

    mock_diagram.assert_called_once()
    assert result.status == "ok"


def test_evidence_skips_photo_when_vision_disabled():
    """run_photo_understand is NOT called when vision_enabled is False."""
    from stages.evidence import EvidenceStage

    ctx = _make_ctx()
    ctx.vision_enabled = False
    ctx.images_index = {"images": [{"image_id": "img1"}]}
    ctx.image_kinds = {"img1": "PHOTO"}

    mock_photo = MagicMock(return_value={"evidence_count": 1})

    with patch("stages.evidence.build_evidence_index", MagicMock()), \
         patch("stages.evidence.run_photo_understand", mock_photo), \
         patch("stages.evidence.run_diagram_understand", None):
        stage = EvidenceStage()
        stage.run(ctx)

    mock_photo.assert_not_called()


def test_evidence_photo_failure_does_not_crash():
    """If run_photo_understand raises, stage still returns ok."""
    from stages.evidence import EvidenceStage

    ctx = _make_ctx()
    ctx.vision_enabled = True
    ctx.images_index = {"images": [{"image_id": "img1"}]}
    ctx.image_kinds = {"img1": "PHOTO"}

    with patch("stages.evidence.build_evidence_index", MagicMock()), \
         patch("stages.evidence.run_photo_understand", MagicMock(side_effect=RuntimeError("Vision failure"))), \
         patch("stages.evidence.run_diagram_understand", None):
        stage = EvidenceStage()
        result = stage.run(ctx)

    assert result.status == "ok"


def test_evidence_diagram_failure_does_not_crash():
    """If run_diagram_understand raises, stage still returns ok."""
    from stages.evidence import EvidenceStage

    ctx = _make_ctx()
    ctx.vision_enabled = True
    ctx.images_index = {"images": [{"image_id": "img2"}]}
    ctx.image_kinds = {"img2": "DIAGRAM"}

    with patch("stages.evidence.build_evidence_index", MagicMock()), \
         patch("stages.evidence.run_photo_understand", None), \
         patch("stages.evidence.run_diagram_understand", MagicMock(side_effect=RuntimeError("Diagram fail"))):
        stage = EvidenceStage()
        result = stage.run(ctx)

    assert result.status == "ok"
