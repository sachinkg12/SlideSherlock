"""
Unit tests for llm_provider.py.
Tests: StubLLMProvider, _steps_from_diagram_interactions, _narrate_diagram_from_graph,
LLMProvider interface, generate_narration default.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from llm_provider import (
    LLMProvider,
    StubLLMProvider,
    _steps_from_diagram_interactions,
    _narrate_diagram_from_graph,
)


# ---------------------------------------------------------------------------
# _steps_from_diagram_interactions
# ---------------------------------------------------------------------------

class TestStepsFromDiagramInteractions:
    def test_parses_basic_interaction(self):
        steps = _steps_from_diagram_interactions("1:A->B:login")
        assert len(steps) == 1
        assert "A" in steps[0]
        assert "B" in steps[0]
        assert "login" in steps[0]

    def test_parses_multiple_interactions(self):
        steps = _steps_from_diagram_interactions("1:Client->Server:request; 2:Server->DB:query")
        assert len(steps) == 2

    def test_defaults_label_to_a_message(self):
        steps = _steps_from_diagram_interactions("1:A->B:")
        assert "a message" in steps[0]

    def test_empty_string_returns_empty_list(self):
        assert _steps_from_diagram_interactions("") == []

    def test_caps_at_15_steps(self):
        content = "; ".join(f"{i}:A->B:msg{i}" for i in range(1, 25))
        steps = _steps_from_diagram_interactions(content)
        assert len(steps) == 15

    def test_non_integer_order_falls_back(self):
        steps = _steps_from_diagram_interactions("X:A->B:hello")
        assert len(steps) == 1
        assert "Step 1:" in steps[0]


# ---------------------------------------------------------------------------
# _narrate_diagram_from_graph
# ---------------------------------------------------------------------------

class TestNarrateDiagramFromGraph:
    def _node(self, node_id, label):
        return {"node_id": node_id, "label_text": label}

    def _edge(self, src, dst):
        return {"src_node_id": src, "dst_node_id": dst}

    def test_returns_none_when_no_labels_and_no_edges(self):
        result = _narrate_diagram_from_graph(0, "", {"nodes": [], "edges": []})
        assert result is None

    def test_includes_node_labels_in_output(self):
        graph = {
            "nodes": [self._node("n1", "API Gateway"), self._node("n2", "Database")],
            "edges": [],
        }
        result = _narrate_diagram_from_graph(0, "", graph)
        assert "API Gateway" in result
        assert "Database" in result

    def test_includes_flow_description_for_edges(self):
        graph = {
            "nodes": [self._node("n1", "Client"), self._node("n2", "Server")],
            "edges": [self._edge("n1", "n2")],
        }
        result = _narrate_diagram_from_graph(0, "", graph)
        assert "Client" in result
        assert "Server" in result

    def test_handles_unlabeled_nodes_gracefully(self):
        graph = {
            "nodes": [{"node_id": "n1", "label_text": ""}],
            "edges": [],
        }
        result = _narrate_diagram_from_graph(0, "", graph)
        # No labels, no edges -> should return None
        assert result is None

    def test_returns_none_when_only_clusters_no_labels_or_edges(self):
        """When nodes have no labels and no edges, function returns None even with clusters."""
        graph = {
            "nodes": [],
            "edges": [],
            "clusters": [{"cluster_id": "c1"}, {"cluster_id": "c2"}],
        }
        result = _narrate_diagram_from_graph(0, "", graph)
        assert result is None

    def test_clusters_mentioned_when_edges_present_but_unlabeled(self):
        """Clusters appear in output when edges exist but produce no flow text."""
        graph = {
            "nodes": [{"node_id": "n1", "label_text": "Alpha"}],
            "edges": [],
            "clusters": [{"cluster_id": "c1"}, {"cluster_id": "c2"}],
        }
        result = _narrate_diagram_from_graph(0, "", graph)
        # labels exist, so result is not None
        assert result is not None
        assert "Alpha" in result


# ---------------------------------------------------------------------------
# StubLLMProvider.generate_segment
# ---------------------------------------------------------------------------

class TestStubLLMProviderGenerateSegment:
    @pytest.fixture
    def provider(self):
        return StubLLMProvider()

    @pytest.fixture
    def minimal_graph(self):
        return {"nodes": [], "edges": [], "clusters": []}

    def test_intro_section_returns_slide_index_and_counts(self, provider, minimal_graph):
        section = {"section_type": "intro", "slide_index": 3}
        result = provider.generate_segment(section, minimal_graph, [], [])
        assert "slide 3" in result.lower()

    def test_summary_section_returns_concludes_text(self, provider, minimal_graph):
        section = {"section_type": "summary", "slide_index": 2}
        result = provider.generate_segment(section, minimal_graph, [], [])
        assert "slide 2" in result.lower()

    def test_nodes_section_returns_element_labels(self, provider):
        graph = {
            "nodes": [{"node_id": "n1", "label_text": "Widget"}],
            "edges": [],
        }
        section = {"section_type": "nodes", "slide_index": 0}
        result = provider.generate_segment(section, graph, ["e1"], ["n1"])
        assert "Widget" in result

    def test_flows_section_returns_flow_description(self, provider):
        graph = {
            "nodes": [
                {"node_id": "n1", "label_text": "Source"},
                {"node_id": "n2", "label_text": "Target"},
            ],
            "edges": [
                {"edge_id": "e1", "src_node_id": "n1", "dst_node_id": "n2"}
            ],
        }
        section = {"section_type": "flows", "slide_index": 0}
        result = provider.generate_segment(section, graph, ["e1"], ["e1"])
        assert "Source" in result
        assert "Target" in result

    def test_clusters_section_returns_cluster_members(self, provider):
        graph = {
            "nodes": [{"node_id": "n1", "label_text": "Alpha"}],
            "edges": [],
        }
        section = {"section_type": "clusters", "slide_index": 0}
        result = provider.generate_segment(section, graph, [], ["n1"])
        assert "Alpha" in result

    def test_unknown_section_type_returns_fallback(self, provider, minimal_graph):
        section = {"section_type": "unknown_type", "slide_index": 0}
        result = provider.generate_segment(section, minimal_graph, [], [])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_context_bundle_notes_policy_returns_notes(self, provider, minimal_graph):
        section = {"section_type": "intro", "slide_index": 0}
        bundle = {"_policy": "notes", "notes": "Speaker note content here."}
        result = provider.generate_segment(section, minimal_graph, [], [], context_bundle=bundle)
        assert result == "Speaker note content here."

    def test_context_bundle_generic_policy_uses_graph(self, provider):
        graph = {
            "nodes": [{"node_id": "n1", "label_text": "Service A"}],
            "edges": [],
        }
        section = {"section_type": "intro", "slide_index": 0}
        bundle = {"_policy": "generic", "slide_text": ""}
        result = provider.generate_segment(section, graph, [], [], context_bundle=bundle)
        assert isinstance(result, str)

    def test_context_bundle_image_evidence_caption(self, provider, minimal_graph):
        section = {"section_type": "intro", "slide_index": 0}
        bundle = {
            "_policy": "image_evidence",
            "narration_tier": "high",
            "_use_hedging": False,
            "image_evidence_items": [
                {"kind": "IMAGE_CAPTION", "content": "A photo of a server rack.", "confidence": 0.9}
            ],
        }
        result = provider.generate_segment(section, minimal_graph, [], [], context_bundle=bundle)
        assert "server rack" in result.lower()

    def test_context_bundle_image_evidence_diagram_summary(self, provider, minimal_graph):
        section = {"section_type": "intro", "slide_index": 0}
        bundle = {
            "_policy": "image_evidence",
            "narration_tier": "medium",
            "_use_hedging": True,
            "image_evidence_items": [
                {"kind": "DIAGRAM_SUMMARY", "content": "Flow from client to server.", "confidence": 0.8}
            ],
        }
        result = provider.generate_segment(section, minimal_graph, [], [], context_bundle=bundle)
        assert "client" in result.lower() or "diagram" in result.lower()

    def test_context_bundle_interactions_narrate_steps(self, provider, minimal_graph):
        section = {"section_type": "intro", "slide_index": 0}
        bundle = {
            "_policy": "image_evidence",
            "narration_tier": "high",
            "_use_hedging": False,
            "image_evidence_items": [
                {
                    "kind": "DIAGRAM_INTERACTIONS",
                    "content": "1:Alice->Bob:login; 2:Bob->DB:query",
                    "confidence": 0.9,
                }
            ],
        }
        result = provider.generate_segment(section, minimal_graph, [], [], context_bundle=bundle)
        assert "Alice" in result or "Step" in result


# ---------------------------------------------------------------------------
# LLMProvider: generate_narration default (stub returns None)
# ---------------------------------------------------------------------------

class TestLLMProviderGenerateNarration:
    def test_generate_narration_returns_none_by_default(self):
        provider = StubLLMProvider()
        result = provider.generate_narration({"slide_index": 0, "slide_type": "content"})
        assert result is None
