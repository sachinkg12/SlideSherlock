"""Unit tests for stages/video.py (VideoStage)."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch, mock_open
import pytest

from pipeline import PipelineContext, StageResult


def _make_ctx(tmp_path=None):
    ctx = PipelineContext(
        job_id="job-video-test",
        project_id="proj-1",
        minio_client=MagicMock(),
        db_session=MagicMock(),
        config={},
        temp_dir=str(tmp_path) if tmp_path else "/tmp",
    )
    ctx.variant = {"id": "en", "lang": "en-US"}
    ctx.script_prefix = "jobs/job-video-test/script/en/"
    ctx.timeline_prefix = "jobs/job-video-test/timing/en/"
    ctx.timeline_path_prefix = "jobs/job-video-test/timeline/en/"
    ctx.overlay_prefix = "jobs/job-video-test/overlays/en/"
    ctx.output_prefix = "jobs/job-video-test/output/en/"
    ctx.slide_count = 1
    ctx.slide_metadata = [{"width": 1280, "height": 720}]
    ctx.unified_by_slide = {1: {"nodes": [], "edges": []}}
    ctx.evidence_index = {"evidence_items": [], "sources": []}
    ctx.script_for_downstream = {"segments": [{"slide_index": 1, "text": "Slide 1.", "claim_id": "c1"}]}
    ctx.per_slide_durations_dict = {1: 3.0}
    ctx.per_slide_audio_paths = ["/tmp/slide_001.wav"]
    ctx.narration_entries = [{"slide_index": 1, "narration_text": "Slide 1."}]
    ctx.per_slide_notes_for_overlay = None
    ctx.coverage = {"pct_claims_with_evidence": 1.0, "pct_entities_grounded": 1.0, "pass": 1, "rewrite": 0, "remove": 0, "total_claims": 1}
    return ctx


def test_video_stage_name():
    from stages.video import VideoStage
    assert VideoStage.name == "video"


def test_video_skips_when_deps_missing():
    """Returns skipped when any critical dep is None."""
    from stages.video import VideoStage

    ctx = _make_ctx()

    with patch("stages.video.build_alignment", None), \
         patch("stages.video.build_timeline", None), \
         patch("stages.video.render_slide_with_overlay_mp4", None), \
         patch("stages.video.compose_video", None), \
         patch.dict("sys.modules", {"apps.api.models": MagicMock(), "models": MagicMock()}):
        stage = VideoStage()
        result = stage.run(ctx)

    assert result.status == "skipped"
    assert "video deps missing" in str(result.metrics.get("reason", ""))


def test_video_runs_and_returns_ok(tmp_path):
    """Happy path: alignment + timeline + overlays + compose all succeed."""
    from stages.video import VideoStage

    ctx = _make_ctx(tmp_path)

    mock_alignment = {"slides": [{"slide_index": 1, "t_start": 0, "t_end": 3.0}]}
    mock_timeline = {"actions": [{"slide_index": 1, "t_start": 0, "t_end": 3.0, "type": "show"}]}

    final_mp4 = tmp_path / "final_en.mp4"
    final_mp4.write_bytes(b"MP4DATA")
    overlay_mp4 = tmp_path / "slide_001_en_overlay.mp4"
    overlay_mp4.write_bytes(b"OVERLAY")

    ctx.minio_client.get.side_effect = lambda key: (
        b"PNG_DATA" if "render/slides" in key else
        json.dumps({"title": "Test Deck", "slide_text": "Test Deck"}).encode() if "ppt/slide_001" in key else
        b"{}"
    )
    ctx.minio_client.put.return_value = None

    mock_artifact_cls = MagicMock()
    mock_models = MagicMock(Artifact=mock_artifact_cls)

    with patch("stages.video.build_alignment", return_value=mock_alignment), \
         patch("stages.video.build_timeline", return_value=mock_timeline), \
         patch("stages.video.render_slide_with_overlay_mp4", MagicMock()), \
         patch("stages.video.compose_video", MagicMock()), \
         patch("stages.video._get_mp4_duration", return_value=3.0), \
         patch("stages.video.VideoConfig", None), \
         patch("stages.video.OnScreenNotesConfig", None), \
         patch("stages.video.resolve_notes_font_for_variant", None), \
         patch("stages.video.generate_srt_from_narration_and_alignment", None), \
         patch("stages.video.run_doctor", None), \
         patch("stages.video.get_current_preset", None), \
         patch("builtins.open", mock_open(read_data=b"MP4DATA")), \
         patch("os.path.exists", return_value=True), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = VideoStage()
        result = stage.run(ctx)

    assert result.status == "ok"
    assert "total_duration" in result.metrics


def test_video_returns_failed_on_exception(tmp_path):
    """Returns failed status when compose raises an unhandled exception."""
    from stages.video import VideoStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.return_value = b"PNG_DATA"

    mock_models = MagicMock(Artifact=MagicMock())

    from exceptions import MediaProcessingError
    with patch("stages.video.build_alignment", side_effect=MediaProcessingError("crash")), \
         patch("stages.video.build_timeline", MagicMock()), \
         patch("stages.video.render_slide_with_overlay_mp4", MagicMock()), \
         patch("stages.video.compose_video", MagicMock()), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = VideoStage()
        result = stage.run(ctx)

    assert result.status == "failed"
    assert "error" in result.metrics


def test_video_writes_summary_and_diagnostics(tmp_path):
    """summary.json and diagnostics.json are uploaded to minio."""
    from stages.video import VideoStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.side_effect = lambda key: (
        b"PNG_DATA" if "render/slides" in key else
        json.dumps({"title": "Deck", "slide_text": "Deck"}).encode() if "ppt/slide_001" in key else
        b"{}"
    )
    ctx.minio_client.put.return_value = None

    mock_models = MagicMock(Artifact=MagicMock())

    with patch("stages.video.build_alignment", return_value={"slides": []}), \
         patch("stages.video.build_timeline", return_value={"actions": []}), \
         patch("stages.video.render_slide_with_overlay_mp4", MagicMock()), \
         patch("stages.video.compose_video", MagicMock()), \
         patch("stages.video._get_mp4_duration", return_value=3.0), \
         patch("stages.video.VideoConfig", None), \
         patch("stages.video.OnScreenNotesConfig", None), \
         patch("stages.video.resolve_notes_font_for_variant", None), \
         patch("stages.video.generate_srt_from_narration_and_alignment", None), \
         patch("stages.video.run_doctor", None), \
         patch("stages.video.get_current_preset", None), \
         patch("builtins.open", mock_open(read_data=b"MP4")), \
         patch("os.path.exists", return_value=True), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = VideoStage()
        stage.run(ctx)

    put_keys = [c.args[0] for c in ctx.minio_client.put.call_args_list]
    assert any("summary.json" in k for k in put_keys)
    assert any("diagnostics.json" in k for k in put_keys)


def test_get_mp4_duration_returns_float():
    """_get_mp4_duration returns a float (0.0 on subprocess error)."""
    from stages.video import _get_mp4_duration

    with patch("stages.video._subprocess.run", side_effect=Exception("no ffprobe")):
        dur = _get_mp4_duration("/nonexistent.mp4")

    assert isinstance(dur, float)
    assert dur == 0.0


def test_pad_audio_to_duration_returns_original_on_failure(tmp_path):
    """_pad_audio_to_duration returns original path if ffmpeg call fails."""
    from stages.video import _pad_audio_to_duration

    audio = str(tmp_path / "slide_001.wav")
    open(audio, "wb").close()

    with patch("stages.video._subprocess.run", side_effect=Exception("ffmpeg error")):
        result = _pad_audio_to_duration(audio, 5.0, str(tmp_path), 1)

    assert result == audio
