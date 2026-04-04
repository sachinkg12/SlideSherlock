"""
Tests for script context bundle and safe-phrasing policy (Prompt 5).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from script_context import (
    build_context_bundle,
    build_context_bundles_per_slide,
    narration_policy,
)


def test_build_context_bundle_includes_image_evidence():
    """Context bundle includes image evidence items with evidence_id and confidence."""
    evidence_items = [
        {
            "evidence_id": "ev_cap",
            "kind": "IMAGE_CAPTION",
            "content": "A football on grass.",
            "slide_index": 1,
            "confidence": 0.9,
        },
        {
            "evidence_id": "ev_dia",
            "kind": "DIAGRAM_SUMMARY",
            "content": "Actor A sends request to B.",
            "slide_index": 1,
            "confidence": 0.7,
        },
    ]
    bundle = build_context_bundle(1, "Slide title", "", {"nodes": [], "edges": []}, evidence_items)
    assert bundle["slide_index"] == 1
    assert len(bundle["image_evidence_items"]) == 2
    by_kind = {e["kind"]: e for e in bundle["image_evidence_items"]}
    assert by_kind["IMAGE_CAPTION"]["evidence_id"] == "ev_cap"
    assert by_kind["IMAGE_CAPTION"]["content"] == "A football on grass."
    assert by_kind["IMAGE_CAPTION"]["confidence"] == 0.9


def test_narration_policy_notes_primary():
    """When notes have enough words, policy is notes."""
    bundle = {
        "notes": "These are speaker notes with enough words for primary narrative.",
        "image_evidence_items": [{"evidence_id": "ev1", "confidence": 0.9}],
    }
    policy, cite_ids, hedging = narration_policy(bundle)
    assert policy == "notes"
    assert hedging is False


def test_narration_policy_image_evidence_high_conf():
    """When no notes and image evidence high confidence, policy is image_evidence."""
    bundle = {
        "notes": "",
        "image_evidence_items": [
            {
                "evidence_id": "ev_cap",
                "kind": "IMAGE_CAPTION",
                "content": "Football.",
                "confidence": 0.8,
            },
        ],
        "image_evidence_max_confidence": 0.8,
    }
    policy, cite_ids, hedging = narration_policy(bundle)
    assert policy == "image_evidence"
    assert "ev_cap" in cite_ids
    assert hedging is False


def test_narration_policy_generic_low_conf():
    """When image evidence low confidence, policy is generic and use_hedging True."""
    bundle = {
        "notes": "",
        "image_evidence_items": [
            {
                "evidence_id": "ev_lo",
                "kind": "IMAGE_CAPTION",
                "content": "Blurry.",
                "confidence": 0.3,
            },
        ],
        "image_evidence_max_confidence": 0.3,
    }
    policy, cite_ids, hedging = narration_policy(bundle)
    assert policy == "generic"
    assert hedging is True


def test_build_context_bundles_per_slide():
    """Build bundles for all slides; filter evidence by slide_index."""
    evidence_items = [
        {
            "evidence_id": "e1",
            "kind": "IMAGE_CAPTION",
            "content": "First.",
            "slide_index": 1,
            "confidence": 0.8,
        },
        {
            "evidence_id": "e2",
            "kind": "DIAGRAM_SUMMARY",
            "content": "Second.",
            "slide_index": 2,
            "confidence": 0.7,
        },
    ]
    bundles = build_context_bundles_per_slide(
        2,
        [("Notes one", "Text one"), ("", "Text two")],
        {1: {"nodes": []}, 2: {"nodes": []}},
        {"evidence_items": evidence_items},
    )
    assert bundles[1]["notes"] == "Notes one"
    assert len(bundles[1]["image_evidence_items"]) == 1
    assert bundles[2]["image_evidence_items"][0]["evidence_id"] == "e2"
