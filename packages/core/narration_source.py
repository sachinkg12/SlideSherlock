"""
Narration source selection per slide (Fig3 step 14).
Primary: Speaker Notes; Secondary: Slide text + diagram summary (G_unified);
Smart narration: LLM (grounded) or template when notes missing or too short.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

SOURCE_USER_AUDIO = "user_audio"
SOURCE_NOTES = "notes"
SOURCE_LLM = "llm"
SOURCE_TEMPLATE = "template"
SOURCE_MIXED = "mixed"
SOURCE_SLIDE_AND_GRAPH = "slide_and_graph"

MIN_NOTES_WORDS = 5  # below this we treat as "missing" and use secondary/LLM/template


def _word_count(text: str) -> int:
    return len((text or "").split())


def _diagram_summary_from_graph(graph: Dict[str, Any]) -> str:
    """Short explanatory summary from G_unified (nodes, edges, clusters)."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    clusters = graph.get("clusters", [])
    parts = []
    if nodes:
        labels = [n.get("label_text") or "" for n in nodes[:5] if n.get("label_text")]
        if labels:
            parts.append("Elements: " + ", ".join(labels))
    if edges:
        parts.append(f"{len(edges)} connection(s)")
    if clusters:
        parts.append(f"{len(clusters)} group(s)")
    return ". ".join(parts) if parts else "Diagram on this slide."


def _graph_entity_ids(graph: Dict[str, Any]) -> Tuple[set, set]:
    """Return (node_ids, edge_ids) for the graph."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_ids = {n.get("node_id") for n in nodes if n.get("node_id")}
    edge_ids = {e.get("edge_id") for e in edges if e.get("edge_id")}
    return node_ids, edge_ids


def _verify_grounding(
    entity_ids: List[str],
    evidence_ids: List[str],
    graph: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
) -> bool:
    """
    Verify LLM output is grounded: entity_ids in G_unified, evidence_ids in evidence index.
    All referenced entity_ids must exist in graph; all evidence_ids must exist in index.
    At least one grounding reference (entity or evidence) required to prevent hallucination.
    """
    node_ids, edge_ids = _graph_entity_ids(graph)
    valid_entity_ids = node_ids | edge_ids

    for eid in entity_ids:
        if eid and eid not in valid_entity_ids:
            return False
    for ev_id in evidence_ids:
        if ev_id and ev_id not in evidence_by_id:
            return False
    return len(entity_ids) > 0 or len(evidence_ids) > 0


def get_narration_text_for_slide(
    slide_index: int,
    notes: str,
    slide_text: str,
    graph: Optional[Dict[str, Any]] = None,
    llm_narration_fn: Optional[Callable[[int, str, str, str], Optional[str]]] = None,
) -> Tuple[str, str]:
    """
    Return (narration_text, source_used).
    Primary: notes (if present and long enough).
    Secondary: slide text + diagram summary.
    Optional: LLM/template if notes missing or too short.
    llm_narration_fn(slide_index, slide_text, diagram_summary, notes) -> narration_text or None.
    """
    notes = (notes or "").strip()
    slide_text = (slide_text or "").strip()
    graph = graph or {}

    if notes and _word_count(notes) >= MIN_NOTES_WORDS:
        return notes, SOURCE_NOTES

    diagram_summary = _diagram_summary_from_graph(graph)
    fallback = slide_text or diagram_summary
    if fallback and _word_count(fallback) >= 3:
        if notes and _word_count(notes) > 0:
            combined = f"{notes} {fallback}".strip()
            return combined, SOURCE_MIXED
        return fallback, SOURCE_SLIDE_AND_GRAPH

    if llm_narration_fn:
        try:
            generated = llm_narration_fn(slide_index, slide_text, diagram_summary, notes)
            if generated and _word_count(generated) >= 2:
                return generated, SOURCE_LLM
        except Exception:
            pass

    template = f"This is slide {slide_index}. {diagram_summary}"
    return template, SOURCE_LLM


def get_narration_with_smart_fallback(
    slide_index: int,
    notes: str,
    slide_text: str,
    graph: Dict[str, Any],
    blueprint: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
    llm_narration_fn: Optional[
        Callable[[Dict[str, Any]], Optional[Tuple[str, List[str], List[str]]]]
    ] = None,
) -> Tuple[str, str, Optional[List[str]], Optional[List[str]]]:
    """
    Smart narration for slides without notes.
    Returns (narration_text, source_used, entity_ids, evidence_ids).
    If LLM returns grounded content (valid entity_ids, evidence_ids): use it, source=llm.
    Else: use blueprint template_narration, source=template.
    llm_narration_fn(blueprint) -> (text, entity_ids, evidence_ids) or None.
    """
    notes = (notes or "").strip()
    graph = graph or {}
    evidence_by_id = evidence_by_id or {}

    if notes and _word_count(notes) >= MIN_NOTES_WORDS:
        return notes, SOURCE_NOTES, None, None

    template_narration = blueprint.get("template_narration", "")
    if not template_narration:
        template_narration = f"This is slide {slide_index}. {_diagram_summary_from_graph(graph)}"

    if llm_narration_fn:
        try:
            result = llm_narration_fn(blueprint)
            if result and len(result) >= 3:
                text, entity_ids, evidence_ids = result[0], result[1], result[2]
                entity_ids = entity_ids or []
                evidence_ids = evidence_ids or []
                if text and _word_count(text) >= 2 and _verify_grounding(
                    entity_ids, evidence_ids, graph, evidence_by_id
                ):
                    return text, SOURCE_LLM, entity_ids, evidence_ids
        except Exception:
            pass

    return template_narration, SOURCE_TEMPLATE, None, None


def build_narration_per_slide(
    slide_count: int,
    slides_notes_and_text: List[Tuple[str, str]],
    unified_graphs_by_slide: Dict[int, Dict[str, Any]],
    llm_narration_fn: Optional[Callable[[int, str, str, str], Optional[str]]] = None,
    blueprints: Optional[List[Dict[str, Any]]] = None,
    evidence_index: Optional[Dict[str, Any]] = None,
    llm_smart_narration_fn: Optional[
        Callable[[Dict[str, Any]], Optional[Tuple[str, List[str], List[str]]]]
    ] = None,
) -> List[Dict[str, Any]]:
    """
    Build narration_per_slide entries: slide_index, narration_text, source_used, word_count.
    slides_notes_and_text: list of (notes, slide_text) per slide_index 1..N.

    When notes missing/short and blueprints provided: uses smart narration
    (LLM with grounding verification or template fallback). Pass evidence_index
    and llm_smart_narration_fn for LLM-based generation.
    """
    from narration_blueprint import build_blueprint_per_slide

    evidence_by_id: Dict[str, Dict[str, Any]] = {}
    if evidence_index:
        for ev in evidence_index.get("evidence_items", []):
            eid = ev.get("evidence_id")
            if eid:
                evidence_by_id[eid] = ev

    if blueprints is None and (llm_smart_narration_fn is not None or evidence_index):
        blueprints = build_blueprint_per_slide(
            slide_count,
            slides_notes_and_text,
            unified_graphs_by_slide,
            evidence_index.get("evidence_items", []) if evidence_index else [],
        )

    entries = []
    for i in range(slide_count):
        slide_index = i + 1
        notes, slide_text = slides_notes_and_text[i] if i < len(slides_notes_and_text) else ("", "")
        graph = unified_graphs_by_slide.get(slide_index, {})
        blueprint = blueprints[i] if blueprints and i < len(blueprints) else {}

        if blueprint:
            text, source, entity_ids, evidence_ids = get_narration_with_smart_fallback(
                slide_index,
                notes,
                slide_text,
                graph,
                blueprint,
                evidence_by_id,
                llm_smart_narration_fn,
            )
            entry = {
                "slide_index": slide_index,
                "narration_text": text,
                "source_used": source,
                "word_count": _word_count(text),
            }
            if entity_ids is not None:
                entry["referenced_entity_ids"] = entity_ids
            if evidence_ids is not None:
                entry["referenced_evidence_ids"] = evidence_ids
            entries.append(entry)
        else:
            text, source = get_narration_text_for_slide(
                slide_index, notes, slide_text, graph, llm_narration_fn
            )
            entries.append({
                "slide_index": slide_index,
                "narration_text": text,
                "source_used": source,
                "word_count": _word_count(text),
            })
    return entries
