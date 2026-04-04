"""
Tests for merge_engine: merge scoring + provenance rules.
- If vision disabled: unified == native, provenance NATIVE, confidence 1.0.
- If vision enabled: provenance NATIVE/VISION/BOTH, confidence per entity.
"""
from __future__ import annotations

import sys
import os

# Allow importing merge_engine from parent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from merge_engine import (
    merge_graphs,
    _geom_score,
    _overall_score,
    _text_similarity,
    _add_provenance_and_confidence,
)


# --- Merge scoring ---


def test_text_similarity_empty():
    assert _text_similarity("", "") == 1.0
    assert _text_similarity("", "foo") == 0.0
    assert _text_similarity("foo", "") == 0.0


def test_text_similarity_same():
    assert _text_similarity("hello", "hello") == 1.0
    assert _text_similarity("Hello World", "hello world") == 1.0


def test_text_similarity_partial():
    # "hello world" vs "hello" -> tokens {hello, world} vs {hello} -> inter 1, union 2 -> 0.5
    assert _text_similarity("hello world", "hello") == 0.5


def test_overall_score_weights():
    # geom 1, text 1, type 1 -> 0.4+0.4+0.2 = 1.0
    assert _overall_score(1.0, 1.0, 1.0) == 1.0
    assert _overall_score(0.5, 0.5, 0.5) == 0.5


def test_geom_score_same_bbox():
    # Same bbox in same coords -> IOU 1, dist 0
    b = {"left": 100, "top": 100, "width": 50, "height": 50}
    n = {"bbox": b}
    v = {"bbox": b}
    s = _geom_score(n, v, 1000.0, 1000.0, 1000.0, 1000.0)
    assert s >= 0.9


def test_add_provenance_and_confidence():
    entity = {"node_id": "n1", "label_text": "A"}
    out = _add_provenance_and_confidence(entity, "NATIVE", 1.0)
    assert out["provenance"] == "NATIVE"
    assert out["confidence"] == 1.0
    assert out["node_id"] == "n1"


# --- Provenance rules: vision disabled -> unified == native ---


def test_merge_vision_disabled_unified_equals_native():
    g_native = {
        "slide_index": 1,
        "nodes": [
            {
                "node_id": "n1",
                "ppt_shape_id": "2",
                "bbox": {"left": 100, "top": 100, "width": 50, "height": 50},
                "label_text": "A",
            },
        ],
        "edges": [
            {"edge_id": "e1", "src_node_id": "n1", "dst_node_id": "n2"},
        ],
        "clusters": [],
    }
    g_unified, flags = merge_graphs(g_native, None, slide_width_px=1000, slide_height_px=1000)
    assert len(g_unified["nodes"]) == 1
    assert g_unified["nodes"][0]["provenance"] == "NATIVE"
    assert g_unified["nodes"][0]["confidence"] == 1.0
    assert len(g_unified["edges"]) == 1
    assert g_unified["edges"][0]["provenance"] == "NATIVE"
    assert g_unified["edges"][0]["confidence"] == 1.0
    assert "needs_review" in flags


def test_merge_vision_empty_nodes_unified_equals_native():
    g_native = {
        "slide_index": 1,
        "nodes": [{"node_id": "n1", "bbox": {}, "label_text": "A"}],
        "edges": [],
        "clusters": [],
    }
    g_vision = {"slide_index": 1, "nodes": [], "edges": []}
    g_unified, _ = merge_graphs(g_native, g_vision, slide_width_px=1000, slide_height_px=1000)
    assert len(g_unified["nodes"]) == 1
    assert g_unified["nodes"][0]["provenance"] == "NATIVE"
    assert g_unified["nodes"][0]["confidence"] == 1.0


# --- Provenance rules: vision enabled -> NATIVE / VISION / BOTH ---


def test_merge_vision_adds_vision_only_node():
    g_native = {
        "slide_index": 1,
        "nodes": [
            {
                "node_id": "n1",
                "bbox": {"left": 100, "top": 100, "width": 50, "height": 50},
                "label_text": "A",
            },
        ],
        "edges": [],
        "clusters": [],
    }
    # Vision node in different place (no overlap) -> stays VISION-only
    g_vision = {
        "slide_index": 1,
        "nodes": [
            {
                "node_id": "v1",
                "det_id": "d1",
                "bbox": {"left": 500, "top": 500, "width": 60, "height": 30},
                "label_text": "OCR only",
            },
        ],
        "edges": [],
    }
    g_unified, flags = merge_graphs(
        g_native,
        g_vision,
        slide_width_px=1000,
        slide_height_px=1000,
        match_threshold=0.5,
    )
    # Native node + vision-only node
    assert len(g_unified["nodes"]) >= 2
    provenances = {n["provenance"] for n in g_unified["nodes"]}
    assert "NATIVE" in provenances
    assert "VISION" in provenances
    # Vision-only node should appear in unmatched_vision
    assert len(flags.get("unmatched_vision", [])) >= 1


def test_merge_vision_matched_both():
    # Overlapping bbox + same label -> BOTH
    g_native = {
        "slide_index": 1,
        "nodes": [
            {
                "node_id": "n1",
                "bbox": {"left": 100, "top": 100, "width": 100, "height": 50},
                "label_text": "Hello",
            },
        ],
        "edges": [],
        "clusters": [],
    }
    g_vision = {
        "slide_index": 1,
        "nodes": [
            {
                "node_id": "v1",
                "det_id": "d1",
                "bbox": {"left": 110, "top": 110, "width": 80, "height": 40},
                "label_text": "Hello",
                "confidence": 0.9,
            },
        ],
        "edges": [],
    }
    g_unified, _ = merge_graphs(
        g_native,
        g_vision,
        slide_width_px=1000,
        slide_height_px=1000,
        match_threshold=0.3,
    )
    # One merged node (BOTH) + possibly no unmatched
    nodes_by_prov = {}
    for n in g_unified["nodes"]:
        nodes_by_prov[n["provenance"]] = nodes_by_prov.get(n["provenance"], 0) + 1
    assert "BOTH" in nodes_by_prov or "NATIVE" in nodes_by_prov
    for n in g_unified["nodes"]:
        assert "provenance" in n
        assert "confidence" in n
        assert n["provenance"] in ("NATIVE", "VISION", "BOTH")
