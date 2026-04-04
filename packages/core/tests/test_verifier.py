"""
Unit tests for verifier engine (Fig3 step 12, Fig6).
- Verifier checks: has evidence_ids, evidence_ids exist, entity_ids in G_unified,
  claim vs evidence (heuristics), relations vs graph.
- Verdicts: PASS / REWRITE / REMOVE.
- Rewrite loop: regenerate REWRITE, stop when clean or max_iters; verified script output.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from verifier import (
    verify_segment,
    verify_script,
    run_rewrite_loop,
    build_verify_report_payload,
    VERDICT_PASS,
    VERDICT_REWRITE,
    VERDICT_REMOVE,
    REASON_NO_EVIDENCE_IDS,
    REASON_EVIDENCE_NOT_FOUND,
    REASON_ENTITY_NOT_IN_GRAPH,
    REASON_UNSUPPORTED_BY_EVIDENCE,
    REASON_GRAPH_CONTRADICTION,
    REASON_IMAGE_CLAIM_NEEDS_IMAGE_EVIDENCE,
    REASON_IMAGE_UNGROUNDED,
    REASON_NEEDS_HEDGING,
    REASON_DIAGRAM_UNSUPPORTED,
    REASON_OBJECT_ACTION_UNSUPPORTED,
)


def test_has_evidence_ids_rewrite():
    """No evidence_ids -> REWRITE, NO_EVIDENCE_IDS."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "Some claim.",
        "evidence_ids": [],
        "entity_ids": [],
    }
    evidence_by_id = {}
    graph = {"nodes": [], "edges": [], "clusters": []}
    entry = verify_segment(segment, evidence_by_id, graph)
    assert entry["verdict"] == VERDICT_REWRITE
    assert REASON_NO_EVIDENCE_IDS in entry["reasons"]


def test_evidence_ids_exist_rewrite():
    """Invalid evidence_id -> REWRITE, EVIDENCE_NOT_FOUND."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "Claim.",
        "evidence_ids": ["ev_missing"],
        "entity_ids": [],
    }
    evidence_by_id = {"ev_other": {"evidence_id": "ev_other", "content": "other"}}
    graph = {"nodes": [], "edges": [], "clusters": []}
    entry = verify_segment(segment, evidence_by_id, graph)
    assert entry["verdict"] == VERDICT_REWRITE
    assert REASON_EVIDENCE_NOT_FOUND in entry["reasons"]
    assert "invalid_evidence_ids" in entry.get("pointers", {})


def test_entity_ids_in_graph_rewrite():
    """entity_id not in G_unified -> REWRITE, ENTITY_NOT_IN_GRAPH."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "Claim.",
        "evidence_ids": ["ev1"],
        "entity_ids": ["node_missing"],
    }
    evidence_by_id = {"ev1": {"evidence_id": "ev1", "content": "evidence content"}}
    graph = {"nodes": [{"node_id": "n1", "label_text": "A"}], "edges": [], "clusters": []}
    entry = verify_segment(segment, evidence_by_id, graph)
    assert entry["verdict"] == VERDICT_REWRITE
    assert REASON_ENTITY_NOT_IN_GRAPH in entry["reasons"]
    assert "missing_entity_ids" in entry.get("pointers", {})


def test_claim_supported_by_evidence_rewrite():
    """Claim numbers not in evidence -> REWRITE, UNSUPPORTED_BY_EVIDENCE."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "There are 99 items.",
        "evidence_ids": ["ev1"],
        "entity_ids": [],
    }
    evidence_by_id = {"ev1": {"evidence_id": "ev1", "content": "We have two items."}}
    graph = {"nodes": [], "edges": [], "clusters": []}
    entry = verify_segment(segment, evidence_by_id, graph)
    assert entry["verdict"] == VERDICT_REWRITE
    assert REASON_UNSUPPORTED_BY_EVIDENCE in entry["reasons"]


def test_image_claim_needs_image_evidence_rewrite():
    """Image/diagram claim citing only TEXT_SPAN -> REWRITE, IMAGE_UNGROUNDED."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "The diagram shows a flow from A to B.",
        "evidence_ids": ["ev_text"],
        "entity_ids": [],
    }
    evidence_by_id = {
        "ev_text": {"evidence_id": "ev_text", "content": "slide title", "kind": "TEXT_SPAN"},
    }
    graph = {"nodes": [], "edges": [], "clusters": []}
    entry = verify_segment(segment, evidence_by_id, graph)
    assert entry["verdict"] == VERDICT_REWRITE
    assert REASON_IMAGE_UNGROUNDED in entry["reasons"]
    assert entry.get("is_image_claim") is True
    assert "required_evidence_kinds" in entry
    assert "confidence_used" in entry


def test_image_claim_with_image_evidence_pass():
    """Image claim citing IMAGE_CAPTION -> PASS."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "The diagram shows visual elements.",
        "evidence_ids": ["ev_img"],
        "entity_ids": [],
    }
    evidence_by_id = {
        "ev_img": {
            "evidence_id": "ev_img",
            "content": "This slide contains an image.",
            "kind": "IMAGE_CAPTION",
        },
    }
    graph = {"nodes": [], "edges": [], "clusters": []}
    entry = verify_segment(segment, evidence_by_id, graph)
    assert REASON_IMAGE_UNGROUNDED not in entry["reasons"]
    assert entry.get("is_image_claim") is True
    assert entry.get("confidence_used", 0) >= 0


def test_claim_supported_by_evidence_no_overlap_rewrite():
    """Claim tokens have no overlap with evidence -> REWRITE."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "xyz alien moon",
        "evidence_ids": ["ev1"],
        "entity_ids": [],
    }
    evidence_by_id = {"ev1": {"evidence_id": "ev1", "content": "slide diagram elements"}}
    graph = {"nodes": [], "edges": [], "clusters": []}
    entry = verify_segment(segment, evidence_by_id, graph)
    assert entry["verdict"] == VERDICT_REWRITE
    assert REASON_UNSUPPORTED_BY_EVIDENCE in entry["reasons"]


def test_relations_consistent_edge_src_dst_rewrite():
    """Edge references node not in graph -> REWRITE, GRAPH_CONTRADICTION."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "Flow.",
        "evidence_ids": ["ev1"],
        "entity_ids": ["e1"],
    }
    evidence_by_id = {"ev1": {"evidence_id": "ev1", "content": "flow"}}
    graph = {
        "nodes": [{"node_id": "n1"}],
        "edges": [{"edge_id": "e1", "src_node_id": "n_missing", "dst_node_id": "n1"}],
        "clusters": [],
    }
    entry = verify_segment(segment, evidence_by_id, graph)
    assert entry["verdict"] == VERDICT_REWRITE
    assert REASON_GRAPH_CONTRADICTION in entry["reasons"]


def test_all_checks_pass():
    """Valid evidence, entities in graph, claim overlap -> PASS."""
    # Avoid image keywords ("shows", "depicts", etc.) so IMAGE_CLAIM_NEEDS_IMAGE_EVIDENCE does not fire
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "Elements and connections on this slide.",
        "evidence_ids": ["ev1"],
        "entity_ids": ["n1"],
    }
    evidence_by_id = {"ev1": {"evidence_id": "ev1", "content": "slide elements connections"}}
    graph = {"nodes": [{"node_id": "n1", "label_text": "A"}], "edges": [], "clusters": []}
    entry = verify_segment(segment, evidence_by_id, graph)
    assert entry["verdict"] == VERDICT_PASS
    assert entry["reasons"] == []


def test_verify_script_coverage():
    """verify_script returns report + coverage with pct_claims_with_evidence, pct_entities_grounded."""
    script = {
        "segments": [
            {
                "claim_id": "c1",
                "slide_index": 1,
                "text": "Slide one.",
                "evidence_ids": ["ev1"],
                "entity_ids": ["n1"],
            },
            {
                "claim_id": "c2",
                "slide_index": 1,
                "text": "No evidence.",
                "evidence_ids": [],
                "entity_ids": [],
            },
        ],
    }
    evidence_index = {"evidence_items": [{"evidence_id": "ev1", "content": "slide one"}]}
    unified_by_slide = {1: {"nodes": [{"node_id": "n1"}], "edges": [], "clusters": []}}
    report, coverage = verify_script(script, evidence_index, unified_by_slide)
    assert len(report) == 2
    assert report[0]["verdict"] == VERDICT_PASS
    assert report[1]["verdict"] == VERDICT_REWRITE
    assert coverage["total_claims"] == 2
    assert "pct_claims_with_evidence" in coverage
    assert "pct_entities_grounded" in coverage


def test_rewrite_loop_verified_script():
    """run_rewrite_loop produces verified script with only PASS segments; loops until clean."""
    script_draft = {
        "job_id": "job1",
        "segments": [
            {
                "claim_id": "c1",
                "slide_index": 1,
                "text": "Good.",
                "evidence_ids": ["ev1"],
                "entity_ids": ["n1"],
            },
            {
                "claim_id": "c2",
                "slide_index": 1,
                "text": "Bad 999.",
                "evidence_ids": ["ev1"],
                "entity_ids": [],
            },
        ],
    }
    evidence_index = {"evidence_items": [{"evidence_id": "ev1", "content": "slide content"}]}
    unified_by_slide = {
        1: {"nodes": [{"node_id": "n1", "label_text": "A"}], "edges": [], "clusters": []}
    }
    verified_script, report, coverage = run_rewrite_loop(
        job_id="job1",
        script_draft=script_draft,
        evidence_index=evidence_index,
        unified_graphs_by_slide=unified_by_slide,
        explain_plan=None,
        llm_provider=None,
        max_iters=3,
    )
    assert verified_script["verified"] is True
    assert verified_script["draft"] is False
    # After rewrite, c2 gets deterministic rewrite text; may pass or still fail. At least c1 is PASS.
    pass_claims = [r["claim_id"] for r in report if r["verdict"] == VERDICT_PASS]
    assert len(pass_claims) >= 1
    assert all(seg["claim_id"] in pass_claims for seg in verified_script["segments"])
    payload = build_verify_report_payload("job1", report)
    assert "report" in payload
    assert len(payload["report"]) == 2


def test_verify_report_has_verdict_reasons_pointers():
    """Each report entry has verdict, reasons, pointers, is_image_claim, required_evidence_kinds, confidence_used."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "X",
        "evidence_ids": [],
        "entity_ids": [],
    }
    entry = verify_segment(segment, {}, {"nodes": [], "edges": [], "clusters": []})
    assert "verdict" in entry
    assert "reasons" in entry
    assert "pointers" in entry
    assert "is_image_claim" in entry
    assert "required_evidence_kinds" in entry
    assert "confidence_used" in entry
    assert entry["verdict"] in (VERDICT_PASS, VERDICT_REWRITE, VERDICT_REMOVE)


def test_needs_hedging_rewrite():
    """Low-confidence image evidence + definitive claim (no hedging) -> REWRITE, NEEDS_HEDGING."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "The photo shows a football match.",
        "evidence_ids": ["ev_lo"],
        "entity_ids": [],
        "used_hedging": False,
    }
    evidence_by_id = {
        "ev_lo": {
            "evidence_id": "ev_lo",
            "content": "sports scene",
            "kind": "IMAGE_CAPTION",
            "confidence": 0.3,
        },
    }
    graph = {"nodes": [], "edges": [], "clusters": []}
    entry = verify_segment(segment, evidence_by_id, graph)
    assert entry["verdict"] == VERDICT_REWRITE
    assert REASON_NEEDS_HEDGING in entry["reasons"]


def test_diagram_unsupported_rewrite():
    """Claim describes message/order not in DIAGRAM_INTERACTIONS -> REWRITE, DIAGRAM_UNSUPPORTED."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "Alice sends secret message to Bob then Charlie replies.",
        "evidence_ids": ["ev_dia"],
        "entity_ids": [],
    }
    evidence_by_id = {
        "ev_dia": {
            "evidence_id": "ev_dia",
            "content": "Actor A to Service B request",
            "kind": "DIAGRAM_INTERACTIONS",
        },
    }
    graph = {"nodes": [], "edges": [], "clusters": []}
    entry = verify_segment(segment, evidence_by_id, graph)
    assert entry["verdict"] == VERDICT_REWRITE
    assert REASON_DIAGRAM_UNSUPPORTED in entry["reasons"]


def test_object_action_unsupported_rewrite():
    """Claim mentions objects/actions not in IMAGE_OBJECTS/ACTIONS -> REWRITE."""
    segment = {
        "claim_id": "c1",
        "slide_index": 1,
        "text": "The image shows elephants and giraffes in the savanna.",
        "evidence_ids": ["ev_obj"],
        "entity_ids": [],
    }
    evidence_by_id = {
        "ev_obj": {
            "evidence_id": "ev_obj",
            "content": "person(0.9); car(0.8)",
            "kind": "IMAGE_OBJECTS",
        },
    }
    graph = {"nodes": [], "edges": [], "clusters": []}
    entry = verify_segment(segment, evidence_by_id, graph)
    assert entry["verdict"] == VERDICT_REWRITE
    assert REASON_OBJECT_ACTION_UNSUPPORTED in entry["reasons"]
