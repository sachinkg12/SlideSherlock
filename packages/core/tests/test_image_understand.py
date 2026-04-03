"""
Tests for image understanding stage (NO-HALLUCINATION policy).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vision_provider import (
    StubVisionExtractor,
    KIND_IMAGE_CAPTION,
    KIND_DIAGRAM_SUMMARY,
)
from image_understand import (
    IMAGE_EVIDENCE_KINDS,
    _is_picture_shape,
    _flatten_shapes,
    _stable_evidence_id,
    write_vision_summary,
)


def test_is_picture_shape():
    assert _is_picture_shape({"type": "PICTURE"}) is True
    assert _is_picture_shape({"type": "picture"}) is True
    assert _is_picture_shape({"type": "IMAGE"}) is True
    assert _is_picture_shape({"type": "PHOTO"}) is True
    assert _is_picture_shape({"type": "RECTANGLE"}) is False
    assert _is_picture_shape({"type": ""}) is False


def test_flatten_shapes():
    shapes = _flatten_shapes({
        "shapes": [{"type": "PICTURE", "ppt_shape_id": "1"}],
        "groups": [],
    })
    assert len(shapes) == 1
    assert shapes[0]["type"] == "PICTURE"

    shapes2 = _flatten_shapes({
        "shapes": [],
        "groups": [{"children": [{"type": "IMAGE", "ppt_shape_id": "2"}]}],
    })
    assert len(shapes2) == 1
    assert shapes2[0]["type"] == "IMAGE"


def test_stable_evidence_id():
    a = _stable_evidence_id("job1", 1, "IMAGE_CAPTION", "0")
    b = _stable_evidence_id("job1", 1, "IMAGE_CAPTION", "0")
    assert a == b
    c = _stable_evidence_id("job1", 1, "IMAGE_CAPTION", "1")
    assert a != c


def test_stub_vision_extractor_photo():
    ext = StubVisionExtractor()
    results = ext.extract_photo(b"fake", slide_index=1)
    assert len(results) == 1
    assert results[0].kind == KIND_IMAGE_CAPTION
    assert "contains an image" in results[0].content
    assert results[0].confidence < 0.7


def test_stub_vision_extractor_diagram():
    ext = StubVisionExtractor()
    results = ext.extract_diagram(b"fake", slide_index=1, vision_graph={
        "nodes": [{"label_text": "A"}, {"label_text": "B"}],
        "edges": [],
    })
    assert len(results) >= 1
    assert results[0].kind == KIND_DIAGRAM_SUMMARY
    assert "A" in results[0].content or "diagram" in results[0].content.lower()


def test_image_evidence_kinds():
    assert "IMAGE_CAPTION" in IMAGE_EVIDENCE_KINDS
    assert "DIAGRAM_ENTITIES" in IMAGE_EVIDENCE_KINDS


def test_write_vision_summary():
    """write_vision_summary reads evidence index and writes debug/vision_summary.json with counts and failures."""
    minio = MagicMock()
    index_payload = {
        "evidence_items": [
            {"evidence_id": "e1", "kind": "IMAGE_CAPTION", "confidence": 0.9, "slide_index": 1},
            {"evidence_id": "e2", "kind": "IMAGE_OBJECTS", "confidence": 0.8, "slide_index": 1},
            {"evidence_id": "e3", "kind": "SLIDE_CAPTION", "confidence": 0.1, "reason_code": "VISION_UNAVAILABLE", "slide_index": 2},
        ],
    }
    minio.get.return_value = json.dumps(index_payload).encode("utf-8")
    summary = write_vision_summary("job-123", minio)
    assert summary["job_id"] == "job-123"
    assert summary["counts_by_kind"]["IMAGE_CAPTION"] == 1
    assert summary["counts_by_kind"]["IMAGE_OBJECTS"] == 1
    assert summary["counts_by_kind"]["SLIDE_CAPTION"] == 1
    assert summary["failures"].get("VISION_UNAVAILABLE") == 1
    assert summary["total_image_evidence_items"] == 3
    put_path = None
    for call in minio.put.call_args_list:
        if "debug/vision_summary.json" in (call[0][0] if call[0] else ""):
            put_path = call[0][0]
            break
    assert put_path is not None
