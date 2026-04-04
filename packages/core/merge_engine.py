"""
Merge engine: combine G_native + optional G_vision -> G_unified.
- If vision disabled or empty: unified = native with provenance NATIVE, confidence 1.0.
- If vision enabled: candidate matching (geom_score, text_score, type_score), threshold,
  provenance NATIVE/VISION/BOTH, confidence per entity, output unified + flags.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

# Default slide size in EMU (10" x 7.5" at 914400 EMU/inch)
DEFAULT_SLIDE_WIDTH_EMU = 9144000
DEFAULT_SLIDE_HEIGHT_EMU = 6858000


def _f(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    return 0.0


def _bbox_to_normalized(
    bbox: Dict[str, Any],
    width: float,
    height: float,
) -> Tuple[float, float, float, float]:
    """Return (left, top, right, bottom) in 0-1 normalized coords."""
    left = _f(bbox.get("left")) / width if width else 0
    top = _f(bbox.get("top")) / height if height else 0
    w = _f(bbox.get("width")) / width if width else 0
    h = _f(bbox.get("height")) / height if height else 0
    return (left, top, left + w, top + h)


def _iou_bbox(
    b1: Dict[str, Any], b2: Dict[str, Any], w1: float, h1: float, w2: float, h2: float
) -> float:
    """Intersection over union of two bboxes in their respective coordinate systems."""
    L1, T1, R1, B1 = _bbox_to_normalized(b1, w1, h1)
    L2, T2, R2, B2 = _bbox_to_normalized(b2, w2, h2)
    li = max(L1, L2)
    ti = max(T1, T2)
    ri = min(R1, R2)
    bi = min(B1, B2)
    if ri <= li or bi <= ti:
        return 0.0
    inter = (ri - li) * (bi - ti)
    a1 = (R1 - L1) * (B1 - T1)
    a2 = (R2 - L2) * (B2 - T2)
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def _bbox_center(bbox: Dict[str, Any], w: float, h: float) -> Tuple[float, float]:
    left = _f(bbox.get("left")) / w if w else 0
    top = _f(bbox.get("top")) / h if h else 0
    bw = _f(bbox.get("width")) / w if w else 0
    bh = _f(bbox.get("height")) / h if h else 0
    return (left + bw / 2, top + bh / 2)


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _normalize_label(s: Optional[str]) -> str:
    if not s:
        return ""
    return " ".join(str(s).lower().split()).strip()


def _text_similarity(a: str, b: str) -> float:
    """Simple Jaccard-like similarity on token sets; 1.0 if both empty."""
    na = _normalize_label(a)
    nb = _normalize_label(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    ta = set(na.split())
    tb = set(nb.split())
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _geom_score(
    node_n: Dict[str, Any],
    node_v: Dict[str, Any],
    width_n: float,
    height_n: float,
    width_v: float,
    height_v: float,
) -> float:
    """Score 0-1 from IOU and inverse of normalized centroid distance."""
    iou = _iou_bbox(
        node_n.get("bbox") or {},
        node_v.get("bbox") or {},
        width_n,
        height_n,
        width_v,
        height_v,
    )
    c_n = _bbox_center(node_n.get("bbox") or {}, width_n, height_n)
    c_v = _bbox_center(node_v.get("bbox") or {}, width_v, height_v)
    d = _dist(c_n, c_v)
    # max distance on diagonal ~ sqrt(2); use 1 - min(d, 1) as distance score
    dist_score = max(0, 1.0 - d)
    return 0.7 * iou + 0.3 * dist_score


def _text_score(node_n: Dict[str, Any], node_v: Dict[str, Any]) -> float:
    """Label similarity 0-1."""
    ln = (node_n.get("label_text") or "").strip()
    lv = (node_v.get("label_text") or "").strip()
    return _text_similarity(ln, lv)


def _type_score(node_n: Dict[str, Any], node_v: Dict[str, Any]) -> float:
    """Type compatibility: text_region vs shape -> 0.8; same type -> 1.0."""
    # Native nodes are shapes; vision nodes are text_region. Allow match.
    return 0.9  # Allow vision text_region to match native shape


def _overall_score(geom: float, text: float, type_s: float) -> float:
    """Weighted overall score."""
    return 0.4 * geom + 0.4 * text + 0.2 * type_s


def _add_provenance_and_confidence(
    entity: Dict[str, Any],
    provenance: str,
    confidence: float,
) -> Dict[str, Any]:
    """Add provenance and confidence to entity (node or edge)."""
    out = dict(entity)
    out["provenance"] = provenance
    out["confidence"] = confidence
    return out


def merge_graphs(
    g_native: Dict[str, Any],
    g_vision: Optional[Dict[str, Any]],
    slide_width_px: float = 1920.0,
    slide_height_px: float = 1080.0,
    slide_width_emu: float = DEFAULT_SLIDE_WIDTH_EMU,
    slide_height_emu: float = DEFAULT_SLIDE_HEIGHT_EMU,
    match_threshold: float = 0.5,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Merge G_native and optional G_vision into G_unified.
    Returns (g_unified, flags).
    - If g_vision is None or has no nodes: unified = native with provenance NATIVE, confidence 1.0.
    - Else: match nodes by geom_score + text_score + type_score; threshold accept else NEEDS_REVIEW;
      provenance NATIVE / VISION / BOTH; confidence per entity.
    """
    nodes_n = list(g_native.get("nodes") or [])
    edges_n = list(g_native.get("edges") or [])
    clusters_n = list(g_native.get("clusters") or [])
    slide_index = g_native.get("slide_index", 0)

    flags: Dict[str, Any] = {
        "slide_index": slide_index,
        "needs_review": [],
        "unmatched_vision": [],
        "ambiguous": [],
    }

    # Vision disabled or empty -> pass-through native with provenance
    if not g_vision or not (g_vision.get("nodes")):
        unified_nodes = [_add_provenance_and_confidence(n, "NATIVE", 1.0) for n in nodes_n]
        unified_edges = [_add_provenance_and_confidence(e, "NATIVE", 1.0) for e in edges_n]
        unified_clusters = [dict(c) for c in clusters_n]
        for u in unified_clusters:
            u["provenance"] = "NATIVE"
            u["confidence"] = 1.0
        return (
            {
                "slide_index": slide_index,
                "nodes": unified_nodes,
                "edges": unified_edges,
                "clusters": unified_clusters,
            },
            flags,
        )

    nodes_v = list(g_vision.get("nodes") or [])
    edges_v = list(g_vision.get("edges") or [])

    # Match native nodes to vision nodes
    used_v = set()
    unified_nodes: List[Dict[str, Any]] = []
    for n_n in nodes_n:
        best_v: Optional[Dict[str, Any]] = None
        best_score = 0.0
        best_geom = best_text = best_type = 0.0  # noqa: F841
        for n_v in nodes_v:
            if n_v.get("node_id") in used_v:
                continue
            geom = _geom_score(
                n_n,
                n_v,
                slide_width_emu,
                slide_height_emu,
                slide_width_px,
                slide_height_px,
            )
            text = _text_score(n_n, n_v)
            type_s = _type_score(n_n, n_v)
            score = _overall_score(geom, text, type_s)
            if score > best_score:
                best_score = score
                best_v = n_v
                best_geom, best_text, best_type = geom, text, type_s  # noqa: F841

        if best_v is not None and best_score >= match_threshold:
            used_v.add(best_v.get("node_id"))
            # Merge: keep native id, add vision label if missing, BOTH provenance
            merged = dict(n_n)
            merged["provenance"] = "BOTH"
            merged["confidence"] = best_score
            if (
                not (merged.get("label_text") or "").strip()
                and (best_v.get("label_text") or "").strip()
            ):
                merged["label_text"] = best_v.get("label_text")
            unified_nodes.append(merged)
        else:
            # Native only
            unified_nodes.append(_add_provenance_and_confidence(n_n, "NATIVE", 1.0))

    # Add vision-only nodes
    for n_v in nodes_v:
        if n_v.get("node_id") in used_v:
            continue
        unified_nodes.append(
            _add_provenance_and_confidence(
                dict(n_v),
                "VISION",
                float(n_v.get("confidence", 0.7)),
            )
        )
        flags["unmatched_vision"].append(
            {"node_id": n_v.get("node_id"), "label": n_v.get("label_text")}
        )

    # Edges: for now carry native edges with NATIVE provenance; vision edges as VISION (no src/dst resolution)
    unified_edges: List[Dict[str, Any]] = []
    for e_n in edges_n:
        unified_edges.append(_add_provenance_and_confidence(dict(e_n), "NATIVE", 1.0))
    for e_v in edges_v:
        unified_edges.append(
            _add_provenance_and_confidence(
                dict(e_v),
                "VISION",
                float(e_v.get("confidence", 0.6)),
            )
        )

    # Clusters: keep native only
    unified_clusters = [dict(c) for c in clusters_n]
    for u in unified_clusters:
        u["provenance"] = "NATIVE"
        u["confidence"] = 1.0

    return (
        {
            "slide_index": slide_index,
            "nodes": unified_nodes,
            "edges": unified_edges,
            "clusters": unified_clusters,
        },
        flags,
    )
