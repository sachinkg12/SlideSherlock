"""
Unit tests for timeline_builder.py — emu_to_pixel, resolve_node_bbox, resolve_edge_path,
resolve_cluster_bbox, choose_action_type, _resolve_image_bbox_from_evidence, build_timeline.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from timeline_builder import (
    emu_to_pixel,
    resolve_node_bbox,
    resolve_edge_path,
    resolve_cluster_bbox,
    choose_action_type,
    _resolve_image_bbox_from_evidence,
    build_timeline,
    ACTION_HIGHLIGHT,
    ACTION_TRACE,
    ACTION_ZOOM,
    DEFAULT_SLIDE_WIDTH_EMU,
    DEFAULT_SLIDE_HEIGHT_EMU,
)


# ---------------------------------------------------------------------------
# emu_to_pixel
# ---------------------------------------------------------------------------


def test_emu_to_pixel_full_width():
    """1-slide-width EMU should map to slide_width_px."""
    result = emu_to_pixel(0, 0, DEFAULT_SLIDE_WIDTH_EMU, DEFAULT_SLIDE_HEIGHT_EMU, 1280, 720)
    assert abs(result["w"] - 1280) < 1
    assert abs(result["h"] - 720) < 1


def test_emu_to_pixel_origin():
    """Top-left at (0,0) EMU stays at (0,0) px."""
    result = emu_to_pixel(0, 0, 100, 100, 1280, 720)
    assert result["x"] == 0.0
    assert result["y"] == 0.0


def test_emu_to_pixel_center():
    """Center of slide in EMU should map to pixel center."""
    result = emu_to_pixel(
        DEFAULT_SLIDE_WIDTH_EMU / 2,
        DEFAULT_SLIDE_HEIGHT_EMU / 2,
        0,
        0,
        1280,
        720,
    )
    assert abs(result["x"] - 640) < 1
    assert abs(result["y"] - 360) < 1


def test_emu_to_pixel_zero_emu_dimensions_safe():
    """Zero slide_width_emu or slide_height_emu should not raise ZeroDivisionError."""
    result = emu_to_pixel(0, 0, 100, 100, 1280, 720, slide_width_emu=0, slide_height_emu=0)
    assert result["x"] == 0.0
    assert result["w"] == 0.0


# ---------------------------------------------------------------------------
# resolve_node_bbox
# ---------------------------------------------------------------------------


def test_resolve_node_bbox_valid():
    node = {"bbox": {"left": 0, "top": 0, "width": DEFAULT_SLIDE_WIDTH_EMU, "height": DEFAULT_SLIDE_HEIGHT_EMU}}
    result = resolve_node_bbox(node, 1280, 720)
    assert result is not None
    assert abs(result["w"] - 1280) < 1


def test_resolve_node_bbox_zero_size_returns_none():
    node = {"bbox": {"left": 0, "top": 0, "width": 0, "height": 0}}
    assert resolve_node_bbox(node, 1280, 720) is None


def test_resolve_node_bbox_missing_bbox_returns_none():
    node = {}
    assert resolve_node_bbox(node, 1280, 720) is None


# ---------------------------------------------------------------------------
# resolve_edge_path
# ---------------------------------------------------------------------------


def test_resolve_edge_path_valid():
    src = {"bbox": {"left": 0, "top": 0, "width": 914400, "height": 685800}}
    dst = {"bbox": {"left": 4572000, "top": 3429000, "width": 914400, "height": 685800}}
    nodes = {"node-a": src, "node-b": dst}
    edge = {"src_node_id": "node-a", "dst_node_id": "node-b"}

    path = resolve_edge_path(edge, nodes, 1280, 720)
    assert path is not None
    assert len(path) == 2
    assert "x" in path[0] and "y" in path[0]


def test_resolve_edge_path_missing_src_returns_none():
    nodes = {"node-b": {"bbox": {"left": 0, "top": 0, "width": 100, "height": 100}}}
    edge = {"src_node_id": "node-a", "dst_node_id": "node-b"}
    assert resolve_edge_path(edge, nodes, 1280, 720) is None


def test_resolve_edge_path_missing_dst_returns_none():
    nodes = {"node-a": {"bbox": {"left": 0, "top": 0, "width": 100, "height": 100}}}
    edge = {"src_node_id": "node-a", "dst_node_id": "node-b"}
    assert resolve_edge_path(edge, nodes, 1280, 720) is None


# ---------------------------------------------------------------------------
# choose_action_type
# ---------------------------------------------------------------------------


def test_choose_action_type_no_entities_returns_highlight():
    seg = {"entity_ids": []}
    graph = {"nodes": [], "edges": [], "clusters": []}
    assert choose_action_type(seg, graph) == ACTION_HIGHLIGHT


def test_choose_action_type_edge_returns_trace():
    seg = {"entity_ids": ["edge-1"]}
    graph = {
        "nodes": [],
        "edges": [{"edge_id": "edge-1"}],
        "clusters": [],
    }
    assert choose_action_type(seg, graph) == ACTION_TRACE


def test_choose_action_type_cluster_returns_zoom():
    seg = {"entity_ids": ["cluster-1"]}
    graph = {
        "nodes": [],
        "edges": [],
        "clusters": [{"cluster_id": "cluster-1"}],
    }
    assert choose_action_type(seg, graph) == ACTION_ZOOM


def test_choose_action_type_node_returns_highlight():
    seg = {"entity_ids": ["node-1"]}
    graph = {
        "nodes": [{"node_id": "node-1"}],
        "edges": [],
        "clusters": [],
    }
    assert choose_action_type(seg, graph) == ACTION_HIGHLIGHT


# ---------------------------------------------------------------------------
# _resolve_image_bbox_from_evidence
# ---------------------------------------------------------------------------


def test_resolve_image_bbox_no_evidence():
    seg = {"evidence_ids": []}
    result = _resolve_image_bbox_from_evidence(seg, {}, {}, 0, 1280, 720)
    assert result == (None, None)


def test_resolve_image_bbox_non_image_kind_skipped():
    seg = {"evidence_ids": ["ev1"]}
    evidence_by_id = {
        "ev1": {"evidence_id": "ev1", "kind": "TEXT_SPAN", "refs": []},
    }
    result = _resolve_image_bbox_from_evidence(seg, evidence_by_id, {}, 0, 1280, 720)
    assert result == (None, None)


def test_resolve_image_bbox_found_in_index():
    seg = {"evidence_ids": ["ev-img"]}
    evidence_by_id = {
        "ev-img": {
            "evidence_id": "ev-img",
            "kind": "IMAGE_ASSET",
            "refs": [
                {"ref_type": "IMAGE", "slide_index": 0, "url": "jobs/j1/images/img001.png"},
            ],
        }
    }
    images_index = {
        "images": [
            {
                "image_id": "IMG001",
                "uri": "jobs/j1/images/img001.png",
                "slide_index": 0,
                "bbox": {"x": 0, "y": 0, "w": DEFAULT_SLIDE_WIDTH_EMU, "h": DEFAULT_SLIDE_HEIGHT_EMU},
            }
        ]
    }
    entity_ids, bbox = _resolve_image_bbox_from_evidence(seg, evidence_by_id, images_index, 0, 1280, 720)
    assert entity_ids == ["image:IMG_IMG001"]
    assert bbox is not None
    assert bbox["w"] > 0


# ---------------------------------------------------------------------------
# build_timeline
# ---------------------------------------------------------------------------


def test_build_timeline_empty_script():
    script = {"segments": []}
    alignment = {"segments": []}
    result = build_timeline("job-1", script, alignment, {}, {})
    assert result["actions"] == []
    assert result["total_duration_seconds"] == 0
    assert result["job_id"] == "job-1"
    assert result["schema_version"] == "1.0"


def test_build_timeline_basic_segment():
    script = {
        "segments": [
            {
                "claim_id": "c1",
                "slide_index": 0,
                "entity_ids": [],
                "evidence_ids": [],
            }
        ]
    }
    alignment = {
        "segments": [{"claim_id": "c1", "t_start": 0.0, "t_end": 3.5}]
    }
    result = build_timeline("job-1", script, alignment, {}, {0: (1280, 720)})
    assert len(result["actions"]) == 1
    action = result["actions"][0]
    assert action["type"] == ACTION_HIGHLIGHT
    assert action["t_start"] == 0.0
    assert action["t_end"] == 3.5
    assert action["slide_index"] == 0


def test_build_timeline_segment_with_node_adds_bbox():
    node = {"node_id": "n1", "bbox": {"left": 0, "top": 0, "width": DEFAULT_SLIDE_WIDTH_EMU // 2, "height": DEFAULT_SLIDE_HEIGHT_EMU // 2}}
    graph = {"nodes": [node], "edges": [], "clusters": []}
    script = {"segments": [{"claim_id": "c2", "slide_index": 0, "entity_ids": ["n1"], "evidence_ids": []}]}
    alignment = {"segments": [{"claim_id": "c2", "t_start": 1.0, "t_end": 4.0}]}
    result = build_timeline("job-2", script, alignment, {0: graph}, {0: (1280, 720)})
    action = result["actions"][0]
    assert "bbox" in action
    assert action["bbox"]["w"] > 0


def test_build_timeline_segment_with_edge_adds_path():
    node_a = {"node_id": "n1", "bbox": {"left": 0, "top": 0, "width": 914400, "height": 685800}}
    node_b = {"node_id": "n2", "bbox": {"left": 4572000, "top": 0, "width": 914400, "height": 685800}}
    edge = {"edge_id": "e1", "src_node_id": "n1", "dst_node_id": "n2"}
    graph = {"nodes": [node_a, node_b], "edges": [edge], "clusters": []}
    script = {"segments": [{"claim_id": "c3", "slide_index": 0, "entity_ids": ["e1"], "evidence_ids": []}]}
    alignment = {"segments": [{"claim_id": "c3", "t_start": 0.0, "t_end": 2.0}]}
    result = build_timeline("job-3", script, alignment, {0: graph}, {0: (1280, 720)})
    action = result["actions"][0]
    assert action["type"] == ACTION_TRACE
    assert "path" in action


def test_build_timeline_action_ids_are_unique():
    segments = [
        {"claim_id": f"c{i}", "slide_index": 0, "entity_ids": [], "evidence_ids": []}
        for i in range(5)
    ]
    alignment_segs = [{"claim_id": f"c{i}", "t_start": float(i), "t_end": float(i + 1)} for i in range(5)]
    script = {"segments": segments}
    alignment = {"segments": alignment_segs}
    result = build_timeline("job-4", script, alignment, {}, {0: (1280, 720)})
    ids = [a["action_id"] for a in result["actions"]]
    assert len(ids) == len(set(ids))


def test_build_timeline_total_duration_is_max_t_end():
    script = {
        "segments": [
            {"claim_id": "c1", "slide_index": 0, "entity_ids": [], "evidence_ids": []},
            {"claim_id": "c2", "slide_index": 0, "entity_ids": [], "evidence_ids": []},
        ]
    }
    alignment = {
        "segments": [
            {"claim_id": "c1", "t_start": 0.0, "t_end": 5.0},
            {"claim_id": "c2", "t_start": 5.0, "t_end": 12.5},
        ]
    }
    result = build_timeline("job-5", script, alignment, {}, {0: (1280, 720)})
    assert abs(result["total_duration_seconds"] - 12.5) < 0.001
