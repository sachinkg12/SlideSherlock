"""Unit tests for stages/render.py (RenderStage)."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from pipeline import PipelineContext, StageResult


def _make_ctx(tmp_path):
    ctx = PipelineContext(
        job_id="job-render-test",
        project_id="proj-1",
        minio_client=MagicMock(),
        db_session=MagicMock(),
        config={"pptx_path": str(tmp_path / "input.pptx")},
        temp_dir=str(tmp_path),
    )
    ctx.vision_enabled = False
    ctx.vision_config = {"lang": "en-US"}
    return ctx


def _make_mock_slide(width=1280, height=720):
    """Create a minimal mock PIL image that saves to a BytesIO of real bytes."""
    from io import BytesIO
    slide = MagicMock()
    slide.size = (width, height)

    def fake_save(buf, format=None):
        buf.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)

    slide.save = fake_save
    return slide


def _run_render_happy_path(tmp_path, mock_slides, mock_models, mock_job, extra_patches=()):
    """Common helper: write real files and run RenderStage with necessary mocks."""
    from stages.render import RenderStage

    pptx = tmp_path / "input.pptx"
    pptx.write_bytes(b"FAKE_PPTX")
    pdf_path = tmp_path / "input.pdf"
    pdf_path.write_bytes(b"FAKE_PDF_CONTENT")

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.put.return_value = None
    ctx.db_session.query.return_value.filter.return_value.first.return_value = mock_job

    mock_ok = MagicMock(returncode=0, stderr="", stdout="")

    with patch("stages.render.subprocess.run", return_value=mock_ok), \
         patch("stages.render.convert_from_path", return_value=mock_slides), \
         patch("stages.render.build_output_variants", return_value=[{"id": "en"}]), \
         patch("stages.render.run_slide_caption_fallback", None), \
         patch("stages.render.write_vision_summary", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = RenderStage()
        result = stage.run(ctx)

    return ctx, result


def test_render_stage_name():
    from stages.render import RenderStage
    assert RenderStage.name == "render"


def test_render_runs_and_returns_ok(tmp_path):
    """Happy path: subprocess + pdf2image succeed, result is ok."""
    mock_slide = _make_mock_slide()
    mock_job = MagicMock(requested_language=None)
    mock_models = MagicMock(Artifact=MagicMock(), Job=MagicMock(return_value=mock_job))

    ctx, result = _run_render_happy_path(tmp_path, [mock_slide], mock_models, mock_job)

    assert result.status == "ok"
    assert result.metrics["slide_count"] == 1


def test_render_raises_if_libreoffice_fails(tmp_path):
    """If LibreOffice returns nonzero, stage raises Exception."""
    from stages.render import RenderStage

    pptx = tmp_path / "input.pptx"
    pptx.write_bytes(b"PPTX")

    ctx = _make_ctx(tmp_path)
    mock_fail = MagicMock(returncode=1, stderr="Conversion failed", stdout="")
    mock_models = MagicMock(Artifact=MagicMock(), Job=MagicMock())

    with patch("stages.render.subprocess.run", return_value=mock_fail), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = RenderStage()
        with pytest.raises(Exception, match="LibreOffice conversion failed"):
            stage.run(ctx)


def test_render_raises_if_pdf_not_created(tmp_path):
    """If PDF file isn't present after LibreOffice, exception is raised."""
    from stages.render import RenderStage

    pptx = tmp_path / "input.pptx"
    pptx.write_bytes(b"PPTX")

    ctx = _make_ctx(tmp_path)
    mock_ok = MagicMock(returncode=0, stderr="", stdout="")
    mock_models = MagicMock(Artifact=MagicMock(), Job=MagicMock())

    # Patch os.path.exists to return False only for the PDF check
    original_exists = os.path.exists
    def exists_except_pdf(path):
        if path.endswith(".pdf"):
            return False
        return original_exists(path)

    with patch("stages.render.subprocess.run", return_value=mock_ok), \
         patch("os.path.exists", side_effect=exists_except_pdf), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = RenderStage()
        with pytest.raises(Exception, match="PDF file not created"):
            stage.run(ctx)


def test_render_raises_if_pdf2image_unavailable(tmp_path):
    """If convert_from_path is None, raises an exception."""
    from stages.render import RenderStage

    pptx = tmp_path / "input.pptx"
    pptx.write_bytes(b"PPTX")
    pdf_path = tmp_path / "input.pdf"
    pdf_path.write_bytes(b"FAKE_PDF")

    ctx = _make_ctx(tmp_path)
    mock_ok = MagicMock(returncode=0)
    mock_models = MagicMock(Artifact=MagicMock(), Job=MagicMock())

    with patch("stages.render.subprocess.run", return_value=mock_ok), \
         patch("stages.render.convert_from_path", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = RenderStage()
        with pytest.raises(Exception, match="pdf2image not available"):
            stage.run(ctx)


def test_render_sets_ctx_attributes(tmp_path):
    """After run, ctx.slide_count, ctx.slide_metadata, ctx.slides_pil are populated."""
    mock_slide = _make_mock_slide(1920, 1080)
    mock_job = MagicMock(requested_language=None)
    mock_models = MagicMock(Artifact=MagicMock(), Job=MagicMock(return_value=mock_job))

    ctx, _ = _run_render_happy_path(tmp_path, [mock_slide], mock_models, mock_job)

    assert ctx.slide_count == 1
    assert len(ctx.slide_metadata) == 1
    assert ctx.slide_metadata[0]["width"] == 1920
    assert ctx.slide_metadata[0]["height"] == 1080


def test_render_uploads_manifest(tmp_path):
    """manifest.json is uploaded to minio."""
    mock_slide = _make_mock_slide()
    mock_job = MagicMock(requested_language=None)
    mock_models = MagicMock(Artifact=MagicMock(), Job=MagicMock(return_value=mock_job))

    ctx, result = _run_render_happy_path(tmp_path, [mock_slide], mock_models, mock_job)

    put_keys = [c.args[0] for c in ctx.minio_client.put.call_args_list]
    assert any("manifest.json" in k for k in put_keys)
    assert any("manifest.json" in p for p in result.artifacts_written)


def test_render_uploads_pdf_and_png(tmp_path):
    """PDF and PNG storage paths appear in artifacts_written."""
    mock_slide = _make_mock_slide()
    mock_job = MagicMock(requested_language=None)
    mock_models = MagicMock(Artifact=MagicMock(), Job=MagicMock(return_value=mock_job))

    ctx, result = _run_render_happy_path(tmp_path, [mock_slide], mock_models, mock_job)

    assert any("deck.pdf" in p for p in result.artifacts_written)
    assert any("slide_001.png" in p for p in result.artifacts_written)
