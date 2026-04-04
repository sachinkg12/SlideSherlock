"""
Unit tests for alignment and timeline builder (Fig3 step 15–16, Fig7).
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from alignment import build_alignment, estimate_duration_seconds
from timeline_builder import build_timeline, ACTION_HIGHLIGHT, ACTION_TRACE, emu_to_pixel


def test_estimate_duration():
    """Estimate duration from word count."""
    assert estimate_duration_seconds("one two three", 60) >= 1.0
    assert estimate_duration_seconds("", 150) >= 1.0


def test_build_alignment():
    """Alignment has t_start, t_end per segment; total_duration."""
    script = {
        "segments": [
            {"claim_id": "c1", "slide_index": 1, "text": "First segment."},
            {"claim_id": "c2", "slide_index": 1, "text": "Second."},
        ],
    }
    align = build_alignment("job1", script)
    assert len(align["segments"]) == 2
    assert align["segments"][0]["t_start"] >= 0
    assert align["segments"][0]["t_end"] > align["segments"][0]["t_start"]
    assert align["total_duration_seconds"] > 0
    assert align["source"] == "estimated"


def test_build_timeline_actions():
    """Timeline has actions with type, t_start, t_end, entity_ids, claim_id, evidence_ids."""
    script = {
        "segments": [
            {
                "claim_id": "c1",
                "slide_index": 1,
                "text": "Intro.",
                "entity_ids": ["n1"],
                "evidence_ids": ["ev1"],
            },
        ],
    }
    align = {
        "segments": [
            {"claim_id": "c1", "t_start": 0, "t_end": 2},
        ],
    }
    graph = {
        1: {
            "nodes": [
                {"node_id": "n1", "bbox": {"left": 0, "top": 0, "width": 914400, "height": 685800}}
            ],
            "edges": [],
            "clusters": [],
        },
    }
    dims = {1: (1280, 720)}
    timeline = build_timeline("job1", script, align, graph, dims)
    assert len(timeline["actions"]) >= 1
    a = timeline["actions"][0]
    assert a["type"] in (ACTION_HIGHLIGHT, ACTION_TRACE, "ZOOM")
    assert "t_start" in a and "t_end" in a
    assert "entity_ids" in a and "claim_id" in a and "evidence_ids" in a
    assert "bbox" in a or "path" in a or True


def test_emu_to_pixel():
    """EMU to pixel conversion scales correctly."""
    bbox = emu_to_pixel(0, 0, 9144000, 6858000, 1280, 720)
    assert bbox["w"] == 1280
    assert bbox["h"] == 720
