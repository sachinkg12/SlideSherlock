"""
Tests for native_graph.py: ID helpers, geometry utils, build_native_graph_slide.
build_native_graph_and_persist is tested with mocked db and minio.
"""
from __future__ import annotations

import os
import sys
import hashlib
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from native_graph import (
    _node_id,
    _edge_id,
    _cluster_id,
    _bbox_center,
    _bbox_contains,
    _dist,
    _resolve_endpoint,
    build_native_graph_slide,
)


# ---------------------------------------------------------------------------
# ID helpers – stability and uniqueness
# ---------------------------------------------------------------------------

def test_node_id_stable():
    assert _node_id(1, "shape_5") == _node_id(1, "shape_5")


def test_node_id_differs_by_slide():
    assert _node_id(1, "shape_5") != _node_id(2, "shape_5")


def test_edge_id_stable():
    assert _edge_id(1, "conn_3") == _edge_id(1, "conn_3")


def test_cluster_id_stable():
    assert _cluster_id(1, "group_7") == _cluster_id(1, "group_7")


# ---------------------------------------------------------------------------
# _bbox_center
# ---------------------------------------------------------------------------

def test_bbox_center_simple():
    bbox = {"left": 0, "top": 0, "width": 100, "height": 50}
    cx, cy = _bbox_center(bbox)
    assert cx == pytest.approx(50.0)
    assert cy == pytest.approx(25.0)


def test_bbox_center_offset():
    bbox = {"left": 10, "top": 20, "width": 40, "height": 60}
    cx, cy = _bbox_center(bbox)
    assert cx == pytest.approx(30.0)
    assert cy == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# _bbox_contains
# ---------------------------------------------------------------------------

def test_bbox_contains_point_inside():
    bbox = {"left": 0, "top": 0, "width": 100, "height": 100}
    assert _bbox_contains(bbox, 50, 50)


def test_bbox_contains_point_outside():
    bbox = {"left": 0, "top": 0, "width": 100, "height": 100}
    assert not _bbox_contains(bbox, 150, 50)


def test_bbox_contains_boundary():
    bbox = {"left": 0, "top": 0, "width": 100, "height": 100}
    assert _bbox_contains(bbox, 0, 0)
    assert _bbox_contains(bbox, 100, 100)


# ---------------------------------------------------------------------------
# _resolve_endpoint
# ---------------------------------------------------------------------------

def _make_node(node_id, left, top, width, height):
    return {
        "node_id": node_id,
        "bbox": {"left": left, "top": top, "width": width, "height": height},
    }


def test_resolve_endpoint_single_containing_node():
    nodes = [_make_node("n1", 0, 0, 100, 100), _make_node("n2", 200, 0, 100, 100)]
    nid, conf, needs_review = _resolve_endpoint(50, 50, nodes)
    assert nid == "n1"
    assert needs_review is False
    assert conf == pytest.approx(1.0)


def test_resolve_endpoint_nearest_when_no_containment():
    nodes = [_make_node("n1", 0, 0, 10, 10), _make_node("n2", 200, 0, 10, 10)]
    # Point at (5, 5) -> inside n1
    nid, conf, needs_review = _resolve_endpoint(5, 5, nodes)
    assert nid == "n1"


def test_resolve_endpoint_no_nodes():
    nid, conf, needs_review = _resolve_endpoint(50, 50, [])
    assert nid is None
    assert needs_review is True


def test_resolve_endpoint_tie_marks_needs_review():
    # Two nodes both contain the point -> ambiguous
    nodes = [_make_node("n1", 0, 0, 100, 100), _make_node("n2", 0, 0, 100, 100)]
    nid, conf, needs_review = _resolve_endpoint(50, 50, nodes)
    assert needs_review is True


# ---------------------------------------------------------------------------
# build_native_graph_slide
# ---------------------------------------------------------------------------

def _make_slide_payload_simple():
    return {
        "slide_index": 1,
        "shapes": [
            {
                "ppt_shape_id": "1",
                "bbox": {"left": 0, "top": 0, "width": 100, "height": 100},
                "text_runs": [{"text": "Node A"}],
                "z_order": 0,
            },
            {
                "ppt_shape_id": "2",
                "bbox": {"left": 200, "top": 0, "width": 100, "height": 100},
                "text_runs": [{"text": "Node B"}],
                "z_order": 1,
            },
        ],
        "connectors": [
            {
                "ppt_connector_id": "conn_3",
                "bbox": {"left": 100, "top": 50, "width": 100, "height": 1},
                "endpoints": {
                    "begin": {"x": 50, "y": 50},
                    "end": {"x": 250, "y": 50},
                },
                "label": "connects",
                "style": "STRAIGHT",
                "z_order": 2,
            }
        ],
        "groups": [],
    }


def test_build_native_graph_slide_returns_dict():
    result = build_native_graph_slide(_make_slide_payload_simple())
    assert "nodes" in result
    assert "edges" in result
    assert "clusters" in result
    assert "needs_review" in result


def test_build_native_graph_slide_node_count():
    result = build_native_graph_slide(_make_slide_payload_simple())
    assert len(result["nodes"]) == 2


def test_build_native_graph_slide_edge_count():
    result = build_native_graph_slide(_make_slide_payload_simple())
    assert len(result["edges"]) == 1


def test_build_native_graph_slide_node_label():
    result = build_native_graph_slide(_make_slide_payload_simple())
    labels = {n["label_text"] for n in result["nodes"]}
    assert "Node A" in labels
    assert "Node B" in labels


def test_build_native_graph_slide_edge_resolves_endpoints():
    result = build_native_graph_slide(_make_slide_payload_simple())
    edge = result["edges"][0]
    # Both endpoints should resolve to distinct nodes without needing review
    assert edge["src_node_id"] is not None
    assert edge["dst_node_id"] is not None
    assert edge["src_node_id"] != edge["dst_node_id"]
    assert edge["needs_review"] is False


def test_build_native_graph_slide_no_shapes():
    payload = {"slide_index": 2, "shapes": [], "connectors": [], "groups": []}
    result = build_native_graph_slide(payload)
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["clusters"] == []


def test_build_native_graph_slide_group_creates_cluster():
    payload = {
        "slide_index": 3,
        "shapes": [],
        "connectors": [],
        "groups": [
            {
                "ppt_shape_id": "group_10",
                "type": "GROUP",
                "bbox": {"left": 0, "top": 0, "width": 200, "height": 200},
                "text_runs": [{"text": "My Group"}],
                "z_order": 0,
                "children": [
                    {
                        "ppt_shape_id": "11",
                        "bbox": {"left": 10, "top": 10, "width": 50, "height": 50},
                        "text_runs": [{"text": "Child"}],
                        "z_order": 0,
                    }
                ],
            }
        ],
    }
    result = build_native_graph_slide(payload)
    assert len(result["clusters"]) == 1
    assert result["clusters"][0]["title"] == "My Group"
    # The child shape should be a node
    assert any(n["label_text"] == "Child" for n in result["nodes"])
