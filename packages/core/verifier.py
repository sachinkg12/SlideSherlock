"""
Verifier engine (Fig3 step 12, Fig6).
Checks each claim: evidence_ids, entity_ids in G_unified, claim vs evidence, relations vs graph.
Outputs: verify_report.json (verdict + reasons + pointers), coverage.json.
Rewrite loop: regenerate REWRITE segments via provider (or deterministic rewrite), re-verify until clean or max_iters.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_provider import LLMProvider

# Verdicts per Fig6
VERDICT_PASS = "PASS"
VERDICT_REWRITE = "REWRITE"
VERDICT_REMOVE = "REMOVE"

# Reason codes
REASON_NO_EVIDENCE_IDS = "NO_EVIDENCE_IDS"
REASON_EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
REASON_ENTITY_NOT_IN_GRAPH = "ENTITY_NOT_IN_GRAPH"
REASON_UNSUPPORTED_BY_EVIDENCE = "UNSUPPORTED_BY_EVIDENCE"
REASON_GRAPH_CONTRADICTION = "GRAPH_CONTRADICTION"
REASON_IMAGE_CLAIM_NEEDS_IMAGE_EVIDENCE = "IMAGE_CLAIM_NEEDS_IMAGE_EVIDENCE"
REASON_IMAGE_UNGROUNDED = "IMAGE_UNGROUNDED"
REASON_DIAGRAM_UNSUPPORTED = "DIAGRAM_UNSUPPORTED"
REASON_NEEDS_HEDGING = "NEEDS_HEDGING"
REASON_OBJECT_ACTION_UNSUPPORTED = "OBJECT_ACTION_UNSUPPORTED"

# Image evidence kinds (NO-HALLUCINATION: image claims must cite these)
IMAGE_EVIDENCE_KINDS = frozenset(
    {
        "IMAGE_ASSET",  # Extracted embedded image (bbox, uri)
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

# Conservative: treat as image-related if text contains any of these
IMAGE_CLAIM_KEYWORDS = (
    "image",
    "photo",
    "shows",
    "students",
    "football",
    "diagram",
    "sequence",
    "actor",
    "message",
    "depicts",
    "picture",
    "illustration",
    "appears to show",
)

# Hedging words: if claim uses these, no NEEDS_HEDGING
HEDGING_WORDS = ("appears", "likely", "may", "might", "could", "seems", "probably", "perhaps")

# Confidence below this with definitive claim -> NEEDS_HEDGING
HEDGING_CONFIDENCE_THRESHOLD = float(
    __import__("os").environ.get("VERIFIER_HEDGING_CONFIDENCE_THRESHOLD", "0.6")
)

DEFAULT_MAX_VERIFY_ITERS = 3


def _tokenize(s: str) -> set:
    """Lowercase token set for heuristic comparison."""
    s = (s or "").lower()
    return set(re.findall(r"[a-z0-9]+", s))


def _evidence_by_id(evidence_index: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build evidence_id -> evidence item map."""
    out = {}
    for ev in evidence_index.get("evidence_items", []):
        eid = ev.get("evidence_id")
        if eid:
            out[eid] = ev
    return out


def _graph_entity_ids(graph: Dict[str, Any]) -> Tuple[set, set]:
    """Return (node_ids, edge_ids) for the graph."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_ids = {n.get("node_id") for n in nodes if n.get("node_id")}
    edge_ids = {e.get("edge_id") for e in edges if e.get("edge_id")}
    return node_ids, edge_ids


def _check_has_evidence_ids(segment: Dict[str, Any]) -> Optional[str]:
    """Check: segment has at least one evidence_id. Returns reason if fail."""
    evidence_ids = segment.get("evidence_ids") or []
    if not evidence_ids:
        return REASON_NO_EVIDENCE_IDS
    return None


def _check_evidence_ids_exist(
    segment: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    """Check: all evidence_ids exist in evidence index. Returns reason if fail."""
    evidence_ids = segment.get("evidence_ids") or []
    for eid in evidence_ids:
        if eid not in evidence_by_id:
            return REASON_EVIDENCE_NOT_FOUND
    return None


def _check_entity_ids_in_graph(
    segment: Dict[str, Any],
    graph: Dict[str, Any],
) -> Optional[str]:
    """Check: all entity_ids exist in G_unified for this slide. Returns reason if fail."""
    entity_ids = segment.get("entity_ids") or []
    if not entity_ids:
        return None
    node_ids, edge_ids = _graph_entity_ids(graph)
    for eid in entity_ids:
        if eid not in node_ids and eid not in edge_ids:
            return REASON_ENTITY_NOT_IN_GRAPH
    return None


def _check_claim_supported_by_evidence(
    segment: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    """
    Heuristic: claim text consistent with evidence content.
    Allow paraphrase; disallow new facts; enforce numeric consistency.
    Returns reason if fail.
    """
    text = (segment.get("text") or "").strip()
    evidence_ids = segment.get("evidence_ids") or []
    if not text or not evidence_ids:
        return None
    claim_tokens = _tokenize(text)
    evidence_contents = []
    for eid in evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev:
            evidence_contents.append((ev.get("content") or "").strip())
    if not evidence_contents:
        return REASON_UNSUPPORTED_BY_EVIDENCE
    all_evidence_text = " ".join(evidence_contents)
    evidence_tokens = _tokenize(all_evidence_text)
    # Numbers in claim must appear in evidence (numeric consistency)
    claim_nums = set(re.findall(r"\d+", text))
    evidence_nums = set(re.findall(r"\d+", all_evidence_text))
    if claim_nums and not evidence_nums:
        return REASON_UNSUPPORTED_BY_EVIDENCE
    for n in claim_nums:
        if n not in evidence_nums:
            return REASON_UNSUPPORTED_BY_EVIDENCE
    # Heuristic: at least some overlap (paraphrase ok; no requirement that every word is in evidence)
    if claim_tokens and not (claim_tokens & evidence_tokens):
        return REASON_UNSUPPORTED_BY_EVIDENCE
    return None


def _is_image_claim(
    segment: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
) -> bool:
    """
    Conservative: claim is image-related if it cites image evidence, or uses image keywords,
    or we are uncertain (then treat as image-related).
    """
    evidence_ids = segment.get("evidence_ids") or []
    for eid in evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev and ev.get("kind") in IMAGE_EVIDENCE_KINDS:
            return True
    text = (segment.get("text") or "").lower()
    if any(kw in text for kw in IMAGE_CLAIM_KEYWORDS):
        return True
    # Uncertain: if segment has very little non-generic content, don't force image
    if not text or len(text.strip()) < 10:
        return False
    # Conservative: if it could describe visual content, treat as image-related
    visual = ("shows", "display", "figure", "chart", "graph")
    if any(v in text for v in visual):
        return True
    return False


def _get_cited_image_evidence_kinds_and_confidence(
    segment: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
) -> Tuple[List[str], float]:
    """Return (list of cited image evidence kinds, min confidence used)."""
    kinds: List[str] = []
    min_conf = 1.0
    for eid in segment.get("evidence_ids") or []:
        ev = evidence_by_id.get(eid)
        if not ev or ev.get("kind") not in IMAGE_EVIDENCE_KINDS:
            continue
        kinds.append(ev.get("kind") or "")
        c = float(ev.get("confidence", 0.5))
        if c < min_conf:
            min_conf = c
    return kinds, min_conf if kinds else 0.0


def _check_image_claims_cite_image_evidence(
    segment: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    """
    NO-HALLUCINATION: If claim is image-related it MUST cite at least one IMAGE_* or DIAGRAM_* evidence.
    Uses REASON_IMAGE_UNGROUNDED when image claim has no image evidence.
    """
    if not _is_image_claim(segment, evidence_by_id):
        return None
    evidence_ids = segment.get("evidence_ids") or []
    has_image_evidence = False
    for eid in evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev and ev.get("kind") in IMAGE_EVIDENCE_KINDS:
            has_image_evidence = True
            break
    if not has_image_evidence:
        return REASON_IMAGE_UNGROUNDED
    return None


def _check_claim_object_action_consistency(
    segment: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    """
    If claim cites IMAGE_OBJECTS/IMAGE_ACTIONS, claim should not mention objects/actions
    not present in that evidence (with sufficient confidence). Heuristic: token overlap.
    """
    evidence_ids = segment.get("evidence_ids") or []
    objects_actions_content: List[str] = []
    for eid in evidence_ids:
        ev = evidence_by_id.get(eid)
        if not ev or ev.get("kind") not in ("IMAGE_OBJECTS", "IMAGE_ACTIONS"):
            continue
        objects_actions_content.append((ev.get("content") or "").strip())
    if not objects_actions_content:
        return None
    text = (segment.get("text") or "").strip()
    if not text:
        return None
    allowed_tokens = _tokenize(" ".join(objects_actions_content))
    claim_tokens = _tokenize(text)
    # Require some overlap; if claim has many tokens not in evidence, may be hallucination
    overlap = len(claim_tokens & allowed_tokens)
    if claim_tokens and overlap == 0:
        return REASON_OBJECT_ACTION_UNSUPPORTED
    # Allow short claims with one word overlap; flag if claim is long and almost no overlap
    if len(claim_tokens) >= 5 and overlap <= 1:
        return REASON_OBJECT_ACTION_UNSUPPORTED
    return None


def _check_diagram_interactions_consistency(
    segment: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    """
    If claim cites DIAGRAM_INTERACTIONS/DIAGRAM_SUMMARY, claim should not describe
    message order or entities not in that evidence. Heuristic: token overlap.
    """
    evidence_ids = segment.get("evidence_ids") or []
    diagram_content: List[str] = []
    for eid in evidence_ids:
        ev = evidence_by_id.get(eid)
        if not ev or ev.get("kind") not in ("DIAGRAM_INTERACTIONS", "DIAGRAM_SUMMARY"):
            continue
        diagram_content.append((ev.get("content") or "").strip())
    if not diagram_content:
        return None
    text = (segment.get("text") or "").strip()
    if not text:
        return None
    allowed_tokens = _tokenize(" ".join(diagram_content))
    claim_tokens = _tokenize(text)
    if claim_tokens and not (claim_tokens & allowed_tokens):
        return REASON_DIAGRAM_UNSUPPORTED
    if len(claim_tokens) >= 4 and len(claim_tokens & allowed_tokens) <= 1:
        return REASON_DIAGRAM_UNSUPPORTED
    return None


def _check_hedging(
    segment: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    """
    If cited image evidence has confidence below threshold and claim is definitive
    (no hedging words), verdict REWRITE reason NEEDS_HEDGING.
    """
    _, min_conf = _get_cited_image_evidence_kinds_and_confidence(segment, evidence_by_id)
    if min_conf >= HEDGING_CONFIDENCE_THRESHOLD:
        return None
    # Only require hedging when segment actually cites image evidence
    evidence_ids = segment.get("evidence_ids") or []
    has_image = any(
        evidence_by_id.get(eid, {}).get("kind") in IMAGE_EVIDENCE_KINDS for eid in evidence_ids
    )
    if not has_image:
        return None
    text = (segment.get("text") or "").lower()
    if any(h in text for h in HEDGING_WORDS):
        return None
    if segment.get("used_hedging") is True:
        return None
    return REASON_NEEDS_HEDGING


def _check_relations_consistent_with_graph(
    segment: Dict[str, Any],
    graph: Dict[str, Any],
) -> Optional[str]:
    """
    When claim references flow (entity_ids include edge_id): edge must exist, src/dst in graph.
    Cluster: entity_ids that are node_ids should be in same cluster if claim suggests grouping.
    Returns reason if fail.
    """
    entity_ids = segment.get("entity_ids") or []
    if not entity_ids:
        return None
    nodes = {n.get("node_id"): n for n in graph.get("nodes", []) if n.get("node_id")}
    edges = {e.get("edge_id"): e for e in graph.get("edges", []) if e.get("edge_id")}
    for eid in entity_ids:
        if eid in edges:
            e = edges[eid]
            src = e.get("src_node_id")
            dst = e.get("dst_node_id")
            if src and src not in nodes:
                return REASON_GRAPH_CONTRADICTION
            if dst and dst not in nodes:
                return REASON_GRAPH_CONTRADICTION
    return None


def verify_segment(
    segment: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
    graph: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run all verifier checks on one segment. Return report entry: verdict, reasons[], pointers,
    is_image_claim, required_evidence_kinds, confidence_used.
    """
    reasons: List[str] = []
    pointers: Dict[str, Any] = {}

    is_image_claim = _is_image_claim(segment, evidence_by_id)
    cited_kinds, confidence_used = _get_cited_image_evidence_kinds_and_confidence(
        segment, evidence_by_id
    )
    required_evidence_kinds: List[str] = list(IMAGE_EVIDENCE_KINDS) if is_image_claim else []

    r = _check_has_evidence_ids(segment)
    if r:
        reasons.append(r)
        pointers["evidence_ids"] = segment.get("evidence_ids", [])

    r = _check_evidence_ids_exist(segment, evidence_by_id)
    if r:
        reasons.append(r)
        invalid = [eid for eid in (segment.get("evidence_ids") or []) if eid not in evidence_by_id]
        pointers["invalid_evidence_ids"] = invalid

    r = _check_entity_ids_in_graph(segment, graph)
    if r:
        reasons.append(r)
        node_ids, edge_ids = _graph_entity_ids(graph)
        entity_ids = segment.get("entity_ids") or []
        missing = [eid for eid in entity_ids if eid not in node_ids and eid not in edge_ids]
        pointers["missing_entity_ids"] = missing

    r = _check_image_claims_cite_image_evidence(segment, evidence_by_id)
    if r:
        reasons.append(r)
        pointers["claim_snippet"] = (segment.get("text") or "")[:200]

    r = _check_claim_object_action_consistency(segment, evidence_by_id)
    if r:
        reasons.append(r)
        pointers["claim_snippet"] = (
            pointers.get("claim_snippet") or (segment.get("text") or "")[:200]
        )

    r = _check_diagram_interactions_consistency(segment, evidence_by_id)
    if r:
        reasons.append(r)
        pointers["claim_snippet"] = (
            pointers.get("claim_snippet") or (segment.get("text") or "")[:200]
        )

    r = _check_claim_supported_by_evidence(segment, evidence_by_id)
    if r:
        reasons.append(r)
        pointers["claim_snippet"] = (
            pointers.get("claim_snippet") or (segment.get("text") or "")[:200]
        )

    r = _check_hedging(segment, evidence_by_id)
    if r:
        reasons.append(r)
        pointers["claim_snippet"] = (
            pointers.get("claim_snippet") or (segment.get("text") or "")[:200]
        )

    r = _check_relations_consistent_with_graph(segment, graph)
    if r:
        reasons.append(r)
        pointers["entity_ids"] = segment.get("entity_ids", [])

    # Decision: REMOVE if no evidence or unsupported; REWRITE if fixable; else PASS
    if REASON_NO_EVIDENCE_IDS in reasons or REASON_EVIDENCE_NOT_FOUND in reasons:
        verdict = VERDICT_REWRITE
    elif REASON_ENTITY_NOT_IN_GRAPH in reasons:
        verdict = VERDICT_REWRITE
    elif REASON_UNSUPPORTED_BY_EVIDENCE in reasons:
        verdict = VERDICT_REWRITE
    elif REASON_GRAPH_CONTRADICTION in reasons:
        verdict = VERDICT_REWRITE
    elif REASON_IMAGE_UNGROUNDED in reasons or REASON_IMAGE_CLAIM_NEEDS_IMAGE_EVIDENCE in reasons:
        verdict = VERDICT_REWRITE
    elif REASON_OBJECT_ACTION_UNSUPPORTED in reasons or REASON_DIAGRAM_UNSUPPORTED in reasons:
        verdict = VERDICT_REWRITE
    elif REASON_NEEDS_HEDGING in reasons:
        verdict = VERDICT_REWRITE
    elif reasons:
        verdict = VERDICT_REWRITE
    else:
        verdict = VERDICT_PASS

    return {
        "claim_id": segment.get("claim_id"),
        "slide_index": segment.get("slide_index"),
        "verdict": verdict,
        "reasons": reasons,
        "reason_codes": list(reasons),  # Day 3: explicit for debug bundle
        "pointers": pointers,
        "is_image_claim": is_image_claim,
        "required_evidence_kinds": required_evidence_kinds,
        "confidence_used": round(confidence_used, 3),
    }


def verify_script(
    script: Dict[str, Any],
    evidence_index: Dict[str, Any],
    unified_graphs_by_slide: Dict[int, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Verify all segments. Return (verify_report list, coverage dict).
    """
    segments = script.get("segments", [])
    evidence_by_id = _evidence_by_id(evidence_index)
    report: List[Dict[str, Any]] = []
    total = len(segments)
    with_evidence = 0
    entities_grounded = 0
    entities_total = 0
    pass_count = 0
    rewrite_count = 0
    remove_count = 0

    for seg in segments:
        slide_index = seg.get("slide_index", 0)
        graph = unified_graphs_by_slide.get(slide_index, {"nodes": [], "edges": [], "clusters": []})
        entry = verify_segment(seg, evidence_by_id, graph)
        report.append(entry)
        if seg.get("evidence_ids"):
            with_evidence += 1
        eids = seg.get("entity_ids") or []
        entities_total += len(eids)
        node_ids, edge_ids = _graph_entity_ids(graph)
        for eid in eids:
            if eid in node_ids or eid in edge_ids:
                entities_grounded += 1
        if entry["verdict"] == VERDICT_PASS:
            pass_count += 1
        elif entry["verdict"] == VERDICT_REWRITE:
            rewrite_count += 1
        else:
            remove_count += 1

    pct_evidence = (with_evidence / total * 100) if total else 0
    pct_grounded = (entities_grounded / entities_total * 100) if entities_total else 100

    coverage = {
        "total_claims": total,
        "claims_with_evidence": with_evidence,
        "pct_claims_with_evidence": round(pct_evidence, 2),
        "entities_total": entities_total,
        "entities_grounded": entities_grounded,
        "pct_entities_grounded": round(pct_grounded, 2),
        "pass": pass_count,
        "rewrite": rewrite_count,
        "remove": remove_count,
    }
    return report, coverage


def _deterministic_rewrite_segment(
    segment: Dict[str, Any],
    graph: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
    report_entry: Optional[Dict[str, Any]] = None,
) -> str:
    """Produce safe narration from evidence content + graph labels (no LLM). Add hedging if low confidence."""
    nodes = {n.get("node_id"): n for n in graph.get("nodes", [])}
    edges = {e.get("edge_id"): e for e in graph.get("edges", [])}
    entity_ids = segment.get("entity_ids") or []
    evidence_ids = segment.get("evidence_ids") or []
    _, min_conf = _get_cited_image_evidence_kinds_and_confidence(segment, evidence_by_id)
    use_hedging = min_conf < HEDGING_CONFIDENCE_THRESHOLD and min_conf > 0
    if report_entry and REASON_NEEDS_HEDGING in (report_entry.get("reasons") or []):
        use_hedging = True
    prefix = "This slide appears to show " if use_hedging else ""
    # Use first evidence content snippet as base
    parts = []
    for eid in evidence_ids[:1]:
        ev = evidence_by_id.get(eid)
        if ev and ev.get("content"):
            content = (ev.get("content") or "").strip()
            if len(content) > 300:
                content = content[:300] + "..."
            parts.append(prefix + content if use_hedging and prefix else content)
    if parts:
        return parts[0]
    # Fallback: describe entities from graph
    labels = []
    for eid in entity_ids:
        if eid in nodes:
            labels.append(nodes[eid].get("label_text") or eid[:8])
        elif eid in edges:
            e = edges[eid]
            src = nodes.get(e.get("src_node_id"))
            dst = nodes.get(e.get("dst_node_id"))
            a = (src.get("label_text") if src else None) or "A"
            b = (dst.get("label_text") if dst else None) or "B"
            labels.append(f"{a} to {b}")
    if labels:
        base = "This slide shows: " + ", ".join(labels) + "."
        return ("This slide appears to show: " + ", ".join(labels) + ".") if use_hedging else base
    return (
        "This slide appears to include visual content."
        if use_hedging
        else "This segment describes content on this slide."
    )


def run_rewrite_loop(
    job_id: str,
    script_draft: Dict[str, Any],
    evidence_index: Dict[str, Any],
    unified_graphs_by_slide: Dict[int, Dict[str, Any]],
    explain_plan: Optional[Dict[str, Any]] = None,
    llm_provider: Optional["LLMProvider"] = None,
    max_iters: int = DEFAULT_MAX_VERIFY_ITERS,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Run verifier; for REWRITE segments regenerate via provider (or deterministic rewrite), re-verify.
    Stop when no REWRITE or max_iters. Return (verified_script, verify_report, coverage).
    """
    segments = list(script_draft.get("segments", []))
    evidence_by_id = _evidence_by_id(evidence_index)
    report: List[Dict[str, Any]] = []
    coverage: Dict[str, Any] = {}
    iter_count = 0

    while iter_count < max_iters:
        report, coverage = verify_script(
            {"segments": segments},
            evidence_index,
            unified_graphs_by_slide,
        )
        report_by_claim = {r["claim_id"]: r for r in report}
        rewrite_claim_ids = {r["claim_id"] for r in report if r["verdict"] == VERDICT_REWRITE}
        if not rewrite_claim_ids:
            break

        # Regenerate REWRITE segments
        for i, seg in enumerate(segments):
            cid = seg.get("claim_id")
            if cid not in rewrite_claim_ids:
                continue
            slide_index = seg.get("slide_index", 0)
            graph = unified_graphs_by_slide.get(
                slide_index, {"nodes": [], "edges": [], "clusters": []}
            )
            if llm_provider and explain_plan:
                # Build minimal section for provider
                section = {
                    "section_type": "rewrite",
                    "slide_index": slide_index,
                    "entity_ids": seg.get("entity_ids", []),
                    "evidence_ids": seg.get("evidence_ids", []),
                    "cluster_ids": [],
                }
                new_text = llm_provider.generate_segment(
                    section=section,
                    graph=graph,
                    evidence_ids=seg.get("evidence_ids", []),
                    entity_ids=seg.get("entity_ids", []),
                    rag_snippets=None,
                )
            else:
                report_ent = report_by_claim.get(cid, {})
                new_text = _deterministic_rewrite_segment(seg, graph, evidence_by_id, report_ent)
            reas = report_by_claim.get(cid, {}).get("reasons") or []
            used_hedging = seg.get("used_hedging") or (REASON_NEEDS_HEDGING in reas)
            segments[i] = {**seg, "text": new_text, "used_hedging": used_hedging}
        iter_count += 1

    # Build verified script: drop REMOVE, keep PASS and (after rewrite) passed
    report, coverage = verify_script(
        {"segments": segments},
        evidence_index,
        unified_graphs_by_slide,
    )
    report_by_claim = {r["claim_id"]: r for r in report}
    verified_segments = [
        seg
        for seg in segments
        if report_by_claim.get(seg.get("claim_id"), {}).get("verdict") == VERDICT_PASS
    ]

    verified_script = {
        "schema_version": "1.0",
        "job_id": job_id,
        "draft": False,
        "verified": True,
        "segments": verified_segments,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    return verified_script, report, coverage


def build_verify_report_payload(
    job_id: str,
    report: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Payload for script/verify_report.json."""
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "report": report,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }


def build_coverage_payload(
    job_id: str,
    coverage: Dict[str, Any],
) -> Dict[str, Any]:
    """Payload for script/coverage.json."""
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        **coverage,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
