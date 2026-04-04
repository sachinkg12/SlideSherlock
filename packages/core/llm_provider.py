"""
Provider interface for LLM (script generation) with a local stub mode.
Stub returns deterministic template text so the pipeline works with NO LLM.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


def _steps_from_diagram_interactions(content: str) -> List[str]:
    """
    Parse DIAGRAM_INTERACTIONS content (e.g. "1:A->B:msg; 2:B->C:reply") into step sentences.
    Returns list of "Step N: From sends X to To." for step-by-step narration.
    """
    steps: List[str] = []
    for part in (content or "").split(";"):
        part = part.strip()
        if not part:
            continue
        # Format: "order:from->to:label" or "from->to:label"
        colon_idx = part.find(":")
        if colon_idx < 0:
            continue
        order_str = part[:colon_idx].strip()
        rest = part[colon_idx + 1 :].strip()
        arrow = "->" in rest
        from_to, _, label = rest.partition(":")
        from_to = from_to.strip()
        label = (label or "").strip() or "a message"
        if arrow:
            fr, _, to = from_to.partition("->")
            fr, to = fr.strip(), to.strip()
        else:
            fr, to = "A", "B"
        try:
            n = int(order_str)
        except ValueError:
            n = len(steps) + 1
        steps.append(f"Step {n}: {fr} sends '{label}' to {to}.")
    return steps[:15]


def _narrate_diagram_from_graph(
    slide_index: int,
    slide_text: str,
    graph: Dict[str, Any],
) -> Optional[str]:
    """
    Build diagram narration from graph (nodes, edges) when no notes/image evidence.
    Returns None if graph has no useful content.
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    clusters = graph.get("clusters", [])
    node_by_id = {n["node_id"]: n for n in nodes}
    labels = [
        n.get("label_text", "").strip() for n in nodes[:6] if (n.get("label_text") or "").strip()
    ]
    if not labels and not edges:
        return None
    parts: List[str] = []
    if labels:
        parts.append(f"This slide shows a diagram with key elements: {', '.join(labels[:4])}.")
    if edges:
        flow_parts: List[str] = []
        for e in edges[:5]:
            src = node_by_id.get(e.get("src_node_id", ""))
            dst = node_by_id.get(e.get("dst_node_id", ""))
            src_label = (src.get("label_text") if src else "") or str(e.get("src_node_id", ""))[:8]
            dst_label = (dst.get("label_text") if dst else "") or str(e.get("dst_node_id", ""))[:8]
            if src_label or dst_label:
                flow_parts.append(f"{src_label} to {dst_label}")
        if flow_parts:
            parts.append(f"The flow goes from {'; and from '.join(flow_parts)}.")
    if clusters and not parts:
        parts.append(f"This slide presents a diagram with {len(clusters)} grouped section(s).")
    return " ".join(parts).strip() if parts else None


class LLMProvider(ABC):
    """Interface for generating script segment narration text."""

    @abstractmethod
    def generate_segment(
        self,
        section: Dict[str, Any],
        graph: Dict[str, Any],
        evidence_ids: List[str],
        entity_ids: List[str],
        rag_snippets: Optional[List[str]] = None,
        context_bundle: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate narration text for one segment.
        section: explain_plan section (section_type, slide_index, entity_ids, ...)
        graph: unified graph for that slide (nodes, edges, clusters)
        evidence_ids: list of evidence_ids grounding this segment
        entity_ids: list of entity_ids (node_id/edge_id) referenced
        rag_snippets: optional doc chunks from RAG
        context_bundle: optional per-slide context (notes, image_evidence_items, graph_summary)
          for safe phrasing: notes primary, else image evidence, else generic.
        Returns: narration text string.
        """

    def generate_narration(
        self, blueprint: Dict[str, Any]
    ) -> Optional[Tuple[str, List[str], List[str]]]:
        """
        Optional: Generate per-slide smart narration from blueprint.
        blueprint: slide_index, slide_type, template_narration, llm_context (nodes, edges, evidence_ids).
        Returns (narration_text, entity_ids, evidence_ids) or None to fall back to template.
        Stub returns None (use template). Real LLMs implement this for grounded generation.
        """
        return None


class StubLLMProvider(LLMProvider):
    """
    Deterministic template provider: no LLM call.
    Safe phrasing: notes primary; else image evidence (caption/diagram summary); else generic.
    Every segment is grounded: text cites evidence_ids; image claims cite IMAGE_* or DIAGRAM_*.
    """

    def generate_segment(
        self,
        section: Dict[str, Any],
        graph: Dict[str, Any],
        evidence_ids: List[str],
        entity_ids: List[str],
        rag_snippets: Optional[List[str]] = None,
        context_bundle: Optional[Dict[str, Any]] = None,
    ) -> str:
        section_type = section.get("section_type", "")
        slide_index = section.get("slide_index", 0)
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        graph.get("clusters", [])

        # Safe phrasing: use context_bundle policy when provided
        if context_bundle:
            policy = context_bundle.get("_policy")  # set by script_generator
            if policy == "notes":
                notes = (context_bundle.get("notes") or "").strip()
                if notes:
                    return notes
            if policy == "generic":
                # When no notes/image evidence: narrate from graph (connector/native shapes) if available
                slide_text = (context_bundle.get("slide_text") or "").strip()
                narration = _narrate_diagram_from_graph(slide_index, slide_text, graph)
                if narration:
                    return narration
                return (
                    "This slide includes an image or diagram. "
                    "Details could not be extracted reliably."
                )
            if policy == "image_evidence":
                items = context_bundle.get("image_evidence_items") or []
                tier = context_bundle.get("narration_tier", "generic")
                use_hedging = context_bundle.get("_use_hedging", True)
                # Day 3: 3-tier wording — high: definitive; medium: hedged; generic: fallback
                if tier == "high":
                    prefix_diagram = "This diagram shows "
                    prefix_image = "This image shows "
                elif tier == "medium":
                    prefix_diagram = "This diagram appears to show "
                    prefix_image = "This image appears to show "
                else:
                    prefix_diagram = "This slide contains a diagram. "
                    prefix_image = "This slide contains an image. "

                # Day 3: When DIAGRAM_INTERACTIONS exists with medium+ confidence, narrate step-by-step
                interactions_item = next(
                    (
                        e
                        for e in items
                        if (e.get("kind") or "") == "DIAGRAM_INTERACTIONS"
                        and float(e.get("confidence", 0)) >= 0.45
                    ),
                    None,
                )
                if interactions_item:
                    content = (interactions_item.get("content") or "").strip()
                    steps = _steps_from_diagram_interactions(content)
                    if steps:
                        intro = prefix_diagram.rstrip() if use_hedging else "This diagram shows "
                        return intro + " ".join(steps)

                parts = []
                for e in items:
                    kind = e.get("kind", "")
                    content = (e.get("content") or "").strip()
                    if not content:
                        continue
                    if kind == "IMAGE_CAPTION" or kind == "SLIDE_CAPTION":
                        parts.append(
                            (prefix_image if tier != "generic" else "This slide shows ").rstrip()
                            + " "
                            + content[:300]
                        )
                        break
                    if kind == "DIAGRAM_SUMMARY":
                        parts.append(
                            (prefix_diagram if tier != "generic" else "This slide shows ").rstrip()
                            + " "
                            + content[:300]
                        )
                        break
                if parts:
                    return parts[0]
                # Fallback: list kinds
                for e in items:
                    if e.get("content"):
                        parts.append((e.get("content") or "")[:150])
                if parts:
                    return (
                        (
                            prefix_diagram
                            if "DIAGRAM" in str([x.get("kind") for x in items])
                            else prefix_image
                        ).rstrip()
                        + " "
                        + "; ".join(parts[:2])
                    )
                return (
                    "This slide appears to include a diagram or image."
                    if use_hedging
                    else "This slide includes a diagram or image."
                )

        node_by_id = {n["node_id"]: n for n in nodes}
        edge_by_id = {e["edge_id"]: e for e in edges}

        if section_type == "intro":
            return (
                f"This is slide {slide_index}. "
                f"It shows {len(nodes)} elements and {len(edges)} connections."
            )
        if section_type == "clusters":
            section.get("cluster_ids", [])
            member_labels = []
            for nid in entity_ids:
                n = node_by_id.get(nid)
                if n:
                    member_labels.append(n.get("label_text") or nid[:8])
            if member_labels:
                return f"Cluster contains: {', '.join(member_labels)}."
            return "This cluster groups related elements."
        if section_type == "nodes":
            labels = []
            for eid in entity_ids:
                n = node_by_id.get(eid)
                if n:
                    labels.append(n.get("label_text") or eid[:8])
            if labels:
                return f"Element: {', '.join(labels)}."
            return "This element is part of the diagram."
        if section_type == "flows":
            parts = []
            for eid in entity_ids:
                e = edge_by_id.get(eid)
                if e:
                    src = node_by_id.get(e.get("src_node_id"))
                    dst = node_by_id.get(e.get("dst_node_id"))
                    src_label = (src.get("label_text") if src else None) or e.get(
                        "src_node_id", ""
                    )[:8]
                    dst_label = (dst.get("label_text") if dst else None) or e.get(
                        "dst_node_id", ""
                    )[:8]
                    parts.append(f"{src_label} to {dst_label}")
            if parts:
                return f"Flow: {'; '.join(parts)}."
            return "This connection links two elements."
        if section_type == "summary":
            return f"That concludes slide {slide_index}."

        return "This segment describes part of the diagram."
