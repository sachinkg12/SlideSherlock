"""
Tests for vision_graph.py: ID helpers, build_vision_graph_slide.
OCR backend and OpenCV are mocked throughout.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import vision_graph as vg_module
from vision_graph import _node_id_v, _edge_id_v, _bbox_center, build_vision_graph_slide


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def test_node_id_v_stable():
    assert _node_id_v(1, "ocr_abc") == _node_id_v(1, "ocr_abc")


def test_node_id_v_differs_by_slide():
    assert _node_id_v(1, "ocr_abc") != _node_id_v(2, "ocr_abc")


def test_edge_id_v_stable():
    assert _edge_id_v(1, 0) == _edge_id_v(1, 0)


def test_edge_id_v_differs_by_index():
    assert _edge_id_v(1, 0) != _edge_id_v(1, 1)


# ---------------------------------------------------------------------------
# _bbox_center
# ---------------------------------------------------------------------------

def test_bbox_center_basic():
    bbox = {"left": 10, "top": 20, "width": 80, "height": 60}
    cx, cy = _bbox_center(bbox)
    assert cx == pytest.approx(50.0)
    assert cy == pytest.approx(50.0)


def test_bbox_center_zeros():
    cx, cy = _bbox_center({"left": 0, "top": 0, "width": 0, "height": 0})
    assert cx == 0.0
    assert cy == 0.0


# ---------------------------------------------------------------------------
# build_vision_graph_slide – no OCR module available
# ---------------------------------------------------------------------------

def test_build_vision_graph_slide_no_run_ocr_returns_empty():
    with patch.object(vg_module, "run_ocr", None):
        result = build_vision_graph_slide(MagicMock(), slide_index=1)
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["text_spans"] == []
    assert result["slide_index"] == 1


# ---------------------------------------------------------------------------
# build_vision_graph_slide – with mocked OCR
# ---------------------------------------------------------------------------

def _make_span(ocr_id, text, conf=0.9, left=0, top=0, width=50, height=20):
    return {
        "ocr_id": ocr_id,
        "text": text,
        "conf": conf,
        "bbox": {"left": left, "top": top, "width": width, "height": height},
    }


def test_build_vision_graph_slide_creates_nodes_from_ocr():
    spans = [
        _make_span("id1", "Hello", conf=0.95, left=0, top=0),
        _make_span("id2", "World", conf=0.80, left=100, top=0),
    ]
    mock_run_ocr = MagicMock(return_value=spans)
    with patch.object(vg_module, "run_ocr", mock_run_ocr):
        result = build_vision_graph_slide(MagicMock(), slide_index=2)

    assert len(result["nodes"]) == 2
    labels = {n["label_text"] for n in result["nodes"]}
    assert "Hello" in labels
    assert "World" in labels


def test_build_vision_graph_slide_populates_text_spans():
    spans = [_make_span("id1", "SlideText")]
    mock_run_ocr = MagicMock(return_value=spans)
    with patch.object(vg_module, "run_ocr", mock_run_ocr):
        result = build_vision_graph_slide(MagicMock(), slide_index=1)

    assert len(result["text_spans"]) == 1
    assert result["text_spans"][0]["text"] == "SlideText"


def test_build_vision_graph_slide_node_ids_stable():
    spans = [_make_span("ocr_x", "Stable")]
    mock_run_ocr = MagicMock(return_value=spans)
    with patch.object(vg_module, "run_ocr", mock_run_ocr):
        r1 = build_vision_graph_slide(MagicMock(), slide_index=5)
        r2 = build_vision_graph_slide(MagicMock(), slide_index=5)

    assert r1["nodes"][0]["node_id"] == r2["nodes"][0]["node_id"]


def test_build_vision_graph_slide_no_spans_returns_empty():
    mock_run_ocr = MagicMock(return_value=[])
    with patch.object(vg_module, "run_ocr", mock_run_ocr):
        result = build_vision_graph_slide(MagicMock(), slide_index=1)
    assert result["nodes"] == []
    assert result["text_spans"] == []


def test_build_vision_graph_slide_no_line_edges_by_default():
    spans = [_make_span("id1", "OnlyText")]
    mock_run_ocr = MagicMock(return_value=spans)
    with patch.object(vg_module, "run_ocr", mock_run_ocr):
        result = build_vision_graph_slide(MagicMock(), slide_index=1, detect_lines=False)
    assert result["edges"] == []


def test_build_vision_graph_slide_detect_lines_disabled_when_cv2_unavailable():
    spans = [_make_span("id1", "Text")]
    mock_run_ocr = MagicMock(return_value=spans)
    with patch.object(vg_module, "run_ocr", mock_run_ocr), \
         patch.object(vg_module, "CV2_AVAILABLE", False):
        result = build_vision_graph_slide(MagicMock(), slide_index=1, detect_lines=True)
    # No OpenCV means no line edges even with detect_lines=True
    assert result["edges"] == []


def test_build_vision_graph_slide_node_center_computed():
    spans = [_make_span("id1", "Center", left=10, top=20, width=80, height=60)]
    mock_run_ocr = MagicMock(return_value=spans)
    with patch.object(vg_module, "run_ocr", mock_run_ocr):
        result = build_vision_graph_slide(MagicMock(), slide_index=1)

    node = result["nodes"][0]
    assert node["center"]["x"] == pytest.approx(50.0)
    assert node["center"]["y"] == pytest.approx(50.0)
