"""
Unit tests for audio_prepare stage (Fig3 step 14).
- Supplied audio: when mode=use_supplied and per-slide files exist, use them (no TTS).
- Generated: when mode=generate or supplied missing, build narration_per_slide and synthesize.
- Artifacts: script/narration_per_slide.json, audio/slide_{i}.wav, timing/slide_{i}_duration.json.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from audio_config import AudioConfig, AUDIO_MODE_USE_SUPPLIED, AUDIO_MODE_GENERATE
from audio_prepare import (
    _check_supplied_audio_exists,
    run_audio_prepare,
    AUDIO_OUTPUT_PREFIX,
    TIMING_PREFIX,
    SCRIPT_NARRATION,
)


def test_check_supplied_audio_exists_all_present():
    """When all slide_001.wav .. slide_N.wav exist, return (True, list of paths)."""
    minio = MagicMock()
    minio.exists.side_effect = lambda key: "slide_001" in key or "slide_002" in key
    all_exist, paths = _check_supplied_audio_exists(minio, "job1", 2)
    assert all_exist is True
    assert len(paths) == 2
    assert "slide_001" in paths[0]
    assert "slide_002" in paths[1]


def test_check_supplied_audio_exists_mp3():
    """When slide_001.mp3 exists (no wav), still count as present."""
    minio = MagicMock()
    call_count = [0]

    def exists(key):
        call_count[0] += 1
        if "slide_001" in key and ".mp3" in key:
            return True
        if "slide_002" in key and ".wav" in key:
            return True
        return False

    minio.exists.side_effect = exists
    all_exist, paths = _check_supplied_audio_exists(minio, "job1", 2)
    assert all_exist is True
    assert len(paths) == 2
    assert paths[0].endswith(".mp3")
    assert paths[1].endswith(".wav")


def test_check_supplied_audio_exists_missing():
    """When any slide has no audio file, return (False, [])."""
    minio = MagicMock()
    minio.exists.return_value = False
    all_exist, paths = _check_supplied_audio_exists(minio, "job1", 3)
    assert all_exist is False
    assert paths == []


def test_check_supplied_audio_exists_partial_missing():
    """When slide_001 exists but slide_002 does not, return (False, [])."""
    minio = MagicMock()
    minio.exists.side_effect = lambda key: "slide_001" in key
    all_exist, paths = _check_supplied_audio_exists(minio, "job1", 2)
    assert all_exist is False
    assert paths == []


def test_run_audio_prepare_use_supplied_no_tts():
    """When mode=use_supplied and all supplied audio exist, use user_audio and do not call TTS."""
    minio = MagicMock()
    minio.exists.side_effect = lambda key: "input/audio" in key and (
        "slide_001" in key or "slide_002" in key
    )
    minio.get.return_value = b"\x00\x00"
    config = AudioConfig(
        mode=AUDIO_MODE_USE_SUPPLIED,
        voice_provider="local",
        loudness_normalize=True,
    )
    slides_notes_and_text = [("Notes one.", "Text one"), ("Notes two.", "Text two")]
    unified_graphs = {1: {}, 2: {}}
    tts_provider = MagicMock()

    def fake_process_simple(in_path, out_path, **kwargs):
        with open(out_path, "wb") as f:
            f.write(b"\x00\x00")
        return 2.0

    with tempfile.TemporaryDirectory() as tmp:
        with patch("audio_processor.process_audio_simple", side_effect=fake_process_simple):
            entries, per_slide_audio, payload = run_audio_prepare(
                job_id="job1",
                slide_count=2,
                minio_client=minio,
                temp_dir=tmp,
                config=config,
                slides_notes_and_text=slides_notes_and_text,
                unified_graphs_by_slide=unified_graphs,
                tts_provider=tts_provider,
            )
    assert len(entries) == 2
    assert all(e["source_used"] == "user_audio" for e in entries)
    assert all(e["word_count"] == 0 for e in entries)
    tts_provider.synthesize.assert_not_called()
    assert len(per_slide_audio) == 2
    assert payload["job_id"] == "job1"
    assert len(payload["slides"]) == 2
    put_calls = [c[0][0] for c in minio.put.call_args_list]
    assert any(SCRIPT_NARRATION in k for k in put_calls)
    assert sum(1 for k in put_calls if f"{AUDIO_OUTPUT_PREFIX}/slide_" in k) == 2
    assert (
        sum(1 for k in put_calls if f"{TIMING_PREFIX}/slide_" in k and "_duration.json" in k) == 2
    )


def test_run_audio_prepare_generate_uses_tts():
    """When mode=generate, build narration_per_slide and call TTS; artifacts have source_used from narration."""
    minio = MagicMock()
    minio.exists.return_value = False
    config = AudioConfig(
        mode=AUDIO_MODE_GENERATE,
        voice_provider="local",
        loudness_normalize=True,
    )
    slides_notes_and_text = [
        ("Speaker notes with enough words for slide one.", "Title"),
        ("", "Slide two content with several words."),
    ]
    unified_graphs = {1: {}, 2: {}}

    def fake_synthesize(text, path, **kwargs):
        with open(path, "wb") as f:
            f.write(b"\x00\x00")
        return 2.5

    mock_tts = MagicMock()
    mock_tts.synthesize.side_effect = fake_synthesize

    def fake_process_simple(in_path, out_path, **kwargs):
        with open(out_path, "wb") as f:
            f.write(b"\x00\x00")
        return 2.5

    with tempfile.TemporaryDirectory() as tmp:
        with patch("audio_processor.process_audio_simple", side_effect=fake_process_simple):
            entries, per_slide_audio, payload = run_audio_prepare(
                job_id="job2",
                slide_count=2,
                minio_client=minio,
                temp_dir=tmp,
                config=config,
                slides_notes_and_text=slides_notes_and_text,
                unified_graphs_by_slide=unified_graphs,
                tts_provider=mock_tts,
            )
    assert len(entries) == 2
    assert entries[0]["source_used"] == "notes"
    assert entries[1]["source_used"] in ("slide_and_graph", "mixed", "llm")
    assert entries[0]["word_count"] > 0
    mock_tts.synthesize.assert_called()
    assert len(per_slide_audio) == 2
    assert payload["schema_version"] == "1.0"
    assert payload["job_id"] == "job2"
    assert all(
        "slide_index" in s and "narration_text" in s and "source_used" in s and "word_count" in s
        for s in payload["slides"]
    )


def test_run_audio_prepare_artifact_narration_structure():
    """narration_per_slide.json (via put) contains slide_index, narration_text, source_used, word_count."""
    minio = MagicMock()
    minio.exists.return_value = False
    config = AudioConfig(mode=AUDIO_MODE_GENERATE, voice_provider="local", loudness_normalize=False)
    slides_notes_and_text = [("Valid speaker notes with enough words here.", "Title")]
    unified_graphs = {1: {}}

    def fake_synth(text, path, **kwargs):
        with open(path, "wb") as f:
            f.write(b"\x00")
        return 1.0

    mock_tts = MagicMock()
    mock_tts.synthesize.side_effect = fake_synth

    def fake_process(in_path, out_path, **kwargs):
        with open(out_path, "wb") as f:
            f.write(b"\x00")
        return 1.0

    with tempfile.TemporaryDirectory() as tmp:
        with patch("audio_processor.process_audio_simple", side_effect=fake_process):
            run_audio_prepare(
                job_id="job3",
                slide_count=1,
                minio_client=minio,
                temp_dir=tmp,
                config=config,
                slides_notes_and_text=slides_notes_and_text,
                unified_graphs_by_slide=unified_graphs,
                tts_provider=mock_tts,
            )
    narration_put = next(c for c in minio.put.call_args_list if SCRIPT_NARRATION in c[0][0])
    key, data, _ = narration_put[0][0], narration_put[0][1], narration_put[0][2]
    obj = json.loads(data.decode("utf-8"))
    assert obj["job_id"] == "job3"
    assert len(obj["slides"]) == 1
    slide = obj["slides"][0]
    assert "slide_index" in slide
    assert "narration_text" in slide
    assert "source_used" in slide
    assert "word_count" in slide


def test_run_audio_prepare_artifact_duration_structure():
    """timing/slide_{i}_duration.json contains audio_duration_seconds, fallback_duration_seconds."""
    minio = MagicMock()
    minio.exists.return_value = False
    config = AudioConfig(mode=AUDIO_MODE_GENERATE, voice_provider="local", loudness_normalize=False)
    slides_notes_and_text = [("Notes with enough words for this slide.", "T")]
    unified_graphs = {1: {}}

    def fake_synth(text, path, **kwargs):
        with open(path, "wb") as f:
            f.write(b"\x00")
        return 3.0

    mock_tts = MagicMock()
    mock_tts.synthesize.side_effect = fake_synth

    def fake_process(in_path, out_path, **kwargs):
        with open(out_path, "wb") as f:
            f.write(b"\x00")
        return 3.14

    with tempfile.TemporaryDirectory() as tmp:
        with patch("audio_processor.process_audio_simple", side_effect=fake_process):
            run_audio_prepare(
                job_id="job4",
                slide_count=1,
                minio_client=minio,
                temp_dir=tmp,
                config=config,
                slides_notes_and_text=slides_notes_and_text,
                unified_graphs_by_slide=unified_graphs,
                tts_provider=mock_tts,
            )
    duration_puts = [
        c
        for c in minio.put.call_args_list
        if f"{TIMING_PREFIX}/slide_" in c[0][0] and "_duration.json" in c[0][0]
    ]
    assert len(duration_puts) == 1
    key, data = duration_puts[0][0][0], duration_puts[0][0][1]
    obj = json.loads(data.decode("utf-8"))
    assert "audio_duration_seconds" in obj
    assert "fallback_duration_seconds" in obj
    assert obj["slide_index"] == 1
    assert obj["audio_duration_seconds"] == 3.14
    assert obj["fallback_duration_seconds"] == 3.14


def test_run_audio_prepare_supplied_missing_falls_back_to_generate():
    """When mode=use_supplied but not all files exist, fall back to generate (TTS)."""
    minio = MagicMock()
    minio.exists.return_value = False
    config = AudioConfig(
        mode=AUDIO_MODE_USE_SUPPLIED,
        voice_provider="local",
        loudness_normalize=True,
    )
    slides_notes_and_text = [("Enough speaker notes for narration.", "T")]
    unified_graphs = {1: {}}

    def fake_synth(text, path, **kwargs):
        with open(path, "wb") as f:
            f.write(b"\x00")
        return 2.0

    mock_tts = MagicMock()
    mock_tts.synthesize.side_effect = fake_synth

    def fake_process(in_path, out_path, **kwargs):
        with open(out_path, "wb") as f:
            f.write(b"\x00")
        return 2.0

    with tempfile.TemporaryDirectory() as tmp:
        with patch("audio_processor.process_audio_simple", side_effect=fake_process):
            entries, _, _ = run_audio_prepare(
                job_id="job5",
                slide_count=1,
                minio_client=minio,
                temp_dir=tmp,
                config=config,
                slides_notes_and_text=slides_notes_and_text,
                unified_graphs_by_slide=unified_graphs,
                tts_provider=mock_tts,
            )
    assert entries[0]["source_used"] == "notes"
    mock_tts.synthesize.assert_called_once()
