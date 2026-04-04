"""
Narration blueprint for smart narration (Fig3 step 14).
Identifies slide type, builds template narration, and provides LLM context
(nodes, edges, clusters, evidence_ids) for grounded generation.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

SLIDE_TYPE_DIAGRAM_PROCESS = "diagram_process"
SLIDE_TYPE_BULLET_LIST = "bullet_list"
SLIDE_TYPE_CHART = "chart"
SLIDE_TYPE_TITLE_ONLY = "title_only"


def _word_count(text: str) -> int:
    return len((text or "").split())


def _has_bullet_pattern(text: str) -> bool:
    """Heuristic: slide text has bullet-like structure (-, •, *, numbers)."""
    if not text or len(text) < 10:
        return False
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 2:
        return False
    bullet_chars = ("-", "•", "*", "·", "–", "—")
    bullet_count = sum(
        1
        for line in lines
        if line.startswith(bullet_chars)
        or (len(line) > 1 and line[0].isdigit() and line[1] in ".):")
    )
    return bullet_count >= 2 or (bullet_count >= 1 and len(lines) >= 3)


def _has_chart_keywords(text: str) -> bool:
    """Basic heuristic for chart-like slides."""
    lower = (text or "").lower()
    keywords = ("chart", "graph", "bar", "pie", "trend", "percentage", "%", "axis")
    return any(kw in lower for kw in keywords)


def classify_slide_type(slide_text: str, graph: Dict[str, Any]) -> str:
    """
    Identify slide type: diagram_process, bullet_list, chart, title_only.
    Uses slide text structure and G_unified (nodes, edges, clusters).
    """
    slide_text = (slide_text or "").strip()
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    clusters = graph.get("clusters", [])

    # Rich diagram: multiple nodes + edges
    if len(nodes) >= 2 and len(edges) >= 1:
        return SLIDE_TYPE_DIAGRAM_PROCESS

    # Bullet list: structured bullet points
    if _has_bullet_pattern(slide_text):
        return SLIDE_TYPE_BULLET_LIST

    # Chart: keywords or many numeric-like nodes
    if _has_chart_keywords(slide_text):
        return SLIDE_TYPE_CHART
    if len(nodes) >= 3 and clusters:
        return SLIDE_TYPE_CHART

    # Diagram/process: single cluster or few nodes
    if nodes or edges or clusters:
        return SLIDE_TYPE_DIAGRAM_PROCESS

    # Title-only / section divider: minimal content
    if _word_count(slide_text) <= 5 and not nodes and not edges:
        return SLIDE_TYPE_TITLE_ONLY

    return SLIDE_TYPE_DIAGRAM_PROCESS


def _template_for_diagram_process(
    slide_index: int,
    slide_text: str,
    graph: Dict[str, Any],
) -> str:
    """Template narration for diagram/process slides. Avoid duplicating slide_text in generic template."""
    slide_text = (slide_text or "").strip()
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    clusters = graph.get("clusters", [])
    labels = [n.get("label_text") or "" for n in nodes[:6] if n.get("label_text")]
    if slide_text and _word_count(slide_text) >= 10:
        return slide_text[:300].strip()
    if labels:
        intro = f"This slide shows a diagram with key elements: {', '.join(labels[:4])}."
        if len(labels) > 4:
            intro += f" And more."
    else:
        intro = f"This slide presents a diagram."
    if edges:
        intro += f" There are {len(edges)} connection(s) between the elements."
    if clusters:
        intro += f" The diagram has {len(clusters)} grouped section(s)."
    if slide_text and _word_count(slide_text) >= 3 and _word_count(slide_text) < 10:
        intro += f" {slide_text[:150].strip()}."
    return intro


def _template_for_bullet_list(slide_index: int, slide_text: str, graph: Dict[str, Any]) -> str:
    """Template narration for bullet list slides."""
    if slide_text and _word_count(slide_text) >= 5:
        lines = [l.strip() for l in slide_text.split("\n") if l.strip()][:5]
        return f"On this slide: {' '.join(lines[:3])}."
    return f"This slide lists several points for slide {slide_index}."


def _template_for_chart(slide_index: int, slide_text: str, graph: Dict[str, Any]) -> str:
    """Template narration for chart slides."""
    nodes = graph.get("nodes", [])
    labels = [n.get("label_text") or "" for n in nodes[:4] if n.get("label_text")]
    if labels:
        return f"This slide displays a chart or graph with elements such as {', '.join(labels)}."
    if slide_text and _word_count(slide_text) >= 3:
        return f"This chart shows: {slide_text[:120].strip()}."
    return f"This slide presents a chart or data visualization."


def _template_for_title_only(slide_index: int, slide_text: str, graph: Dict[str, Any]) -> str:
    """Template narration for title-only / section divider slides."""
    if slide_text and _word_count(slide_text) >= 1:
        return f"This is a section: {slide_text.strip()}."
    return f"This is slide {slide_index}."


def build_template_narration(
    slide_index: int,
    slide_type: str,
    slide_text: str,
    graph: Dict[str, Any],
) -> str:
    """Generate template narration from slide type and content."""
    graph = graph or {}
    slide_text = (slide_text or "").strip()
    if slide_type == SLIDE_TYPE_DIAGRAM_PROCESS:
        return _template_for_diagram_process(slide_index, slide_text, graph)
    if slide_type == SLIDE_TYPE_BULLET_LIST:
        return _template_for_bullet_list(slide_index, slide_text, graph)
    if slide_type == SLIDE_TYPE_CHART:
        return _template_for_chart(slide_index, slide_text, graph)
    if slide_type == SLIDE_TYPE_TITLE_ONLY:
        return _template_for_title_only(slide_index, slide_text, graph)
    return _template_for_diagram_process(slide_index, slide_text, graph)


def _evidence_for_slide(
    evidence_items: List[Dict[str, Any]],
    slide_index: int,
) -> List[Dict[str, Any]]:
    """Filter evidence items for this slide."""
    out = []
    for ev in evidence_items:
        si = ev.get("slide_index")
        if si is None:
            continue
        if int(si) == int(slide_index):
            out.append(ev)
    return out


# Evidence kinds that describe diagram/image content (used when graph has no labels)
_IMAGE_EVIDENCE_KINDS = frozenset(
    {
        "IMAGE_CAPTION",
        "DIAGRAM_SUMMARY",
        "SLIDE_CAPTION",
        "DIAGRAM_ENTITIES",
        "DIAGRAM_INTERACTIONS",
    }
)

# Low-confidence fallback phrases - do NOT use as narration (user would hear "low confidence, details not present")
_LOW_CONFIDENCE_PHRASES = (
    "image present (low confidence)",
    "details unavailable",
    "details not present",
    "could not be extracted",
)


def _is_low_confidence_fallback(content: str) -> bool:
    """True if content is a stub/low-confidence fallback, not useful for narration."""
    c = (content or "").lower().strip()
    return any(phrase in c for phrase in _LOW_CONFIDENCE_PHRASES)


def build_narration_blueprint(
    slide_index: int,
    notes: str,
    slide_text: str,
    graph: Dict[str, Any],
    evidence_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build a narration blueprint for one slide.
    Returns: slide_index, slide_type, template_narration, llm_context (nodes, edges, clusters, evidence_ids).
    Uses image evidence (DIAGRAM_SUMMARY, IMAGE_CAPTION, SLIDE_CAPTION) when graph has no labels.
    """
    graph = graph or {}
    notes = (notes or "").strip()
    slide_text = (slide_text or "").strip()
    evidence_items = evidence_items or []

    slide_type = classify_slide_type(slide_text, graph)
    template_narration = build_template_narration(slide_index, slide_type, slide_text, graph)

    # When template is generic and we have image evidence, use evidence content
    evidence_for_slide = _evidence_for_slide(evidence_items, slide_index)
    t_lower = template_narration.lower()
    is_generic = (
        "this slide presents a diagram" in t_lower
        or "this slide includes an image or diagram" in t_lower
    )
    if is_generic:
        for ev in evidence_for_slide:
            if ev.get("kind") in _IMAGE_EVIDENCE_KINDS:
                content = (ev.get("content") or "").strip()
                if content and len(content) > 10 and not _is_low_confidence_fallback(content):
                    template_narration = f"This slide shows {content[:400]}."
                    break

    # LLM context: diagram flow, key nodes, valid evidence_ids
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    clusters = graph.get("clusters", [])

    node_labels = [
        {"node_id": n.get("node_id"), "label": n.get("label_text") or ""} for n in nodes[:15]
    ]
    edge_flow = [
        {
            "edge_id": e.get("edge_id"),
            "src": e.get("src_node_id"),
            "dst": e.get("dst_node_id"),
            "label": e.get("label_text"),
        }
        for e in edges[:20]
    ]
    cluster_info = [
        {
            "cluster_id": c.get("cluster_id"),
            "member_node_ids": c.get("member_node_ids", []),
            "title": c.get("title"),
        }
        for c in clusters[:10]
    ]

    valid_evidence_ids = [
        ev.get("evidence_id") for ev in evidence_for_slide if ev.get("evidence_id")
    ]

    llm_context = {
        "nodes": node_labels,
        "edges": edge_flow,
        "clusters": cluster_info,
        "evidence_ids": valid_evidence_ids,
        "slide_text": slide_text[:500] if slide_text else "",
        "notes_preview": notes[:200] if notes else "",
    }

    return {
        "slide_index": slide_index,
        "slide_type": slide_type,
        "template_narration": template_narration,
        "llm_context": llm_context,
        "needs_smart_narration": _word_count(notes) < 5,
    }


def build_blueprint_per_slide(
    slide_count: int,
    slides_notes_and_text: List[Tuple[str, str]],
    unified_graphs_by_slide: Dict[int, Dict[str, Any]],
    evidence_items: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Build narration blueprints for all slides.
    Returns list of blueprint dicts.
    """
    evidence_items = evidence_items or []
    blueprints = []
    for i in range(slide_count):
        slide_index = i + 1
        notes, slide_text = slides_notes_and_text[i] if i < len(slides_notes_and_text) else ("", "")
        graph = unified_graphs_by_slide.get(slide_index, {})
        bp = build_narration_blueprint(slide_index, notes, slide_text, graph, evidence_items)
        blueprints.append(bp)
    return blueprints
