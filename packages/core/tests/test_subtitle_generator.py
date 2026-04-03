"""Unit tests for SRT subtitle generation."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from subtitle_generator import generate_srt, generate_srt_from_narration_and_alignment


def test_generate_srt_basic():
    """generate_srt produces valid SRT format."""
    texts = ["First slide narration.", "Second slide text."]
    durations = [2.5, 3.0]
    srt = generate_srt(texts, durations)
    assert "1\n" in srt
    assert "00:00:00,000 --> 00:00:02,500" in srt
    assert "First slide narration." in srt
    assert "2\n" in srt
    assert "00:00:02,500 --> 00:00:05,500" in srt
    assert "Second slide text." in srt


def test_generate_srt_with_offset():
    """Offset shifts all timestamps."""
    texts = ["Only slide"]
    durations = [2.0]
    srt = generate_srt(texts, durations, offset_seconds=5.0)
    assert "00:00:05,000 --> 00:00:07,000" in srt


def test_generate_srt_from_narration():
    """generate_srt_from_narration_and_alignment uses narration slides and per_slide_durations."""
    narration_slides = [
        {"slide_index": 1, "narration_text": "Slide one.", "source_used": "notes"},
        {"slide_index": 2, "narration_text": "Slide two.", "source_used": "llm"},
    ]
    per_slide_durations = {1: 2.0, 2: 3.0}
    srt = generate_srt_from_narration_and_alignment(
        narration_slides, per_slide_durations, slide_count=2, offset_seconds=0
    )
    assert "Slide one." in srt
    assert "Slide two." in srt
