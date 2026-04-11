"""
Unit tests for alignment.py: estimate_duration_seconds, build_alignment, timing modes.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from alignment import (
    build_alignment,
    estimate_duration_seconds,
    DEFAULT_WPM,
    MIN_SEGMENT_DURATION,
    MAX_SEGMENT_DURATION,
)


# --- estimate_duration_seconds ---

def test_empty_text_returns_min_duration():
    """Empty string -> MIN_SEGMENT_DURATION."""
    assert estimate_duration_seconds("") == MIN_SEGMENT_DURATION


def test_whitespace_only_returns_min_duration():
    """Whitespace-only text has zero words -> MIN_SEGMENT_DURATION."""
    assert estimate_duration_seconds("   ") == MIN_SEGMENT_DURATION


def test_single_word():
    """A single word is within [MIN, MAX] bounds."""
    dur = estimate_duration_seconds("hello")
    assert MIN_SEGMENT_DURATION <= dur <= MAX_SEGMENT_DURATION


def test_long_text_capped_at_max():
    """Very many words are capped at MAX_SEGMENT_DURATION."""
    many_words = " ".join(["word"] * 1000)
    dur = estimate_duration_seconds(many_words)
    assert dur == MAX_SEGMENT_DURATION


def test_duration_proportional_to_word_count():
    """More words -> longer duration (before hitting cap)."""
    short = estimate_duration_seconds("one two")
    longer = estimate_duration_seconds("one two three four five six")
    assert longer > short


def test_custom_wpm_affects_duration():
    """Slower WPM -> longer duration for same text."""
    text = "hello world"
    fast = estimate_duration_seconds(text, wpm=300)
    slow = estimate_duration_seconds(text, wpm=75)
    assert slow > fast


# --- build_alignment ---

def _script(segments):
    return {"segments": segments}


def _seg(claim_id="c1", slide_index=0, text="hello world"):
    return {"claim_id": claim_id, "slide_index": slide_index, "text": text}


def test_empty_segments_produces_valid_output():
    """No segments -> alignment with empty segments list."""
    result = build_alignment("job-1", _script([]))
    assert result["job_id"] == "job-1"
    assert result["schema_version"] == "1.0"
    assert result["segments"] == []
    assert result["total_duration_seconds"] == 0.0
    assert result["source"] == "estimated"


def test_estimated_mode_monotonic_timestamps():
    """Without timestamps or per_slide_durations, t_end increases monotonically."""
    segs = [
        _seg("c1", 0, "This is slide one content here."),
        _seg("c2", 0, "More content for slide one."),
        _seg("c3", 1, "Slide two starts now."),
    ]
    result = build_alignment("job-2", _script(segs))
    entries = result["segments"]
    for i in range(1, len(entries)):
        assert entries[i]["t_start"] >= entries[i - 1]["t_end"] - 0.001


def test_estimated_mode_segment_index_matches_position():
    """segment_index in each entry matches its position in the list."""
    segs = [_seg("c1"), _seg("c2"), _seg("c3")]
    result = build_alignment("job-3", _script(segs))
    for i, entry in enumerate(result["segments"]):
        assert entry["segment_index"] == i


def test_tts_timestamps_mode_uses_provided_times():
    """segment_timestamps are used as t_start/t_end directly."""
    segs = [_seg("c1", 0, "hello"), _seg("c2", 0, "world")]
    timestamps = [{"t_start": 0.0, "t_end": 2.5}, {"t_start": 2.5, "t_end": 5.0}]
    result = build_alignment("job-4", _script(segs), segment_timestamps=timestamps)
    assert result["source"] == "tts"
    assert result["segments"][0]["t_start"] == 0.0
    assert result["segments"][0]["t_end"] == 2.5
    assert result["segments"][1]["t_start"] == 2.5
    assert result["segments"][1]["t_end"] == 5.0


def test_per_slide_durations_mode_source_label():
    """per_slide_durations mode sets source to 'per_slide_audio'."""
    segs = [_seg("c1", 0, "hello world")]
    result = build_alignment("job-5", _script(segs), per_slide_durations={0: 5.0})
    assert result["source"] == "per_slide_audio"


def test_per_slide_durations_total_duration():
    """total_duration_seconds matches sum of per_slide_durations."""
    segs = [_seg("c1", 0, "a b c"), _seg("c2", 1, "d e f")]
    per_slide = {0: 4.0, 1: 6.0}
    result = build_alignment("job-6", _script(segs), per_slide_durations=per_slide)
    assert abs(result["total_duration_seconds"] - 10.0) < 0.01


def test_wpm_none_in_tts_mode():
    """wpm field is None in the output when segment_timestamps are used."""
    segs = [_seg("c1")]
    result = build_alignment("job-7", _script(segs), segment_timestamps=[{"t_start": 0, "t_end": 2}])
    assert result["wpm"] is None


def test_estimated_mode_wpm_is_recorded():
    """wpm is recorded in estimated mode."""
    result = build_alignment("job-8", _script([_seg("c1")]))
    assert result["wpm"] == DEFAULT_WPM


def test_claim_id_preserved_in_entry():
    """claim_id from the segment is preserved in the output entry."""
    segs = [_seg("my-claim-id", 0, "some text here")]
    result = build_alignment("job-9", _script(segs))
    assert result["segments"][0]["claim_id"] == "my-claim-id"


def test_duration_field_matches_t_end_minus_t_start():
    """duration == t_end - t_start (within rounding)."""
    segs = [_seg("c1", 0, "a few words here")]
    result = build_alignment("job-10", _script(segs))
    for entry in result["segments"]:
        expected = round(entry["t_end"] - entry["t_start"], 3)
        assert abs(entry["duration"] - expected) < 0.001


def test_constants():
    """Spot-check exported constants."""
    assert DEFAULT_WPM == 150
    assert MIN_SEGMENT_DURATION == 1.0
    assert MAX_SEGMENT_DURATION == 15.0
