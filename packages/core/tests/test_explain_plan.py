"""
Unit tests for explain_plan.py: build_explain_plan section ordering, structure, edge cases.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from explain_plan import build_explain_plan, PLAN_ORDER


def _make_graph(slide_index=0, nodes=None, edges=None, clusters=None):
    return {
        "slide_index": slide_index,
        "nodes": nodes or [],
        "edges": edges or [],
        "clusters": clusters or [],
    }


def test_empty_graphs_produces_valid_plan():
    """Empty unified_graphs list -> plan with zero sections."""
    plan = build_explain_plan("job-1", [])
    assert plan["job_id"] == "job-1"
    assert plan["schema_version"] == "1.0"
    assert plan["sections"] == []
    assert plan["ordering"] == list(PLAN_ORDER)
    assert plan["rag_chunk_ids"] == []


def test_single_slide_no_nodes_has_intro_and_summary():
    """A slide with no nodes/edges/clusters gets intro + summary sections only."""
    plan = build_explain_plan("job-2", [_make_graph(slide_index=0)])
    types = [s["section_type"] for s in plan["sections"]]
    assert types == ["intro", "summary"]


def test_nodes_produce_node_sections():
    """Each node in a graph produces a 'nodes' section."""
    graph = _make_graph(
        slide_index=0,
        nodes=[{"node_id": "n1"}, {"node_id": "n2"}],
    )
    plan = build_explain_plan("job-3", [graph])
    node_sections = [s for s in plan["sections"] if s["section_type"] == "nodes"]
    assert len(node_sections) == 2
    entity_ids_flat = [nid for s in node_sections for nid in s["entity_ids"]]
    assert "n1" in entity_ids_flat
    assert "n2" in entity_ids_flat


def test_edges_produce_flow_sections():
    """Each edge produces a 'flows' section."""
    graph = _make_graph(
        slide_index=0,
        edges=[{"edge_id": "e1"}, {"edge_id": "e2"}],
    )
    plan = build_explain_plan("job-4", [graph])
    flow_sections = [s for s in plan["sections"] if s["section_type"] == "flows"]
    assert len(flow_sections) == 2


def test_clusters_produce_cluster_sections():
    """Each cluster produces a 'clusters' section."""
    graph = _make_graph(
        slide_index=0,
        clusters=[
            {"cluster_id": "c1", "member_node_ids": ["n1", "n2"]},
            {"cluster_id": "c2", "member_node_ids": ["n3"]},
        ],
    )
    plan = build_explain_plan("job-5", [graph])
    cluster_sections = [s for s in plan["sections"] if s["section_type"] == "clusters"]
    assert len(cluster_sections) == 2


def test_section_ordering_is_intro_clusters_nodes_flows_summary():
    """Sections within a slide follow intro -> clusters -> nodes -> flows -> summary."""
    graph = _make_graph(
        slide_index=0,
        nodes=[{"node_id": "n1"}],
        edges=[{"edge_id": "e1"}],
        clusters=[{"cluster_id": "c1", "member_node_ids": ["n1"]}],
    )
    plan = build_explain_plan("job-6", [graph])
    types = [s["section_type"] for s in plan["sections"]]
    assert types.index("intro") < types.index("clusters")
    assert types.index("clusters") < types.index("nodes")
    assert types.index("nodes") < types.index("flows")
    assert types.index("flows") < types.index("summary")


def test_multi_slide_ordering():
    """Slide 0 sections come before slide 1 sections."""
    graphs = [_make_graph(slide_index=0), _make_graph(slide_index=1)]
    plan = build_explain_plan("job-7", graphs)
    slide_indices = [s["slide_index"] for s in plan["sections"]]
    # Slide 0 intro must appear before slide 1 intro
    assert slide_indices.index(0) < slide_indices.index(1)


def test_rag_chunk_ids_passed_through():
    """rag_chunk_ids are attached to the plan unchanged."""
    plan = build_explain_plan("job-8", [], rag_chunk_ids=["chunk-1", "chunk-2"])
    assert plan["rag_chunk_ids"] == ["chunk-1", "chunk-2"]


def test_rag_chunk_ids_default_to_empty_list():
    """No rag_chunk_ids argument -> empty list in plan."""
    plan = build_explain_plan("job-9", [])
    assert plan["rag_chunk_ids"] == []


def test_no_order_key_in_output_sections():
    """order_key is stripped from all output sections."""
    graph = _make_graph(slide_index=0, nodes=[{"node_id": "n1"}])
    plan = build_explain_plan("job-10", [graph])
    for section in plan["sections"]:
        assert "order_key" not in section


def test_no_cluster_id_field_in_output_sections():
    """cluster_id (singular) is stripped; cluster_ids (list) remains."""
    graph = _make_graph(
        slide_index=0,
        clusters=[{"cluster_id": "c1", "member_node_ids": []}],
    )
    plan = build_explain_plan("job-11", [graph])
    for section in plan["sections"]:
        assert "cluster_id" not in section
        # cluster_ids list is present on all sections
        assert "cluster_ids" in section


def test_plan_has_created_at_timestamp():
    """plan includes a created_at ISO timestamp."""
    plan = build_explain_plan("job-12", [])
    assert "created_at" in plan
    assert plan["created_at"].endswith("Z")


def test_plan_ordering_constant_matches_module():
    """PLAN_ORDER matches the expected phase sequence."""
    assert PLAN_ORDER == ("intro", "clusters", "nodes", "flows", "summary")


def test_cluster_entity_ids_contain_member_node_ids():
    """cluster sections list their member_node_ids as entity_ids."""
    graph = _make_graph(
        slide_index=0,
        clusters=[{"cluster_id": "c1", "member_node_ids": ["na", "nb"]}],
    )
    plan = build_explain_plan("job-13", [graph])
    cluster_sec = next(s for s in plan["sections"] if s["section_type"] == "clusters")
    assert set(cluster_sec["entity_ids"]) == {"na", "nb"}
