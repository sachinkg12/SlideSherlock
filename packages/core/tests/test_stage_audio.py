"""Unit tests for stages/audio.py (AudioStage)."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from pipeline import PipelineContext, StageResult


def _make_ctx(tmp_path=None):
    ctx = PipelineContext(
        job_id="job-audio-test",
        project_id="proj-1",
        minio_client=MagicMock(),
        db_session=MagicMock(),
        config={},
        temp_dir=str(tmp_path) if tmp_path else "/tmp",
    )
    ctx.variant = {"id": "en", "lang": "en-US", "voice_id": "default_en"}
    ctx.script_prefix = "jobs/job-audio-test/script/en/"
    ctx.slide_count = 2
    ctx.unified_by_slide = {1: {}, 2: {}}
    ctx.evidence_index = {"evidence_items": [], "sources": []}
    ctx.narration_entries_override = None
    ctx.llm_provider = MagicMock()
    return ctx


def test_audio_stage_name():
    from stages.audio import AudioStage
    assert AudioStage.name == "audio"


def test_audio_skips_when_deps_missing():
    """Returns skipped when run_audio_prepare or AudioConfig is None."""
    from stages.audio import AudioStage

    ctx = _make_ctx()
    mock_models = MagicMock(Artifact=MagicMock())

    with patch("stages.audio.run_audio_prepare", None), \
         patch("stages.audio.AudioConfig", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = AudioStage()
        result = stage.run(ctx)

    assert result.status == "skipped"
    assert "audio deps missing" in str(result.metrics.get("reason", ""))


def test_audio_result_is_ok_on_success(tmp_path):
    """Returns ok when audio_prepare runs without error."""
    from stages.audio import AudioStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.return_value = json.dumps({"notes": "", "slide_text": ""}).encode()
    ctx.minio_client.exists.return_value = False

    mock_config = MagicMock()
    mock_audio_config_cls = MagicMock()
    mock_audio_config_cls.from_env.return_value = mock_config

    narration_entries = [{"slide_index": 1, "narration_text": "Slide 1."}, {"slide_index": 2, "narration_text": "Slide 2."}]
    per_slide_audio = [("/tmp/slide_001.wav", 3.0), ("/tmp/slide_002.wav", 2.5)]
    narration_payload = {"slides": narration_entries}

    mock_run_audio = MagicMock(return_value=(narration_entries, per_slide_audio, narration_payload))

    mock_artifact_cls = MagicMock()
    mock_models = MagicMock(Artifact=mock_artifact_cls)

    with patch("stages.audio.AudioConfig", mock_audio_config_cls), \
         patch("stages.audio.run_audio_prepare", mock_run_audio), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = AudioStage()
        result = stage.run(ctx)

    assert result.status == "ok"


def test_audio_sets_narration_entries_on_ctx(tmp_path):
    """ctx.narration_entries is set after audio prepare runs."""
    from stages.audio import AudioStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.return_value = json.dumps({"notes": "Note", "slide_text": "Text"}).encode()
    ctx.minio_client.exists.return_value = False

    narration_entries = [{"slide_index": 1, "narration_text": "Here we go."}]
    per_slide_audio = [("/tmp/slide_001.wav", 4.0)]
    narration_payload = {}

    mock_audio_cfg = MagicMock()
    mock_audio_cfg_cls = MagicMock(from_env=MagicMock(return_value=mock_audio_cfg))
    mock_run_audio = MagicMock(return_value=(narration_entries, per_slide_audio, narration_payload))

    mock_models = MagicMock(Artifact=MagicMock())
    ctx.slide_count = 1

    with patch("stages.audio.AudioConfig", mock_audio_cfg_cls), \
         patch("stages.audio.run_audio_prepare", mock_run_audio), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = AudioStage()
        stage.run(ctx)

    assert ctx.narration_entries == narration_entries
    assert ctx.per_slide_audio_paths == ["/tmp/slide_001.wav"]
    assert ctx.per_slide_durations_dict == {1: 4.0}


def test_audio_builds_slides_notes_from_minio(tmp_path):
    """Stage fetches per-slide PPT JSON to build slides_notes_and_text."""
    from stages.audio import AudioStage

    ctx = _make_ctx(tmp_path)
    slide_payload = {"notes": "Speaker note", "slide_text": "Slide body"}
    ctx.minio_client.get.return_value = json.dumps(slide_payload).encode()
    ctx.minio_client.exists.return_value = False

    ctx.slide_count = 1

    narration_entries = [{"slide_index": 1, "narration_text": "Test"}]
    per_slide_audio = [("/tmp/s1.wav", 2.0)]

    mock_audio_cfg_cls = MagicMock(from_env=MagicMock(return_value=MagicMock()))
    mock_run_audio = MagicMock(return_value=(narration_entries, per_slide_audio, {}))
    mock_models = MagicMock(Artifact=MagicMock())

    with patch("stages.audio.AudioConfig", mock_audio_cfg_cls), \
         patch("stages.audio.run_audio_prepare", mock_run_audio), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = AudioStage()
        stage.run(ctx)

    assert ctx.slides_notes_and_text == [("Speaker note", "Slide body")]


def test_audio_handles_prepare_failure_gracefully(tmp_path):
    """Even if audio_prepare raises, stage returns ok (warn but continue)."""
    from stages.audio import AudioStage

    ctx = _make_ctx(tmp_path)
    ctx.minio_client.get.return_value = json.dumps({"notes": "", "slide_text": ""}).encode()

    mock_audio_cfg_cls = MagicMock(from_env=MagicMock(return_value=MagicMock()))
    mock_run_audio = MagicMock(side_effect=RuntimeError("TTS exploded"))
    mock_models = MagicMock(Artifact=MagicMock())

    with patch("stages.audio.AudioConfig", mock_audio_cfg_cls), \
         patch("stages.audio.run_audio_prepare", mock_run_audio), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = AudioStage()
        result = stage.run(ctx)

    assert result.status == "ok"


def test_audio_override_logging(tmp_path, capsys):
    """Presence of narration_entries_override triggers the override log path."""
    from stages.audio import AudioStage

    ctx = _make_ctx(tmp_path)
    ctx.narration_entries_override = [
        {"slide_index": 1, "narration_text": "Override text", "source_used": "ai_narrate"}
    ]
    ctx.minio_client.get.return_value = json.dumps({"notes": "", "slide_text": ""}).encode()
    ctx.minio_client.exists.return_value = False
    ctx.slide_count = 1

    narration_entries = [{"slide_index": 1, "narration_text": "Override text"}]
    per_slide_audio = [("/tmp/s1.wav", 3.0)]

    mock_audio_cfg_cls = MagicMock(from_env=MagicMock(return_value=MagicMock()))
    mock_run_audio = MagicMock(return_value=(narration_entries, per_slide_audio, {}))
    mock_models = MagicMock(Artifact=MagicMock())

    with patch("stages.audio.AudioConfig", mock_audio_cfg_cls), \
         patch("stages.audio.run_audio_prepare", mock_run_audio), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = AudioStage()
        stage.run(ctx)

    captured = capsys.readouterr()
    assert "narration_entries_override" in captured.out
