"""Regression test for the script-generator evidence-selection priority bug.

Before the fix, when a slide had both a high-confidence SLIDE_CAPTION and a
low-confidence DIAGRAM_SUMMARY, the stub provider would pick whichever came
first in the items list. That produced narration like:

    "This slide shows a diagram with key elements: Win2k, Service, Packs."

even though a 0.95-confidence caption was available:

    "The bar graph illustrates the number of service packs for Win2k over time..."

The fix is in llm_provider.StubLLMProvider.generate_segment: when a
SLIDE_CAPTION (or IMAGE_CAPTION) item has confidence >= 0.8, it wins
regardless of its position in the items list.
"""
from __future__ import annotations

from packages.core import llm_provider


def _bundle(items, tier="high"):
    return {
        "_policy": "image_evidence",
        "_use_hedging": False,
        "image_evidence_items": items,
        "narration_tier": tier,
        "slide_text": "",
        "notes": "",
    }


def test_high_conf_slide_caption_wins_over_diagram_summary():
    provider = llm_provider.StubLLMProvider()
    items = [
        # DIAGRAM_SUMMARY first in the list, low confidence
        {"evidence_id": "d1", "kind": "DIAGRAM_SUMMARY",
         "content": "The diagram appears to show: Win2k, Service, Packs.",
         "confidence": 0.4},
        # SLIDE_CAPTION second, high confidence — should win anyway
        {"evidence_id": "c1", "kind": "SLIDE_CAPTION",
         "content": "The bar graph illustrates the number of service packs for Win2k over time.",
         "confidence": 0.95},
    ]
    text = provider.generate_segment(
        section={"section_type": "intro", "slide_index": 8},
        graph={"nodes": [], "edges": [], "clusters": []},
        evidence_ids=["c1", "d1"],
        entity_ids=[],
        context_bundle=_bundle(items, tier="high"),
    )
    assert "bar graph" in text.lower()
    assert "service packs" in text.lower()
    # Must NOT contain the low-confidence diagram-summary phrasing
    assert "appears to show: Win2k" not in text


def test_low_conf_caption_does_not_override_diagram_summary():
    """If the caption is below the high-confidence threshold, fall back to
    the original first-wins behavior."""
    provider = llm_provider.StubLLMProvider()
    items = [
        {"evidence_id": "d1", "kind": "DIAGRAM_SUMMARY",
         "content": "The diagram shows network topology.",
         "confidence": 0.6},
        {"evidence_id": "c1", "kind": "SLIDE_CAPTION",
         "content": "Possibly a logo or screenshot.",
         "confidence": 0.5},
    ]
    text = provider.generate_segment(
        section={"section_type": "intro", "slide_index": 1},
        graph={"nodes": [], "edges": [], "clusters": []},
        evidence_ids=["d1", "c1"],
        entity_ids=[],
        context_bundle=_bundle(items, tier="medium"),
    )
    assert "network topology" in text.lower()


def test_high_conf_image_caption_also_wins():
    """IMAGE_CAPTION is treated the same as SLIDE_CAPTION for priority."""
    provider = llm_provider.StubLLMProvider()
    items = [
        {"evidence_id": "d1", "kind": "DIAGRAM_SUMMARY",
         "content": "Generic diagram description.",
         "confidence": 0.4},
        {"evidence_id": "c1", "kind": "IMAGE_CAPTION",
         "content": "A photograph of three engineers reviewing a printout.",
         "confidence": 0.9},
    ]
    text = provider.generate_segment(
        section={"section_type": "intro", "slide_index": 1},
        graph={"nodes": [], "edges": [], "clusters": []},
        evidence_ids=["c1"],
        entity_ids=[],
        context_bundle=_bundle(items, tier="high"),
    )
    assert "photograph" in text.lower()
    assert "engineers" in text.lower()
