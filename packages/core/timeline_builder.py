"""
Timeline builder (Fig3 step 16, Fig7).
Maps verified script + alignment to timeline actions: HIGHLIGHT, TRACE, ZOOM.
Output: timeline/timeline.json with actions[] (t_start, t_end, entity_ids, bbox/path, claim_id, evidence_ids).
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Default slide size in EMU (10" x 7.5" at 914400 EMU/inch)
DEFAULT_SLIDE_WIDTH_EMU = 9144000
DEFAULT_SLIDE_HEIGHT_EMU = 6858000

ACTION_HIGHLIGHT = "HIGHLIGHT"
ACTION_TRACE = "TRACE"
ACTION_ZOOM = "ZOOM"

# Day 3: image/diagram evidence kinds; segment citing these may get HIGHLIGHT/ZOOM on image bbox
IMAGE_EVIDENCE_KINDS = frozenset(
    {
        "IMAGE_ASSET",
        "IMAGE_CAPTION",
        "IMAGE_OBJECTS",
        "IMAGE_ACTIONS",
        "IMAGE_TAGS",
        "DIAGRAM_TYPE",
        "DIAGRAM_ENTITIES",
        "DIAGRAM_INTERACTIONS",
        "DIAGRAM_SUMMARY",
        "SLIDE_CAPTION",
    }
)


def _f(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    return 0.0


def emu_to_pixel(
    left_emu: float,
    top_emu: float,
    width_emu: float,
    height_emu: float,
    slide_width_px: float,
    slide_height_px: float,
    slide_width_emu: float = DEFAULT_SLIDE_WIDTH_EMU,
    slide_height_emu: float = DEFAULT_SLIDE_HEIGHT_EMU,
) -> Dict[str, float]:
    """Convert bbox from EMU to pixel coordinates (x, y, w, h)."""
    scale_x = slide_width_px / slide_width_emu if slide_width_emu else 0
    scale_y = slide_height_px / slide_height_emu if slide_height_emu else 0
    return {
        "x": left_emu * scale_x,
        "y": top_emu * scale_y,
        "w": width_emu * scale_x,
        "h": height_emu * scale_y,
    }


def resolve_node_bbox(
    node: Dict[str, Any],
    slide_width_px: float,
    slide_height_px: float,
) -> Optional[Dict[str, float]]:
    """Return bbox in pixels for a node."""
    bbox = node.get("bbox") or {}
    left = _f(bbox.get("left"))
    top = _f(bbox.get("top"))
    w = _f(bbox.get("width"))
    h = _f(bbox.get("height"))
    if w <= 0 or h <= 0:
        return None
    return emu_to_pixel(left, top, w, h, slide_width_px, slide_height_px)


def resolve_edge_path(
    edge: Dict[str, Any],
    nodes_by_id: Dict[str, Dict[str, Any]],
    slide_width_px: float,
    slide_height_px: float,
) -> Optional[List[Dict[str, float]]]:
    """Return path as list of {x,y} in pixels (line from src center to dst center)."""
    src_id = edge.get("src_node_id")
    dst_id = edge.get("dst_node_id")
    src = nodes_by_id.get(src_id) if src_id else None
    dst = nodes_by_id.get(dst_id) if dst_id else None
    if not src or not dst:
        return None
    src_bbox = src.get("bbox") or {}
    dst_bbox = dst.get("bbox") or {}
    src_cx = _f(src_bbox.get("left")) + _f(src_bbox.get("width")) / 2
    src_cy = _f(src_bbox.get("top")) + _f(src_bbox.get("height")) / 2
    dst_cx = _f(dst_bbox.get("left")) + _f(dst_bbox.get("width")) / 2
    dst_cy = _f(dst_bbox.get("top")) + _f(dst_bbox.get("height")) / 2
    scale_x = slide_width_px / DEFAULT_SLIDE_WIDTH_EMU
    scale_y = slide_height_px / DEFAULT_SLIDE_HEIGHT_EMU
    return [
        {"x": src_cx * scale_x, "y": src_cy * scale_y},
        {"x": dst_cx * scale_x, "y": dst_cy * scale_y},
    ]


def resolve_cluster_bbox(
    cluster: Dict[str, Any],
    slide_width_px: float,
    slide_height_px: float,
) -> Optional[Dict[str, float]]:
    """Return bbox in pixels for a cluster."""
    bbox = cluster.get("bbox") or {}
    left = _f(bbox.get("left"))
    top = _f(bbox.get("top"))
    w = _f(bbox.get("width"))
    h = _f(bbox.get("height"))
    if w <= 0 or h <= 0:
        return None
    return emu_to_pixel(left, top, w, h, slide_width_px, slide_height_px)


def choose_action_type(
    segment: Dict[str, Any],
    graph: Dict[str, Any],
) -> str:
    """Heuristics: 1 entity node => HIGHLIGHT, edge => TRACE, cluster => ZOOM, 2+ nodes => HIGHLIGHT (first)."""
    entity_ids = segment.get("entity_ids") or []
    if not entity_ids:
        return ACTION_HIGHLIGHT
    _nodes = {n.get("node_id"): n for n in graph.get("nodes", [])}  # noqa: F841
    edges = {e.get("edge_id"): e for e in graph.get("edges", [])}
    clusters = {c.get("cluster_id"): c for c in graph.get("clusters", [])}
    for eid in entity_ids:
        if eid in edges:
            return ACTION_TRACE
        if eid in clusters:
            return ACTION_ZOOM
    return ACTION_HIGHLIGHT


def _resolve_image_bbox_from_evidence(
    segment: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
    images_index: Dict[str, Any],
    slide_index: int,
    width_px: float,
    height_px: float,
) -> Tuple[Optional[List[str]], Optional[Dict[str, float]]]:
    """
    Day 3: If segment cites IMAGE_* or DIAGRAM_* evidence, return (entity_ids for image, bbox in pixels).
    entity_ids use form image:IMG_{image_id}; bbox from evidence refs or images/index.json.
    """
    evidence_ids = segment.get("evidence_ids") or []
    for eid in evidence_ids:
        ev = evidence_by_id.get(eid)
        if not ev or ev.get("kind") not in IMAGE_EVIDENCE_KINDS:
            continue
        refs = ev.get("refs") or []
        for ref in refs:
            if ref.get("ref_type") != "IMAGE" or ref.get("slide_index") != slide_index:
                continue
            url = (ref.get("url") or ref.get("image_uri") or "").strip()
            # Match to images index for image_id and EMU bbox
            for img in images_index.get("images") or []:
                if (img.get("uri") or "").strip() != url or img.get("slide_index") != slide_index:
                    continue
                image_id = img.get("image_id", "")
                if not image_id:
                    continue
                bbox_emu = img.get("bbox") or {}
                left = _f(bbox_emu.get("x"))
                top = _f(bbox_emu.get("y"))
                w = _f(bbox_emu.get("w"))
                h = _f(bbox_emu.get("h"))
                if w <= 0 or h <= 0:
                    # Fallback: ref may have bbox_x/y/w/h (same EMU convention)
                    left = _f(ref.get("bbox_x"))
                    top = _f(ref.get("bbox_y"))
                    w = _f(ref.get("bbox_w"))
                    h = _f(ref.get("bbox_h"))
                if w <= 0 or h <= 0:
                    continue
                geometry = emu_to_pixel(left, top, w, h, width_px, height_px)
                return (["image:IMG_" + image_id], geometry)
        # Fallback: use ref bbox (EMU) when image not in index
        for ref in refs:
            if ref.get("ref_type") != "IMAGE" or ref.get("slide_index") != slide_index:
                continue
            left = _f(ref.get("bbox_x"))
            top = _f(ref.get("bbox_y"))
            w = _f(ref.get("bbox_w"))
            h = _f(ref.get("bbox_h"))
            if w <= 0 or h <= 0:
                continue
            geometry = emu_to_pixel(left, top, w, h, width_px, height_px)
            # Synthetic image entity id from evidence_id for audit
            return (["image:IMG_" + (eid[:16] or "unknown")], geometry)
    return (None, None)


def build_timeline(
    job_id: str,
    verified_script: Dict[str, Any],
    alignment: Dict[str, Any],
    unified_graphs_by_slide: Dict[int, Dict[str, Any]],
    slide_dimensions: Dict[int, Tuple[float, float]],
    images_index: Optional[Dict[str, Any]] = None,
    evidence_index: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build timeline/timeline.json: actions[] with type, t_start, t_end, entity_ids, bbox/path, claim_id, evidence_ids.
    Day 3: When segment cites image/diagram evidence, add HIGHLIGHT or ZOOM for image entity (image:IMG_{id}).
    """
    segments = verified_script.get("segments", [])
    alignment_entries = {e.get("claim_id"): e for e in alignment.get("segments", [])}
    actions: List[Dict[str, Any]] = []
    action_ix = 0
    evidence_by_id: Dict[str, Dict[str, Any]] = {}
    if evidence_index:
        for ev in evidence_index.get("evidence_items", []):
            eid = ev.get("evidence_id")
            if eid:
                evidence_by_id[eid] = ev
    images_index = images_index or {}

    for seg in segments:
        claim_id = seg.get("claim_id", "")
        slide_index = seg.get("slide_index", 0)
        entity_ids = list(seg.get("entity_ids") or [])
        evidence_ids = list(seg.get("evidence_ids") or [])
        align = alignment_entries.get(claim_id, {})
        t_start = float(align.get("t_start", 0))
        t_end = float(align.get("t_end", t_start + 2))

        graph = unified_graphs_by_slide.get(slide_index, {"nodes": [], "edges": [], "clusters": []})
        width_px, height_px = slide_dimensions.get(slide_index, (1280, 720))

        nodes_by_id = {n.get("node_id"): n for n in graph.get("nodes", [])}
        edges_by_id = {e.get("edge_id"): e for e in graph.get("edges", [])}
        clusters_by_id = {c.get("cluster_id"): c for c in graph.get("clusters", [])}

        action_type = choose_action_type(seg, graph)
        geometry = None
        path = None

        if entity_ids:
            eid = entity_ids[0]
            if eid in nodes_by_id:
                geometry = resolve_node_bbox(nodes_by_id[eid], width_px, height_px)
            elif eid in edges_by_id:
                path = resolve_edge_path(edges_by_id[eid], nodes_by_id, width_px, height_px)
            elif eid in clusters_by_id:
                geometry = resolve_cluster_bbox(clusters_by_id[eid], width_px, height_px)

        # Day 3: When narration references image/diagram evidence, add HIGHLIGHT or ZOOM for image bbox
        if (geometry is None and path is None) and evidence_ids and evidence_by_id and images_index:
            image_entity_ids, image_bbox = _resolve_image_bbox_from_evidence(
                seg, evidence_by_id, images_index, slide_index, width_px, height_px
            )
            if image_entity_ids and image_bbox:
                geometry = image_bbox
                entity_ids = image_entity_ids
                action_type = ACTION_HIGHLIGHT  # or ZOOM; use HIGHLIGHT for image region

        action_id = hashlib.sha256(f"{job_id}|{action_ix}|{claim_id}".encode()).hexdigest()[:16]
        action_ix += 1

        action = {
            "action_id": action_id,
            "type": action_type,
            "t_start": round(t_start, 3),
            "t_end": round(t_end, 3),
            "slide_index": slide_index,
            "entity_ids": entity_ids,
            "claim_id": claim_id,
            "evidence_ids": evidence_ids,
        }
        if geometry:
            action["bbox"] = geometry
        if path:
            action["path"] = path
        actions.append(action)

    total_duration = max((a["t_end"] for a in actions), default=0)

    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "actions": actions,
        "total_duration_seconds": round(total_duration, 3),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
