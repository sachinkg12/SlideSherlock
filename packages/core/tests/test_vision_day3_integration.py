"""
Day 3 integration test: meaningful diagram/photo narration, verifier allows hedged medium, timeline image actions.
Uses mocked evidence (PHOTO caption 'Students playing football', DIAGRAM interactions); no external APIs.
Asserts: narration has specifics (football; actor/message flow), correct evidence citations, 0 REWRITE, timeline HIGHLIGHT/ZOOM.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from script_context import build_context_bundles_per_slide, narration_policy
from script_generator import generate_script
from llm_provider import StubLLMProvider
from verifier import verify_script, VERDICT_REWRITE
from timeline_builder import build_timeline, ACTION_HIGHLIGHT, ACTION_ZOOM


# Mock evidence for slide 1: PHOTO + DIAGRAM
MOCK_PHOTO_CAPTION = "Students playing football"
MOCK_PHOTO_EVIDENCE_ID = "ev-photo-caption-1"
MOCK_DIAGRAM_INTERACTIONS_ID = "ev-diagram-interactions-1"
MOCK_IMAGE_URI = "jobs/test-job-day3/images/slide_001/img_00.png"
MOCK_IMAGE_ID = "img_s1_0"


def _mock_evidence_index_with_photo_and_diagram():
    return {
        "schema_version": "1.0",
        "job_id": "test-job-day3",
        "evidence_items": [
            {
                "evidence_id": MOCK_PHOTO_EVIDENCE_ID,
                "kind": "IMAGE_CAPTION",
                "content": MOCK_PHOTO_CAPTION,
                "confidence": 0.85,
                "slide_index": 1,
                "refs": [
                    {
                        "ref_type": "IMAGE",
                        "slide_index": 1,
                        "url": MOCK_IMAGE_URI,
                        "image_uri": MOCK_IMAGE_URI,
                        "bbox_x": 100000,
                        "bbox_y": 100000,
                        "bbox_w": 2000000,
                        "bbox_h": 1500000,
                    },
                ],
            },
            {
                "evidence_id": MOCK_DIAGRAM_INTERACTIONS_ID,
                "kind": "DIAGRAM_INTERACTIONS",
                "content": "1:User->API:request; 2:API->DB:query; 3:DB->API:result",
                "confidence": 0.6,
                "slide_index": 1,
                "refs": [
                    {
                        "ref_type": "IMAGE",
                        "slide_index": 1,
                        "url": MOCK_IMAGE_URI,
                        "image_uri": MOCK_IMAGE_URI,
                        "bbox_x": 100000,
                        "bbox_y": 100000,
                        "bbox_w": 2000000,
                        "bbox_h": 1500000,
                    },
                ],
            },
        ],
        "sources": [],
    }


def _mock_images_index():
    return {
        "schema_version": "1.0",
        "job_id": "test-job-day3",
        "images": [
            {
                "image_id": MOCK_IMAGE_ID,
                "slide_index": 1,
                "uri": MOCK_IMAGE_URI,
                "bbox": {"x": 100000, "y": 100000, "w": 2000000, "h": 1500000},
            },
        ],
    }


def test_narration_includes_meaningful_specifics_and_cites_evidence():
    """Script segment for slide with PHOTO caption: narration includes 'football' and cites IMAGE_CAPTION."""
    job_id = "test-job-day3"
    evidence_index = _mock_evidence_index_with_photo_and_diagram()
    # Use only PHOTO for this test so policy picks image_evidence and stub uses caption
    evidence_index["evidence_items"] = [e for e in evidence_index["evidence_items"] if e["kind"] == "IMAGE_CAPTION"]

    explain_plan = {
        "sections": [
            {"slide_index": 1, "section_type": "intro", "entity_ids": [], "evidence_ids": []},
        ],
        "ordering": ["intro"],
    }
    unified_graphs_by_slide = {1: {"nodes": [], "edges": [], "clusters": []}}
    slides_notes_and_text = [("", "Slide 1")]

    context_bundles = build_context_bundles_per_slide(
        1, slides_notes_and_text, unified_graphs_by_slide, evidence_index
    )
    policy, cite_ids, _ = narration_policy(context_bundles[1])
    assert policy == "image_evidence"
    assert MOCK_PHOTO_EVIDENCE_ID in cite_ids

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
    assert len(segments) >= 1
    text = (segments[0].get("text") or "").strip().lower()
    evidence_ids = list(segments[0].get("evidence_ids") or [])
    assert "football" in text, f"Narration must include meaningful specific 'football'; got {text!r}"
    assert MOCK_PHOTO_EVIDENCE_ID in evidence_ids, f"Segment must cite IMAGE_CAPTION; got {evidence_ids}"


def test_diagram_interactions_step_by_step_and_verifier_zero_rewrite():
    """Slide with DIAGRAM_INTERACTIONS (medium+ conf): step-by-step narration, verifier ends with 0 REWRITE."""
    job_id = "test-job-day3"
    evidence_index = _mock_evidence_index_with_photo_and_diagram()
    # Prefer diagram evidence for this test
    explain_plan = {
        "sections": [
            {"slide_index": 1, "section_type": "intro", "entity_ids": [], "evidence_ids": []},
        ],
        "ordering": ["intro"],
    }
    unified_graphs_by_slide = {1: {"nodes": [], "edges": [], "clusters": []}}
    slides_notes_and_text = [("", "Slide 1")]

    context_bundles = build_context_bundles_per_slide(
        1, slides_notes_and_text, unified_graphs_by_slide, evidence_index
    )
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
    assert len(segments) >= 1
    text = (segments[0].get("text") or "").strip()
    evidence_ids = list(segments[0].get("evidence_ids") or [])
    # Stub uses DIAGRAM_INTERACTIONS when present with conf >= 0.45 -> step-by-step
    assert "Step" in text or "sends" in text or "User" in text or "API" in text or "request" in text.lower(), (
        f"Narration should reflect diagram interactions; got {text!r}"
    )
    assert any(
        eid in evidence_ids for eid in [MOCK_PHOTO_EVIDENCE_ID, MOCK_DIAGRAM_INTERACTIONS_ID]
    ), f"Segment must cite image/diagram evidence; got {evidence_ids}"

    # Verifier: should PASS when claim cites image evidence and is hedged or high conf
    report, _ = verify_script(script, evidence_index, unified_graphs_by_slide)
    rewrite_count = sum(1 for r in report if r.get("verdict") == VERDICT_REWRITE)
    assert rewrite_count == 0, (
        f"Verifier must end with 0 REWRITE when narration is grounded and appropriately hedged; got {rewrite_count} rewrites: {report}"
    )


def test_timeline_includes_highlight_or_zoom_for_image_entity():
    """When script segment cites image/diagram evidence, timeline has HIGHLIGHT or ZOOM for image entity."""
    job_id = "test-job-day3"
    evidence_index = _mock_evidence_index_with_photo_and_diagram()
    images_index = _mock_images_index()
    explain_plan = {
        "sections": [
            {"slide_index": 1, "section_type": "intro", "entity_ids": [], "evidence_ids": [MOCK_PHOTO_EVIDENCE_ID]},
        ],
        "ordering": ["intro"],
    }
    unified_graphs_by_slide = {1: {"nodes": [], "edges": [], "clusters": []}}
    slides_notes_and_text = [("", "Slide 1")]
    context_bundles = build_context_bundles_per_slide(
        1, slides_notes_and_text, unified_graphs_by_slide, evidence_index
    )
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
    alignment = {"segments": [{"claim_id": script["segments"][0]["claim_id"], "t_start": 0, "t_end": 3}]}
    slide_dimensions = {1: (1280, 720)}
    timeline = build_timeline(
        job_id,
        script,
        alignment,
        unified_graphs_by_slide,
        slide_dimensions,
        images_index=images_index,
        evidence_index=evidence_index,
    )
    actions = timeline.get("actions", [])
    assert len(actions) >= 1
    image_actions = [
        a for a in actions
        if a.get("type") in (ACTION_HIGHLIGHT, ACTION_ZOOM)
        and any(
            (eid or "").startswith("image:IMG_")
            for eid in (a.get("entity_ids") or [])
        )
    ]
    assert len(image_actions) >= 1, (
        f"Timeline must include at least one HIGHLIGHT or ZOOM for image entity; got actions={actions}"
    )
    a = image_actions[0]
    assert a.get("claim_id")
    assert a.get("evidence_ids")
    assert "bbox" in a or "path" in a
