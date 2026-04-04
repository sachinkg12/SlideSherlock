"""
Per-slide context bundle for script generation (Prompt 5).
Includes: slide text, notes, G_unified summary, image evidence items (photo + diagram) with evidence_id and confidence.
Used to enforce safe phrasing: narrate from notes or image evidence only; no hallucination.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Image evidence kinds that may be used for narration (photo + diagram + slide fallback)
IMAGE_EVIDENCE_KINDS = frozenset(
    {
        "IMAGE_CAPTION",
        "IMAGE_OBJECTS",
        "IMAGE_ACTIONS",
        "IMAGE_TAGS",
        "DIAGRAM_TYPE",
        "DIAGRAM_ENTITIES",
        "DIAGRAM_INTERACTIONS",
        "DIAGRAM_SUMMARY",
        "SLIDE_CAPTION",  # Last-resort full-slide caption (Prompt 7)
    }
)

# Minimum words in notes to treat as "primary narrative"
MIN_NOTES_WORDS = 5

# Confidence threshold: IMAGE_CAPTION/evidence >= this => include 1–3 sentences citing evidence_id; below => generic narration only (no specifics)
IMAGE_CONFIDENCE_THRESHOLD = float(
    __import__("os").environ.get("VISION_SCRIPT_IMAGE_CONFIDENCE_THRESHOLD", "0.5")
)
# Day 3: 3-tier confidence for image/diagram narration
HIGH_CONF = 0.70  # definitive: "This diagram shows..."
MEDIUM_CONF = 0.45  # hedged: "This diagram appears to show..."; below => generic


def _word_count(text: str) -> int:
    return len((text or "").split())


def _graph_summary(graph: Dict[str, Any]) -> str:
    """Short summary of G_unified (nodes, edges) for context."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    parts = []
    if nodes:
        labels = [
            n.get("label_text") or n.get("node_id", "")[:12]
            for n in nodes[:8]
            if n.get("label_text") or n.get("node_id")
        ]
        if labels:
            parts.append("Nodes: " + ", ".join(labels))
    if edges:
        parts.append(f"{len(edges)} edge(s)")
    return ". ".join(parts) if parts else "No graph content"


def _image_evidence_for_slide(
    evidence_items: List[Dict[str, Any]],
    slide_index: int,
) -> List[Dict[str, Any]]:
    """
    Filter to image/diagram evidence for this slide.
    Each item: evidence_id, kind, content, confidence.
    """
    out: List[Dict[str, Any]] = []
    for ev in evidence_items:
        if ev.get("slide_index") != slide_index:
            continue
        kind = (ev.get("kind") or "").strip()
        if kind not in IMAGE_EVIDENCE_KINDS:
            continue
        eid = ev.get("evidence_id")
        if not eid:
            continue
        content = (ev.get("content") or "").strip()
        confidence = float(ev.get("confidence", 0.5))
        out.append(
            {
                "evidence_id": eid,
                "kind": kind,
                "content": content,
                "confidence": confidence,
            }
        )
    return out


def build_context_bundle(
    slide_index: int,
    slide_text: str,
    notes: str,
    graph: Dict[str, Any],
    evidence_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build one slide's context bundle for the script generator.
    Returns: slide_index, slide_text, notes, graph_summary, image_evidence_items (each with evidence_id, kind, content, confidence).
    """
    image_evidence = _image_evidence_for_slide(evidence_items, slide_index)
    max_conf = max([e["confidence"] for e in image_evidence], default=0.0)
    if max_conf >= HIGH_CONF:
        narration_tier = "high"
    elif max_conf >= MEDIUM_CONF:
        narration_tier = "medium"
    else:
        narration_tier = "generic"
    return {
        "slide_index": slide_index,
        "slide_text": (slide_text or "").strip(),
        "notes": (notes or "").strip(),
        "graph_summary": _graph_summary(graph),
        "image_evidence_items": image_evidence,
        "has_notes_primary": _word_count(notes or "") >= MIN_NOTES_WORDS,
        "image_evidence_max_confidence": max_conf,
        "narration_tier": narration_tier,
    }


def build_context_bundles_per_slide(
    slide_count: int,
    slides_notes_and_text: List[Tuple[str, str]],
    unified_graphs_by_slide: Dict[int, Dict[str, Any]],
    evidence_index: Dict[str, Any],
) -> Dict[int, Dict[str, Any]]:
    """
    Build context bundle for each slide.
    slides_notes_and_text: list of (notes, slide_text) for slide_index 1..N.
    Returns: dict slide_index -> context_bundle.
    """
    evidence_items = list(evidence_index.get("evidence_items", []))
    bundles: Dict[int, Dict[str, Any]] = {}
    for i in range(slide_count):
        slide_index = i + 1
        notes, slide_text = slides_notes_and_text[i] if i < len(slides_notes_and_text) else ("", "")
        graph = unified_graphs_by_slide.get(slide_index, {})
        bundles[slide_index] = build_context_bundle(
            slide_index, slide_text, notes, graph, evidence_items
        )
    return bundles


def narration_policy(
    context_bundle: Dict[str, Any],
) -> Tuple[str, List[str], bool]:
    """
    Determine narration source and evidence to cite.
    Returns (policy, evidence_ids_to_cite, use_hedging).
    policy: "notes" | "image_evidence" | "generic"
    """
    notes = (context_bundle.get("notes") or "").strip()
    if _word_count(notes) >= MIN_NOTES_WORDS:
        return "notes", [], False

    image_items = context_bundle.get("image_evidence_items") or []
    max_conf = context_bundle.get("image_evidence_max_confidence", 0.0)
    # Day 3: allow image_evidence when >= MEDIUM_CONF; hedging when tier is medium or generic
    if image_items and max_conf >= MEDIUM_CONF:
        evidence_ids = [e["evidence_id"] for e in image_items]
        use_hedging = max_conf < HIGH_CONF  # high -> definitive, medium/generic -> hedged
        return "image_evidence", evidence_ids, use_hedging

    # Low or no image evidence -> generic, no invented content
    return "generic", [], True
