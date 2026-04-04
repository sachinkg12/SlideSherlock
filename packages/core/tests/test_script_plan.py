"""
Tests for explain plan and script generator (Fig3 step 10/11).
- script.json has segments with claim_id, slide_index, text, evidence_ids[], entity_ids[]
- stub mode produces deterministic template text; every segment is grounded.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from explain_plan import build_explain_plan, PLAN_ORDER
from llm_provider import StubLLMProvider
from rag import retrieve_chunk_ids, tfidf_retrieve
from script_generator import generate_script


def test_explain_plan_ordering():
    """Explain plan uses intro -> clusters -> nodes -> flows -> summary."""
    g = {
        "slide_index": 1,
        "nodes": [{"node_id": "n1", "label_text": "A"}, {"node_id": "n2", "label_text": "B"}],
        "edges": [{"edge_id": "e1", "src_node_id": "n1", "dst_node_id": "n2"}],
        "clusters": [],
    }
    plan = build_explain_plan("job1", [g])
    assert plan["ordering"] == list(PLAN_ORDER)
    section_types = [s["section_type"] for s in plan["sections"]]
    assert "intro" in section_types
    assert "nodes" in section_types
    assert "flows" in section_types
    assert "summary" in section_types


def test_script_segments_grounded():
    """script.json segments have claim_id, slide_index, text, evidence_ids[], entity_ids[]; stub is grounded."""
    g = {
        "slide_index": 1,
        "nodes": [{"node_id": "n1", "label_text": "A"}, {"node_id": "n2", "label_text": "B"}],
        "edges": [{"edge_id": "e1", "src_node_id": "n1", "dst_node_id": "n2"}],
        "clusters": [],
    }
    plan = build_explain_plan("job1", [g])
    by_slide = {1: g}
    evidence_index = {"evidence_items": [{"evidence_id": "ev1", "slide_index": 1}]}
    entity_to_evidence = {"n1": ["ev1"], "n2": ["ev1"], "e1": ["ev2"]}
    stub = StubLLMProvider()
    script = generate_script("job1", plan, by_slide, evidence_index, entity_to_evidence, stub)
    assert script["draft"] is True
    assert "segments" in script
    for s in script["segments"]:
        assert "claim_id" in s
        assert "slide_index" in s
        assert "text" in s
        assert "evidence_ids" in s
        assert "entity_ids" in s
        assert "used_hedging" in s
        # Grounded: at least one of evidence_ids or entity_ids
        assert len(s["evidence_ids"]) > 0 or len(s["entity_ids"]) > 0


def test_stub_deterministic():
    """Stub LLM returns deterministic template text (no LLM)."""
    stub = StubLLMProvider()
    section = {"section_type": "intro", "slide_index": 1, "entity_ids": [], "evidence_ids": []}
    graph = {"nodes": [], "edges": [], "clusters": []}
    text = stub.generate_segment(section, graph, [], [])
    assert "slide" in text.lower() or "1" in text


def test_script_with_context_bundle_image_evidence():
    """With context bundle (image_evidence high conf), intro segment cites caption and has evidence_ids."""
    from script_context import build_context_bundle

    g = {"slide_index": 1, "nodes": [], "edges": [], "clusters": []}
    plan = build_explain_plan("job1", [g])
    by_slide = {1: g}
    evidence_items = [
        {
            "evidence_id": "ev_cap",
            "kind": "IMAGE_CAPTION",
            "content": "A football on the field.",
            "slide_index": 1,
            "confidence": 0.85,
        },
    ]
    evidence_index = {"evidence_items": evidence_items}
    bundle = build_context_bundle(1, "Title", "", g, evidence_items)
    stub = StubLLMProvider()
    script = generate_script(
        "job1",
        plan,
        by_slide,
        evidence_index,
        {},
        stub,
        context_bundles_by_slide={1: bundle},
    )
    intro_seg = next(s for s in script["segments"] if s["slide_index"] == 1)
    assert "football" in intro_seg["text"].lower()
    assert "ev_cap" in intro_seg["evidence_ids"]
    assert intro_seg.get("used_hedging") is False


def test_script_with_context_bundle_generic():
    """With context bundle (generic), intro segment has generic text and used_hedging."""
    from script_context import build_context_bundle

    g = {"slide_index": 1, "nodes": [], "edges": [], "clusters": []}
    plan = build_explain_plan("job1", [g])
    by_slide = {1: g}
    evidence_items = [
        {
            "evidence_id": "ev_lo",
            "kind": "IMAGE_CAPTION",
            "content": "Unclear.",
            "slide_index": 1,
            "confidence": 0.2,
        },
    ]
    evidence_index = {"evidence_items": evidence_items}
    bundle = build_context_bundle(1, "", "", g, evidence_items)
    bundle["_policy"] = "generic"
    stub = StubLLMProvider()
    script = generate_script(
        "job1",
        plan,
        by_slide,
        evidence_index,
        {},
        stub,
        context_bundles_by_slide={1: bundle},
    )
    intro_seg = next(s for s in script["segments"] if s["slide_index"] == 1)
    assert (
        "could not be extracted" in intro_seg["text"].lower()
        or "image or diagram" in intro_seg["text"].lower()
    )
    assert intro_seg.get("used_hedging") is True


def test_rag_tfidf_retrieve():
    """RAG hook: tf-idf retrieves chunk ids."""
    chunks = [{"id": "c1", "text": "hello world"}, {"id": "c2", "text": "world peace"}]
    ids = retrieve_chunk_ids("world", chunks, top_k=2)
    assert len(ids) <= 2
    assert all(isinstance(x, str) for x in ids)
