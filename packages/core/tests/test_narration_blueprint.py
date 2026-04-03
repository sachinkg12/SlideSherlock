"""
Unit tests for narration blueprint (smart narration Fig3 step 14).
- Slide type classification: diagram_process, bullet_list, chart, title_only.
- Template narration per type.
- Blueprint with llm_context (nodes, edges, clusters, evidence_ids).
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from narration_blueprint import (
    classify_slide_type,
    build_template_narration,
    build_narration_blueprint,
    build_blueprint_per_slide,
    SLIDE_TYPE_DIAGRAM_PROCESS,
    SLIDE_TYPE_BULLET_LIST,
    SLIDE_TYPE_CHART,
    SLIDE_TYPE_TITLE_ONLY,
)


def test_classify_diagram_process():
    """Rich diagram: multiple nodes + edges -> diagram_process."""
    graph = {
        "nodes": [{"node_id": "n1", "label_text": "A"}, {"node_id": "n2", "label_text": "B"}],
        "edges": [{"edge_id": "e1", "src_node_id": "n1", "dst_node_id": "n2"}],
        "clusters": [],
    }
    assert classify_slide_type("", graph) == SLIDE_TYPE_DIAGRAM_PROCESS


def test_classify_bullet_list():
    """Bullet-like structure -> bullet_list."""
    slide_text = """Key points:
- First point here
- Second point there
- Third point"""
    graph = {"nodes": [], "edges": [], "clusters": []}
    assert classify_slide_type(slide_text, graph) == SLIDE_TYPE_BULLET_LIST


def test_classify_chart():
    """Chart keywords -> chart."""
    slide_text = "Sales chart showing 45% growth"
    graph = {"nodes": [], "edges": [], "clusters": []}
    assert classify_slide_type(slide_text, graph) == SLIDE_TYPE_CHART


def test_classify_title_only():
    """Minimal content -> title_only."""
    slide_text = "Section 1"
    graph = {"nodes": [], "edges": [], "clusters": []}
    assert classify_slide_type(slide_text, graph) == SLIDE_TYPE_TITLE_ONLY


def test_template_diagram_process():
    """Template for diagram includes node labels and edge count."""
    graph = {
        "nodes": [{"label_text": "A"}, {"label_text": "B"}],
        "edges": [{"edge_id": "e1"}],
        "clusters": [{"cluster_id": "c1"}],
    }
    text = build_template_narration(1, SLIDE_TYPE_DIAGRAM_PROCESS, "Intro", graph)
    assert "A" in text or "B" in text
    assert "connection" in text
    assert "group" in text


def test_template_bullet_list():
    """Template for bullet list uses slide text."""
    slide_text = "Point one. Point two. Point three."
    graph = {}
    text = build_template_narration(1, SLIDE_TYPE_BULLET_LIST, slide_text, graph)
    assert "Point" in text


def test_template_title_only():
    """Template for title-only slide."""
    text = build_template_narration(1, SLIDE_TYPE_TITLE_ONLY, "Section 1", {})
    assert "Section 1" in text or "slide 1" in text.lower()


def test_build_narration_blueprint():
    """Blueprint includes slide_type, template_narration, llm_context."""
    graph = {
        "nodes": [{"node_id": "n1", "label_text": "A"}],
        "edges": [{"edge_id": "e1", "src_node_id": "n1", "dst_node_id": "n2"}],
        "clusters": [],
    }
    evidence_items = [{"evidence_id": "ev1", "slide_index": 1, "content": "A"}]
    bp = build_narration_blueprint(1, "", "Diagram", graph, evidence_items)
    assert bp["slide_index"] == 1
    assert bp["slide_type"] in (SLIDE_TYPE_DIAGRAM_PROCESS, SLIDE_TYPE_CHART, SLIDE_TYPE_TITLE_ONLY)
    assert "template_narration" in bp
    assert "llm_context" in bp
    assert "nodes" in bp["llm_context"]
    assert "edges" in bp["llm_context"]
    assert "evidence_ids" in bp["llm_context"]
    assert "ev1" in bp["llm_context"]["evidence_ids"]
    assert bp["needs_smart_narration"] is True


def test_build_blueprint_per_slide():
    """build_blueprint_per_slide returns one blueprint per slide."""
    slides_notes_and_text = [("", "Slide 1"), ("Notes with five or more words here.", "Slide 2")]
    unified_graphs = {
        1: {"nodes": [{"label_text": "A"}], "edges": [], "clusters": []},
        2: {"nodes": [], "edges": [], "clusters": []},
    }
    blueprints = build_blueprint_per_slide(2, slides_notes_and_text, unified_graphs)
    assert len(blueprints) == 2
    assert blueprints[0]["slide_index"] == 1
    assert blueprints[1]["slide_index"] == 2
    assert blueprints[0]["needs_smart_narration"] is True
    assert blueprints[1]["needs_smart_narration"] is False
