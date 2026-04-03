"""
Day 2 integration test: script segment cites IMAGE_CAPTION evidence_id and narration contains caption (or derived phrase).
Uses mocked evidence index (no real OpenAI); asserts no image facts without evidence.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from script_context import build_context_bundles_per_slide, narration_policy
from script_generator import generate_script
from llm_provider import StubLLMProvider


# Known caption from "mocked" vision provider for test
MOCK_CAPTION = "A football on the grass."
MOCK_EVIDENCE_ID = "ev-caption-football-1"


def test_script_segment_cites_image_caption_and_contains_phrase():
    """
    With evidence_index containing one IMAGE_CAPTION (known caption), script generation produces
    a segment whose text contains the caption (or derived phrase) and whose evidence_ids include that evidence_id.
    """
    job_id = "test-job-day2"
    evidence_index = {
        "schema_version": "1.0",
        "job_id": job_id,
        "evidence_items": [
            {
                "evidence_id": MOCK_EVIDENCE_ID,
                "kind": "IMAGE_CAPTION",
                "content": MOCK_CAPTION,
                "confidence": 0.9,
                "slide_index": 1,
                "reason_code": None,
            },
        ],
        "sources": [],
    }

    explain_plan = {
        "sections": [
            {"slide_index": 1, "section_type": "intro", "entity_ids": [], "evidence_ids": []},
        ],
        "ordering": ["intro"],
    }

    unified_graphs_by_slide = {1: {"nodes": [], "edges": [], "clusters": []}}
    slides_notes_and_text = [("", "Slide 1")]  # No notes so policy will use image_evidence

    context_bundles = build_context_bundles_per_slide(
        1,
        slides_notes_and_text,
        unified_graphs_by_slide,
        evidence_index,
    )
    bundle = context_bundles.get(1)
    assert bundle is not None
    policy, cite_ids, _ = narration_policy(bundle)
    assert policy == "image_evidence", f"expected image_evidence, got {policy}"
    assert MOCK_EVIDENCE_ID in cite_ids, f"expected {MOCK_EVIDENCE_ID} in cite_ids {cite_ids}"

    script = generate_script(
        job_id=job_id,
        explain_plan=explain_plan,
        unified_graphs_by_slide=unified_graphs_by_slide,
        evidence_index=evidence_index,
        entity_to_evidence={},
        llm_provider=StubLLMProvider(),
        context_bundles_by_slide=context_bundles,
        slides_notes_and_text=slides_notes_and_text,
    )

    segments = script.get("segments", [])
    assert len(segments) >= 1, "expected at least one segment"
    seg = segments[0]
    assert seg["slide_index"] == 1
    text = (seg.get("text") or "").strip()
    evidence_ids = list(seg.get("evidence_ids") or [])

    assert MOCK_EVIDENCE_ID in evidence_ids, (
        f"Segment must cite IMAGE_CAPTION evidence_id; got evidence_ids={evidence_ids}"
    )
    # Narration should contain the caption or a clear derived phrase (stub uses content verbatim or with prefix)
    assert "football" in text.lower() or "grass" in text.lower(), (
        f"Narration must contain caption-derived phrase; got text={text!r}"
    )
