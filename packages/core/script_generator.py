"""
Script generator (Fig3 step 11). Prompt 5: image evidence + safe phrasing.
Generates script/script.json (draft) with segments: claim_id, slide_index, text,
evidence_ids[], entity_ids[], used_hedging. Narrates from notes or image evidence only.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_provider import LLMProvider

try:
    from script_context import build_context_bundles_per_slide, narration_policy
except ImportError:
    build_context_bundles_per_slide = None  # type: ignore
    narration_policy = None  # type: ignore


def _claim_id(job_id: str, slide_index: int, segment_ix: int) -> str:
    """Stable claim_id for a segment."""
    payload = f"{job_id}|{slide_index}|{segment_ix}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_script(
    job_id: str,
    explain_plan: Dict[str, Any],
    unified_graphs_by_slide: Dict[int, Dict[str, Any]],
    evidence_index: Dict[str, Any],
    entity_to_evidence: Dict[str, List[str]],
    llm_provider: "LLMProvider",
    rag_snippets_by_slide: Optional[Dict[int, List[str]]] = None,
    context_bundles_by_slide: Optional[Dict[int, Dict[str, Any]]] = None,
    slides_notes_and_text: Optional[List[tuple]] = None,
) -> Dict[str, Any]:
    """
    Generate script segments from explain_plan. Every segment has claim_id, slide_index,
    text, evidence_ids[], entity_ids[], used_hedging. Safe phrasing: notes primary; else
    image evidence (high confidence); else generic. Image-derived claims cite IMAGE_* or DIAGRAM_*.
    """
    sections = explain_plan.get("sections", [])
    segments: List[Dict[str, Any]] = []
    rag_snippets_by_slide = rag_snippets_by_slide or {}
    context_bundles_by_slide = context_bundles_by_slide or {}

    # Build context bundles if not provided but we have slides data
    if (
        not context_bundles_by_slide
        and build_context_bundles_per_slide
        and slides_notes_and_text is not None
    ):
        slide_count = max((s.get("slide_index", 0) for s in sections), default=0) or len(
            slides_notes_and_text
        )
        context_bundles_by_slide = build_context_bundles_per_slide(
            slide_count, slides_notes_and_text, unified_graphs_by_slide, evidence_index
        )

    for ix, section in enumerate(sections):
        slide_index = section.get("slide_index", 0)
        entity_ids = list(section.get("entity_ids") or [])
        plan_evidence_ids = list(section.get("evidence_ids") or [])

        # Resolve evidence_ids from entity_to_evidence (EntityLink in DB)
        evidence_ids_set: set = set(plan_evidence_ids)
        for eid in entity_ids:
            evidence_ids_set.update(entity_to_evidence.get(eid, []))
        evidence_ids = list(evidence_ids_set)

        section_type = section.get("section_type", "")
        # Apply safe-phrasing policy (notes / image evidence / generic) only to intro segment per slide
        context_bundle = (
            context_bundles_by_slide.get(slide_index) if section_type == "intro" else None
        )
        policy_override: Optional[str] = None
        used_hedging = False

        if context_bundle and narration_policy and section_type == "intro":
            policy, cite_ids, hedging = narration_policy(context_bundle)
            policy_override = policy
            if policy == "notes":
                if not evidence_ids:
                    for ev in evidence_index.get("evidence_items", []):
                        if ev.get("slide_index") == slide_index and ev.get("evidence_id"):
                            evidence_ids.append(ev["evidence_id"])
                            if len(evidence_ids) >= 3:
                                break
                context_bundle["_policy"] = "notes"
            elif policy == "image_evidence":
                evidence_ids = list(set(evidence_ids) | set(cite_ids))
                used_hedging = hedging
                context_bundle["_policy"] = "image_evidence"
                context_bundle["_use_hedging"] = hedging
            elif policy == "generic":
                # Cite one image evidence if any (so verifier sees evidence_ids); text stays generic
                evidence_ids = list(cite_ids) if cite_ids else []
                if not evidence_ids:
                    for ev in context_bundle.get("image_evidence_items") or []:
                        if ev.get("evidence_id"):
                            evidence_ids.append(ev["evidence_id"])
                            break
                used_hedging = True
                context_bundle["_policy"] = "generic"

        if not context_bundle or policy_override is None:
            # Grounding: ensure every segment has at least one citation when no context policy
            if not evidence_ids and not entity_ids:
                evidence_items = evidence_index.get("evidence_items", [])
                for ev in evidence_items:
                    if ev.get("slide_index") == slide_index:
                        evidence_ids.append(ev.get("evidence_id"))
                        if len(evidence_ids) >= 1:
                            break
            context_bundle = None

        graph = unified_graphs_by_slide.get(slide_index, {"nodes": [], "edges": [], "clusters": []})
        rag_snippets = rag_snippets_by_slide.get(slide_index, [])

        text = llm_provider.generate_segment(
            section=section,
            graph=graph,
            evidence_ids=evidence_ids,
            entity_ids=entity_ids,
            rag_snippets=rag_snippets if rag_snippets else None,
            context_bundle=context_bundle,
        )

        claim_id = _claim_id(job_id, slide_index, ix)
        segments.append(
            {
                "claim_id": claim_id,
                "slide_index": slide_index,
                "text": text,
                "evidence_ids": evidence_ids,
                "entity_ids": entity_ids,
                "used_hedging": used_hedging,
            }
        )

    script = {
        "schema_version": "1.0",
        "job_id": job_id,
        "draft": True,
        "segments": segments,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    return script
