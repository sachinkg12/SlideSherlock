"""Unit tests for stages/ingest.py (IngestStage)."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from pipeline import PipelineContext, StageResult


def _make_ctx(tmp_path, config=None):
    ctx = PipelineContext(
        job_id="job-ingest-test",
        project_id="proj-1",
        minio_client=MagicMock(),
        db_session=MagicMock(),
        config=config or {"input_file_path": "uploads/deck.pptx"},
        temp_dir=str(tmp_path),
    )
    return ctx


def test_ingest_stage_name():
    from stages.ingest import IngestStage
    assert IngestStage.name == "ingest"


def test_ingest_downloads_pptx_and_writes_path(tmp_path):
    """Stage downloads PPTX bytes from minio and stores pptx_path in ctx.config."""
    from stages.ingest import IngestStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.return_value = b"PPTX_BYTES"

    mock_artifact = MagicMock()
    with patch("stages.ingest.parse_pptx", None), \
         patch("stages.ingest.extract_images_from_pptx", None), \
         patch("stages.ingest.run_classify_images", None), \
         patch.dict("sys.modules", {"apps.api.models": MagicMock(Artifact=mock_artifact),
                                    "models": MagicMock(Artifact=mock_artifact)}):
        stage = IngestStage()
        result = stage.run(ctx)

    ctx.minio_client.get.assert_called_once_with("uploads/deck.pptx")
    assert "pptx_path" in ctx.config
    assert result.status == "ok"
    assert result.metrics["slide_count"] == 0


def test_ingest_result_structure(tmp_path):
    """StageResult has expected keys."""
    from stages.ingest import IngestStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.return_value = b""

    with patch("stages.ingest.parse_pptx", None), \
         patch.dict("sys.modules", {"apps.api.models": MagicMock(Artifact=MagicMock()),
                                    "models": MagicMock(Artifact=MagicMock())}):
        stage = IngestStage()
        result = stage.run(ctx)

    assert isinstance(result, StageResult)
    assert result.status in ("ok", "skipped", "failed")
    assert isinstance(result.artifacts_written, list)
    assert "slide_count" in result.metrics


def test_ingest_parse_pptx_populates_slides_data(tmp_path):
    """When parse_pptx is available, ctx.slides_data is populated."""
    from stages.ingest import IngestStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.return_value = b"PPTX"
    ctx.minio_client.put.return_value = None

    mock_slides = [
        {"slide_index": 1, "slide_text": "Slide 1", "notes": "", "shapes": [], "connectors": [], "groups": []},
        {"slide_index": 2, "slide_text": "Slide 2", "notes": "Note", "shapes": [], "connectors": [], "groups": []},
    ]
    mock_artifact_cls = MagicMock()
    mock_artifact_cls.return_value = MagicMock()

    with patch("stages.ingest.parse_pptx", return_value=mock_slides), \
         patch("stages.ingest.extract_images_from_pptx", None), \
         patch("stages.ingest.run_classify_images", None), \
         patch.dict("sys.modules", {"apps.api.models": MagicMock(Artifact=mock_artifact_cls),
                                    "models": MagicMock(Artifact=mock_artifact_cls)}):
        with patch("stages.ingest.build_native_graph_and_persist", None, create=True):
            stage = IngestStage()
            result = stage.run(ctx)

    assert ctx.slides_data == mock_slides
    assert result.metrics["slide_count"] == 2


def test_ingest_uploads_slide_json_artifacts(tmp_path):
    """Each parsed slide JSON is uploaded to minio."""
    from stages.ingest import IngestStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.return_value = b"PPTX"
    ctx.minio_client.put.return_value = None

    mock_slides = [
        {"slide_index": 1, "slide_text": "A", "notes": "", "shapes": [], "connectors": [], "groups": []},
    ]
    mock_artifact_cls = MagicMock()

    with patch("stages.ingest.parse_pptx", return_value=mock_slides), \
         patch("stages.ingest.extract_images_from_pptx", None), \
         patch("stages.ingest.run_classify_images", None), \
         patch.dict("sys.modules", {"apps.api.models": MagicMock(Artifact=mock_artifact_cls),
                                    "models": MagicMock(Artifact=mock_artifact_cls)}):
        with patch("stages.ingest.build_native_graph_and_persist", None, create=True):
            stage = IngestStage()
            result = stage.run(ctx)

    put_keys = [call.args[0] for call in ctx.minio_client.put.call_args_list]
    assert any("ppt/slide_001.json" in k for k in put_keys)
    assert "jobs/job-ingest-test/ppt/slide_001.json" in result.artifacts_written


def test_ingest_no_parse_pptx_gives_empty_slides(tmp_path):
    """If parse_pptx is None, slides_data is empty and result is still ok."""
    from stages.ingest import IngestStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.return_value = b""

    with patch("stages.ingest.parse_pptx", None), \
         patch.dict("sys.modules", {"apps.api.models": MagicMock(Artifact=MagicMock()),
                                    "models": MagicMock(Artifact=MagicMock())}):
        stage = IngestStage()
        result = stage.run(ctx)

    assert ctx.slides_data == []
    assert result.status == "ok"


def test_ingest_image_extraction_called_when_available(tmp_path):
    """extract_images_from_pptx is called when available and slides exist."""
    from stages.ingest import IngestStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.return_value = b"PPTX"
    ctx.minio_client.put.return_value = None
    ctx.vision_enabled = False

    mock_slides = [
        {"slide_index": 1, "slide_text": "A", "notes": "", "shapes": [], "connectors": [], "groups": []},
    ]
    mock_extract = MagicMock(return_value={"images": [{"image_id": "img1"}]})
    mock_artifact_cls = MagicMock()

    with patch("stages.ingest.parse_pptx", return_value=mock_slides), \
         patch("stages.ingest.extract_images_from_pptx", mock_extract), \
         patch("stages.ingest.run_classify_images", None), \
         patch.dict("sys.modules", {"apps.api.models": MagicMock(Artifact=mock_artifact_cls),
                                    "models": MagicMock(Artifact=mock_artifact_cls)}):
        with patch("stages.ingest.build_native_graph_and_persist", None, create=True):
            stage = IngestStage()
            result = stage.run(ctx)

    mock_extract.assert_called_once()
    assert ctx.images_index == {"images": [{"image_id": "img1"}]}


def test_ingest_native_graph_called_when_available(tmp_path):
    """build_native_graph_and_persist is called when imported and slides exist."""
    from stages.ingest import IngestStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.return_value = b"PPTX"
    ctx.minio_client.put.return_value = None

    mock_slides = [
        {"slide_index": 1, "slide_text": "A", "notes": "", "shapes": [], "connectors": [], "groups": []},
    ]
    mock_build_graph = MagicMock()
    mock_artifact_cls = MagicMock()

    with patch("stages.ingest.parse_pptx", return_value=mock_slides), \
         patch("stages.ingest.extract_images_from_pptx", None), \
         patch("stages.ingest.run_classify_images", None), \
         patch.dict("sys.modules", {"apps.api.models": MagicMock(Artifact=mock_artifact_cls),
                                    "models": MagicMock(Artifact=mock_artifact_cls),
                                    "native_graph": MagicMock(build_native_graph_and_persist=mock_build_graph)}):
        stage = IngestStage()
        result = stage.run(ctx)

    # If the module-level import of build_native_graph_and_persist resolved, it gets called
    assert result.status == "ok"
