"""
G_native graph extraction from ppt/slide_i.json (Fig 4 + Fig 3 step 6).
Produces nodes from shapes, edges from connectors, clusters from groups;
stable node_id/edge_id/cluster_id; endpoint resolution with NEEDS_REVIEW for ambiguous edges.
Outputs graphs/native/slide_i.json, optional index.json, flags.json; EntityLink rows (LABEL/GEOMETRY).
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# EMU to float for geometry
def _f(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if hasattr(val, "emu"):
        return float(val.emu)
    return 0.0


def _node_id(slide_index: int, ppt_shape_id: str) -> str:
    """Stable node_id: hash(slide_index + ppt_shape_id)."""
    return hashlib.sha256(f"{slide_index}|{ppt_shape_id}".encode("utf-8")).hexdigest()


def _edge_id(slide_index: int, ppt_connector_id: str) -> str:
    """Stable edge_id: hash(slide_index + ppt_connector_id)."""
    return hashlib.sha256(f"{slide_index}|{ppt_connector_id}".encode("utf-8")).hexdigest()


def _cluster_id(slide_index: int, group_id: str) -> str:
    """Stable cluster_id: hash(slide_index + group_id)."""
    return hashlib.sha256(f"{slide_index}|{group_id}".encode("utf-8")).hexdigest()


def _bbox_center(bbox: Dict[str, Any]) -> Tuple[float, float]:
    left = _f(bbox.get("left"))
    top = _f(bbox.get("top"))
    w = _f(bbox.get("width"))
    h = _f(bbox.get("height"))
    return (left + w / 2.0, top + h / 2.0)


def _bbox_contains(bbox: Dict[str, Any], x: float, y: float) -> bool:
    left = _f(bbox.get("left"))
    top = _f(bbox.get("top"))
    w = _f(bbox.get("width"))
    h = _f(bbox.get("height"))
    return left <= x <= left + w and top <= y <= top + h


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def _label_from_text_runs(text_runs: List[Dict]) -> str:
    if not text_runs:
        return ""
    s = " ".join(r.get("text", "") for r in text_runs).strip()
    return " ".join(s.split())  # collapse whitespace


def _flatten_shapes_connectors_groups(
    slide_payload: Dict[str, Any]
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Return (shapes, connectors, groups) including from group children."""
    shapes: List[Dict] = []
    connectors: List[Dict] = []
    groups: List[Dict] = []

    def add(s: Dict) -> None:
        if s.get("ppt_connector_id"):
            connectors.append(s)
        elif s.get("type") == "GROUP" or "children" in s:
            groups.append(s)
            for c in s.get("children", []):
                add(c)
        else:
            shapes.append(s)

    for s in slide_payload.get("shapes", []):
        add(s)
    for c in slide_payload.get("connectors", []):
        add(c)
    for g in slide_payload.get("groups", []):
        add(g)
    return shapes, connectors, groups


def _group_member_shape_ids(group: Dict) -> List[str]:
    """Recursively collect ppt_shape_ids of leaf shapes in a group (nodes only, not connectors)."""
    out: List[str] = []
    for c in group.get("children", []):
        if c.get("ppt_connector_id"):
            continue  # connectors are edges, not cluster members
        if c.get("type") == "GROUP" or "children" in c:
            out.extend(_group_member_shape_ids(c))
        else:
            sid = c.get("ppt_shape_id", "")
            if sid:
                out.append(sid)
    return out


def _resolve_endpoint(x: float, y: float, nodes: List[Dict]) -> Tuple[Optional[str], float, bool]:
    """
    Resolve (x,y) to a node_id. Returns (node_id, confidence, needs_review).
    First try bbox containment, then nearest center. If tie or none -> needs_review.
    """
    candidates_contain = [n for n in nodes if _bbox_contains(n["bbox"], x, y)]
    if len(candidates_contain) == 1:
        return candidates_contain[0]["node_id"], 1.0, False
    if len(candidates_contain) > 1:
        return candidates_contain[0]["node_id"], 0.5, True  # tie
    # No bbox contains; use nearest center
    best_node: Optional[Dict] = None
    best_d = float("inf")
    for n in nodes:
        cx, cy = _bbox_center(n["bbox"])
        d = _dist(x, y, cx, cy)
        if d < best_d:
            best_d = d
            best_node = n
    if best_node is None:
        return None, 0.0, True
    # If multiple nodes at same distance, ambiguous
    ties = [n for n in nodes if abs(_dist(x, y, *_bbox_center(n["bbox"])) - best_d) < 1e-6]
    needs_review = len(ties) > 1
    conf = 0.7 if not needs_review else 0.4
    return best_node["node_id"], conf, needs_review


def build_native_graph_slide(slide_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build G_native for one slide from ppt/slide_i.json payload.
    Returns dict with nodes, edges, clusters, needs_review_list.
    """
    slide_index = slide_payload.get("slide_index", 0)
    shapes, connectors, groups = _flatten_shapes_connectors_groups(slide_payload)

    # Nodes from shapes
    nodes: List[Dict[str, Any]] = []
    ppt_to_node: Dict[str, str] = {}
    for s in shapes:
        ppt_shape_id = s.get("ppt_shape_id", "")
        if not ppt_shape_id:
            continue
        nid = _node_id(slide_index, ppt_shape_id)
        ppt_to_node[ppt_shape_id] = nid
        bbox = s.get("bbox") or {}
        center = _bbox_center(bbox)
        label = _label_from_text_runs(s.get("text_runs") or [])
        nodes.append(
            {
                "node_id": nid,
                "ppt_shape_id": ppt_shape_id,
                "bbox": bbox,
                "center": {"x": center[0], "y": center[1]},
                "label_text": label,
                "z_index": s.get("z_order", 0),
                "cluster_id": None,
                "confidence": 1.0,
            }
        )

    # Clusters from groups
    clusters: List[Dict[str, Any]] = []
    group_members: Dict[str, List[str]] = {}  # cluster_id -> member node_ids
    for g in groups:
        gid = g.get("ppt_shape_id", "")
        if not gid:
            continue
        cid = _cluster_id(slide_index, gid)
        members_ppt = _group_member_shape_ids(g)
        member_node_ids = [ppt_to_node[p] for p in members_ppt if p in ppt_to_node]
        group_members[cid] = member_node_ids
        bbox = g.get("bbox") or {}
        title = _label_from_text_runs(g.get("text_runs") or [])
        clusters.append(
            {
                "cluster_id": cid,
                "group_id": gid,
                "member_node_ids": member_node_ids,
                "bbox": bbox,
                "title": title or None,
            }
        )
        for nid in member_node_ids:
            for n in nodes:
                if n["node_id"] == nid:
                    n["cluster_id"] = cid
                    break

    # Edges from connectors; resolve endpoints
    edges: List[Dict[str, Any]] = []
    needs_review_list: List[Dict[str, Any]] = []
    for conn in connectors:
        pcid = conn.get("ppt_connector_id", "")
        if not pcid:
            continue
        eid = _edge_id(slide_index, pcid)
        endpts = conn.get("endpoints") or {}
        begin = endpts.get("begin") or {}
        end = endpts.get("end") or {}
        bx, by = _f(begin.get("x")), _f(begin.get("y"))
        ex, ey = _f(end.get("x")), _f(end.get("y"))

        src_id, conf_src, rev_src = _resolve_endpoint(bx, by, nodes)
        dst_id, conf_dst, rev_dst = _resolve_endpoint(ex, ey, nodes)
        needs_review = rev_src or rev_dst or src_id is None or dst_id is None
        confidence = min(conf_src, conf_dst) if (src_id and dst_id) else 0.0

        edge = {
            "edge_id": eid,
            "ppt_connector_id": pcid,
            "src_node_id": src_id,
            "dst_node_id": dst_id,
            "label_text": (conn.get("label") or "").strip() or None,
            "style": conn.get("style") or "",
            "confidence": confidence,
            "needs_review": needs_review,
        }
        edges.append(edge)
        if needs_review:
            needs_review_list.append(
                {
                    "slide_index": slide_index,
                    "edge_id": eid,
                    "ppt_connector_id": pcid,
                    "reason": "ambiguous_endpoints"
                    if (src_id is None or dst_id is None or rev_src or rev_dst)
                    else "unresolved",
                }
            )

    return {
        "slide_index": slide_index,
        "nodes": nodes,
        "edges": edges,
        "clusters": clusters,
        "needs_review": needs_review_list,
    }


def build_native_graph_and_persist(
    job_id: str,
    project_id: str,
    slides_data: List[Dict[str, Any]],
    db_session: Any,
    minio_client: Any,
) -> Dict[str, Any]:
    """
    Build G_native for each slide, write graphs/native/slide_i.json to MinIO,
    optional index.json and flags.json, and create EntityLink rows (entity_id -> evidence_id, LABEL/GEOMETRY).
    Uses same evidence_id formula as evidence_index: hash(job_id|slide_index|kind|offset_key).
    """
    from apps.api.models import EvidenceItem, EntityLink

    def _evidence_id_shape(job_id: str, slide_index: int, ppt_shape_id: str) -> str:
        return hashlib.sha256(
            f"{job_id}|{slide_index}|SHAPE_LABEL|{ppt_shape_id}".encode("utf-8")
        ).hexdigest()

    def _evidence_id_connector(job_id: str, slide_index: int, ppt_connector_id: str) -> str:
        return hashlib.sha256(
            f"{job_id}|{slide_index}|CONNECTOR|{ppt_connector_id}".encode("utf-8")
        ).hexdigest()

    created_at = datetime.utcnow()
    all_needs_review: List[Dict] = []
    index_entries: List[Dict] = []

    for slide_payload in slides_data:
        slide_index = slide_payload.get("slide_index", 0)
        g = build_native_graph_slide(slide_payload)

        # Write graphs/native/slide_i.json
        storage_path = f"jobs/{job_id}/graphs/native/slide_{slide_index:03d}.json"
        payload = {
            "slide_index": slide_index,
            "nodes": g["nodes"],
            "edges": g["edges"],
            "clusters": g["clusters"],
            "needs_review": g["needs_review"],
        }
        minio_client.put(
            storage_path, json.dumps(payload, indent=2).encode("utf-8"), "application/json"
        )
        index_entries.append({"slide_index": slide_index, "path": storage_path})
        all_needs_review.extend(g["needs_review"])

        # EntityLink: node_id -> evidence_id (LABEL, GEOMETRY)
        for n in g["nodes"]:
            ppt_shape_id = n.get("ppt_shape_id", "")
            if not ppt_shape_id:
                continue
            ev_id = _evidence_id_shape(job_id, slide_index, ppt_shape_id)
            # Only add if evidence_item exists (evidence index ran first)
            if db_session.query(EvidenceItem).filter(EvidenceItem.evidence_id == ev_id).first():
                for role in ("LABEL", "GEOMETRY"):
                    db_session.add(
                        EntityLink(
                            entity_link_id=str(uuid.uuid4()),
                            entity_id=n["node_id"],
                            evidence_id=ev_id,
                            role=role,
                        )
                    )
        # EntityLink: edge_id -> evidence_id (LABEL, GEOMETRY)
        for e in g["edges"]:
            ppt_connector_id = e.get("ppt_connector_id", "")
            if not ppt_connector_id:
                continue
            ev_id = _evidence_id_connector(job_id, slide_index, ppt_connector_id)
            if db_session.query(EvidenceItem).filter(EvidenceItem.evidence_id == ev_id).first():
                for role in ("LABEL", "GEOMETRY"):
                    db_session.add(
                        EntityLink(
                            entity_link_id=str(uuid.uuid4()),
                            entity_id=e["edge_id"],
                            evidence_id=ev_id,
                            role=role,
                        )
                    )

    # Optional index.json
    index_path = f"jobs/{job_id}/graphs/native/index.json"
    index_payload = {
        "job_id": job_id,
        "slides": index_entries,
        "created_at": created_at.isoformat() + "Z",
    }
    minio_client.put(
        index_path, json.dumps(index_payload, indent=2).encode("utf-8"), "application/json"
    )

    # flags.json (NEEDS_REVIEW)
    flags_path = f"jobs/{job_id}/graphs/native/flags.json"
    flags_payload = {
        "job_id": job_id,
        "needs_review": all_needs_review,
        "created_at": created_at.isoformat() + "Z",
    }
    minio_client.put(
        flags_path, json.dumps(flags_payload, indent=2).encode("utf-8"), "application/json"
    )

    db_session.commit()
    return {"slides": index_entries, "needs_review_count": len(all_needs_review)}
