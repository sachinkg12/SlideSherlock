"""
Unit tests for DIAGRAM understanding (OCR + structure -> evidence).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from diagram_understand import (
    DIAGRAM_TYPE_SEQUENCE,
    DIAGRAM_TYPE_FLOW,
    DIAGRAM_TYPE_UNKNOWN,
    _determine_diagram_type,
    _run_diagram_parse,
    _build_diagram_summary,
    _extract_entities_sequence,
)


def test_determine_diagram_type_sequence():
    """Horizontal lines + top labels -> SEQUENCE."""
    spans = [
        {"bbox": {"left": 10, "top": 5, "width": 50, "height": 10}, "text": "Actor"},
        {"bbox": {"left": 100, "top": 8, "width": 40, "height": 10}, "text": "Service"},
    ]
    primitives = {
        "lines": [
            {"x1": 20, "y1": 100, "x2": 200, "y2": 100},
            {"x1": 20, "y1": 150, "x2": 200, "y2": 148},
        ],
    }
    dtype, conf = _determine_diagram_type(spans, primitives, 400, 300)
    assert dtype == DIAGRAM_TYPE_SEQUENCE
    assert conf >= 0.5


def test_determine_diagram_type_flow():
    """Vertical/mixed lines -> FLOW."""
    primitives = {
        "lines": [
            {"x1": 50, "y1": 50, "x2": 50, "y2": 150},
            {"x1": 150, "y1": 50, "x2": 150, "y2": 150},
        ],
    }
    dtype, conf = _determine_diagram_type([], primitives, 400, 300)
    assert dtype == DIAGRAM_TYPE_FLOW
    assert conf >= 0.4


def test_determine_diagram_type_unknown():
    """No lines and no spans -> UNKNOWN."""
    dtype, conf = _determine_diagram_type([], {"lines": []}, 400, 300)
    assert dtype == DIAGRAM_TYPE_UNKNOWN
    assert conf <= 0.5


def test_extract_entities_sequence():
    """Top-region OCR spans become lifelines."""
    spans = [
        {"bbox": {"left": 10, "top": 10, "width": 40, "height": 12}, "text": "User"},
        {"bbox": {"left": 100, "top": 15, "width": 50, "height": 12}, "text": "API"},
        {"bbox": {"left": 50, "top": 200, "width": 30, "height": 10}, "text": "middle"},
    ]
    entities = _extract_entities_sequence(spans, 400, 300)
    names = [e["name"] for e in entities]
    assert "User" in names
    assert "API" in names
    assert "middle" not in names  # below top fraction


def test_run_diagram_parse_sequence():
    """Parse with sequence-like OCR + lines yields entities and interactions."""
    ocr_result = {
        "spans": [
            {"bbox": {"left": 10, "top": 8, "width": 40, "height": 10}, "text": "A"},
            {"bbox": {"left": 150, "top": 10, "width": 30, "height": 10}, "text": "B"},
            {"bbox": {"left": 80, "top": 100, "width": 30, "height": 8}, "text": "msg"},
        ],
        "avg_conf": 0.8,
    }
    primitives = {
        "lines": [
            {"x1": 30, "y1": 95, "x2": 160, "y2": 95},
            {"x1": 30, "y1": 130, "x2": 160, "y2": 130},
        ],
        "reason_code": None,
    }
    parse = _run_diagram_parse(ocr_result, primitives, 400, 300)
    assert parse["diagram_type"] == DIAGRAM_TYPE_SEQUENCE
    assert len(parse["entities"]) >= 1
    assert "interactions" in parse
    assert parse["confidence"] >= 0


def test_build_diagram_summary_no_hallucination():
    """Summary contains only entities and interactions from parse."""
    parse = {
        "diagram_type": DIAGRAM_TYPE_SEQUENCE,
        "entities": [{"name": "Actor A"}, {"name": "Service B"}],
        "interactions": [
            {"from_entity": "Actor A", "to_entity": "Service B", "label": "request"},
        ],
    }
    summary = _build_diagram_summary(parse)
    assert "Actor A" in summary
    assert "Service B" in summary
    assert "request" in summary
    # No random content
    assert "maybe" not in summary.lower() or "could not" in summary


def test_build_diagram_summary_empty():
    """Empty parse yields low-confidence message."""
    parse = {"diagram_type": DIAGRAM_TYPE_UNKNOWN, "entities": [], "interactions": []}
    summary = _build_diagram_summary(parse)
    assert "could not" in summary or "low confidence" in summary.lower()


def test_run_diagram_understand_empty():
    """No DIAGRAM images -> empty results and artifacts still written."""
    from unittest.mock import MagicMock

    from diagram_understand import run_diagram_understand

    minio = MagicMock()
    result = run_diagram_understand(
        job_id="job1",
        project_id="proj1",
        images_index={"images": []},
        image_kinds={"classifications": []},
        minio_client=minio,
        db_session=MagicMock(),
    )
    assert result["evidence_count"] == 0
    assert result["diagram_results"] == []
    # Artifacts should still be written (empty)
    put_calls = [str(c) for c in minio.put.call_args_list]
    assert any("diagram_ocr.json" in c for c in put_calls)
    assert any("diagram_parse.json" in c for c in put_calls)
