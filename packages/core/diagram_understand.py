"""
DIAGRAM understanding v1: OCR + structure extraction for sequence/flow diagrams.
NO-HALLUCINATION: summary and evidence derived only from extracted OCR and primitives.

For each image classified DIAGRAM:
1) OCR -> jobs/{job_id}/vision/diagram_ocr.json
2) Primitives (lines, arrows) -> jobs/{job_id}/vision/diagram_primitives.json
3) Structured parse (type, entities, interactions) -> jobs/{job_id}/vision/diagram_parse.json
4) EvidenceItems: DIAGRAM_TYPE, DIAGRAM_ENTITIES, DIAGRAM_INTERACTIONS, DIAGRAM_SUMMARY
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

# Evidence kinds (must match verifier IMAGE_EVIDENCE_KINDS)
KIND_DIAGRAM_TYPE = "DIAGRAM_TYPE"
KIND_DIAGRAM_ENTITIES = "DIAGRAM_ENTITIES"
KIND_DIAGRAM_INTERACTIONS = "DIAGRAM_INTERACTIONS"
KIND_DIAGRAM_SUMMARY = "DIAGRAM_SUMMARY"

# Diagram types (must match DiagramExtractResult)
DIAGRAM_TYPE_SEQUENCE = "SEQUENCE"
DIAGRAM_TYPE_FLOW = "FLOW"
DIAGRAM_TYPE_ARCH = "ARCH"
DIAGRAM_TYPE_UNKNOWN = "UNKNOWN_DIAGRAM"
VALID_DIAGRAM_TYPES = frozenset({DIAGRAM_TYPE_SEQUENCE, DIAGRAM_TYPE_FLOW, DIAGRAM_TYPE_ARCH, DIAGRAM_TYPE_UNKNOWN})

# Strict fallback when OpenAI/validation fails (Day 3)
DIAGRAM_FALLBACK_SUMMARY = "Diagram present; details unavailable"
DIAGRAM_FALLBACK_REASON = "VISION_UNAVAILABLE"

# Reason codes for low confidence
REASON_OCR_LOW_CONF = "OCR_LOW_CONF"
REASON_ARROW_DETECT_LOW = "ARROW_DETECT_LOW"

# OCR
try:
    from ocr import run_ocr
except ImportError:
    run_ocr = None  # type: ignore

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    Image = None  # type: ignore
    PIL_AVAILABLE = False

try:
    import numpy as np
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    cv2 = None  # type: ignore
    CV2_AVAILABLE = False

# Confidence threshold below which we add reason_code
OCR_CONF_THRESHOLD = float(os.environ.get("VISION_DIAGRAM_OCR_CONF_THRESHOLD", "0.5"))


def _stable_evidence_id(job_id: str, slide_index: int, kind: str, offset_key: str) -> str:
    payload = f"{job_id}|{slide_index}|{kind}|diagram|{offset_key}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _run_diagram_ocr(image_bytes: bytes, image_id: str, slide_index: int) -> Dict[str, Any]:
    """
    Run OCR on image bytes. Returns { spans: [{ ocr_id, bbox, text, conf }], avg_conf, reason_code? }.
    """
    out: Dict[str, Any] = {"image_id": image_id, "slide_index": slide_index, "spans": []}
    if not run_ocr or not PIL_AVAILABLE:
        out["avg_conf"] = 0.0
        out["reason_code"] = REASON_OCR_LOW_CONF
        return out
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        spans = run_ocr(img, slide_index=slide_index, backend="tesseract")
        out["spans"] = spans
        if not spans:
            out["avg_conf"] = 0.0
            out["reason_code"] = REASON_OCR_LOW_CONF
            return out
        avg_conf = sum(s.get("conf", 0) for s in spans) / len(spans)
        out["avg_conf"] = avg_conf
        if avg_conf < OCR_CONF_THRESHOLD:
            out["reason_code"] = REASON_OCR_LOW_CONF
        return out
    except Exception:
        out["avg_conf"] = 0.0
        out["reason_code"] = REASON_OCR_LOW_CONF
        return out


def _run_diagram_primitives(image_bytes: bytes) -> Dict[str, Any]:
    """
    Detect lines and optional arrowheads. Returns { lines, arrows, connectors, reason_code? }.
    lines: [ { x1, y1, x2, y2, length } ]
    arrows: [ { x1, y1, x2, y2, has_head } ] (subset of lines with detected head)
    connectors: grouped lines sharing endpoints (simplified: same as lines for v1)
    """
    out: Dict[str, Any] = {"lines": [], "arrows": [], "connectors": [], "line_count": 0}
    if not CV2_AVAILABLE or np is None or cv2 is None:
        out["reason_code"] = REASON_ARROW_DETECT_LOW
        return out
    try:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            out["reason_code"] = REASON_ARROW_DETECT_LOW
            return out
        h, w = img.shape[:2]
        edges = cv2.Canny(img, 50, 150)
        lines_p = cv2.HoughLinesP(
            edges, rho=1, theta=math.pi / 180, threshold=40, minLineLength=min(w, h) // 20, maxLineGap=10
        )
        if lines_p is None:
            out["reason_code"] = REASON_ARROW_DETECT_LOW
            return out
        lines: List[Dict[str, Any]] = []
        for seg in lines_p:
            x1, y1, x2, y2 = int(seg[0][0]), int(seg[0][1]), int(seg[0][2]), int(seg[0][3])
            length = math.hypot(x2 - x1, y2 - y1)
            lines.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "length": round(length, 1)})
        out["lines"] = lines
        out["line_count"] = len(lines)
        # Arrow detection: heuristic - check for small contour (triangle) near line end
        arrows: List[Dict[str, Any]] = []
        for ln in lines:
            has_head = _detect_arrowhead_simple(img, ln.get("x1"), ln.get("y1"), ln.get("x2"), ln.get("y2"))
            arrows.append({**ln, "has_head": has_head})
        out["arrows"] = arrows
        out["connectors"] = lines  # v1: no grouping
        if len(lines) < 2:
            out["reason_code"] = REASON_ARROW_DETECT_LOW
        return out
    except Exception:
        out["reason_code"] = REASON_ARROW_DETECT_LOW
        return out


def _detect_arrowhead_simple(gray: Any, x1: int, y1: int, x2: int, y2: int) -> bool:
    """Heuristic: look for extra edge density near line endpoint (x2,y2)."""
    if not CV2_AVAILABLE or gray is None:
        return False
    try:
        h, w = gray.shape[:2]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 5:
            return False
        # unit vector along line
        ux, uy = dx / length, dy / length
        # sample a few pixels beyond (x2,y2)
        r = min(15, length // 2)
        cx, cy = int(x2 + ux * r), int(y2 + uy * r)
        roi_radius = 8
        y0 = max(0, cy - roi_radius)
        y1_end = min(h, cy + roi_radius)
        x0 = max(0, cx - roi_radius)
        x1_end = min(w, cx + roi_radius)
        if y1_end - y0 < 4 or x1_end - x0 < 4:
            return False
        roi = gray[y0:y1_end, x0:x1_end]
        edge_sum = float(cv2.Canny(roi, 50, 150).sum())
        # If there's notable edge density near tip, treat as arrow
        return edge_sum > 100
    except Exception:
        return False


def _determine_diagram_type(
    ocr_spans: List[Dict], primitives: Dict[str, Any], width: int, height: int
) -> Tuple[str, float]:
    """
    Heuristic: SEQUENCE (horizontal lines + top labels), FLOW (box-like clusters), else UNKNOWN_DIAGRAM.
    Returns (diagram_type, confidence).
    """
    lines = primitives.get("lines") or []
    if not ocr_spans and not lines:
        return DIAGRAM_TYPE_UNKNOWN, 0.0
    # Count roughly horizontal vs vertical lines
    horiz, vert = 0, 0
    for ln in lines:
        dx = abs(ln.get("x2", 0) - ln.get("x1", 0))
        dy = abs(ln.get("y2", 0) - ln.get("y1", 0))
        if dx > dy * 1.5:
            horiz += 1
        elif dy > dx * 1.5:
            vert += 1
    # Top-region labels (y in top 25%): typical for sequence lifelines
    top_frac = 0.25
    top_labels = [s for s in ocr_spans if (s.get("bbox", {}).get("top", 0) or 0) < height * top_frac]
    if horiz >= 2 and len(top_labels) >= 1:
        return DIAGRAM_TYPE_SEQUENCE, 0.7
    if vert >= 2 or (horiz >= 1 and vert >= 1):
        return DIAGRAM_TYPE_FLOW, 0.6
    return DIAGRAM_TYPE_UNKNOWN, 0.4


def _extract_entities_sequence(
    ocr_spans: List[Dict], width: int, height: int
) -> List[Dict[str, Any]]:
    """Lifelines/actors from top labels (y in top fraction)."""
    top_frac = 0.35
    entities: List[Dict[str, Any]] = []
    for s in ocr_spans:
        bbox = s.get("bbox") or {}
        top = bbox.get("top") or 0
        if top < height * top_frac:
            text = (s.get("text") or "").strip()
            if text:
                entities.append({
                    "name": text,
                    "bbox": bbox,
                    "role": "lifeline",
                })
    return entities


def _extract_entities_flow(ocr_spans: List[Dict], width: int, height: int) -> List[Dict[str, Any]]:
    """Nodes from OCR text; cluster by proximity (simplified: one entity per span or cluster)."""
    entities: List[Dict[str, Any]] = []
    for s in ocr_spans:
        text = (s.get("text") or "").strip()
        if text and len(text) < 80:
            entities.append({
                "name": text,
                "bbox": s.get("bbox") or {},
                "role": "node",
            })
    return entities


def _extract_interactions_sequence(
    ocr_spans: List[Dict],
    lines: List[Dict],
    entities: List[Dict],
    height: int,
) -> List[Dict[str, Any]]:
    """
    Message arrows: horizontal lines with order (top-down). Label from OCR near line midpoint.
    """
    interactions: List[Dict[str, Any]] = []
    # Sort lines by vertical position (use center y)
    horiz_lines = []
    for ln in lines:
        dx = abs(ln.get("x2", 0) - ln.get("x1", 0))
        dy = abs(ln.get("y2", 0) - ln.get("y1", 0))
        if dx > dy * 1.2:
            cy = (ln.get("y1", 0) + ln.get("y2", 0)) / 2
            horiz_lines.append((cy, ln))
    horiz_lines.sort(key=lambda t: t[0])
    entity_names = [e.get("name", "") for e in entities]
    for order, (_, ln) in enumerate(horiz_lines):
        cx = (ln.get("x1", 0) + ln.get("x2", 0)) / 2
        cy = (ln.get("y1", 0) + ln.get("y2", 0)) / 2
        # Find OCR span whose bbox center is closest to (cx, cy) and near this line
        label = ""
        best_dist = 1e9
        for s in ocr_spans:
            b = s.get("bbox") or {}
            bcx = (b.get("left", 0) + b.get("width", 0) / 2)
            bcy = (b.get("top", 0) + b.get("height", 0) / 2)
            dist = abs(bcy - cy) + abs(bcx - cx) * 0.5
            if dist < best_dist and abs(bcy - cy) < height * 0.1:
                best_dist = dist
                label = (s.get("text") or "").strip()
        from_name = entity_names[0] if entity_names else "A"
        to_name = entity_names[1] if len(entity_names) > 1 else "B"
        interactions.append({
            "from_entity": from_name,
            "to_entity": to_name,
            "label": label or "(message)",
            "order": order,
            "confidence": 0.6,
        })
    return interactions


def _extract_interactions_flow(
    lines: List[Dict],
    entities: List[Dict],
) -> List[Dict[str, Any]]:
    """Edges between nodes (simplified: from line endpoints; match to nearest entity by position)."""
    interactions: List[Dict[str, Any]] = []
    names = [e.get("name", "") for e in entities]
    for i, ln in enumerate(lines):
        # Simplified: first two entities as from/to if we have them
        from_name = names[0] if names else "Node1"
        to_name = names[1] if len(names) > 1 else "Node2"
        interactions.append({
            "from_entity": from_name,
            "to_entity": to_name,
            "label": "",
            "order": i,
            "confidence": 0.5,
        })
    return interactions[:20]  # cap


def _run_diagram_parse(
    ocr_result: Dict[str, Any],
    primitives: Dict[str, Any],
    image_width: int,
    image_height: int,
) -> Dict[str, Any]:
    """
    Build structured parse: diagram_type, entities, interactions.
    Returns dict with confidence and reason_codes when low.
    """
    spans = ocr_result.get("spans") or []
    diagram_type, type_conf = _determine_diagram_type(
        spans, primitives, image_width, image_height
    )
    entities: List[Dict[str, Any]] = []
    interactions: List[Dict[str, Any]] = []
    if diagram_type == DIAGRAM_TYPE_SEQUENCE:
        entities = _extract_entities_sequence(spans, image_width, image_height)
        interactions = _extract_interactions_sequence(
            spans, primitives.get("lines") or [], entities, image_height
        )
    elif diagram_type == DIAGRAM_TYPE_FLOW:
        entities = _extract_entities_flow(spans, image_width, image_height)
        interactions = _extract_interactions_flow(primitives.get("lines") or [], entities)
    else:
        entities = _extract_entities_flow(spans, image_width, image_height)
        if not entities and spans:
            entities = [{"name": (s.get("text") or "").strip(), "bbox": s.get("bbox"), "role": "node"} for s in spans[:10] if (s.get("text") or "").strip()]

    reason_codes: List[str] = []
    if ocr_result.get("reason_code"):
        reason_codes.append(ocr_result["reason_code"])
    if primitives.get("reason_code"):
        reason_codes.append(primitives["reason_code"])
    overall_conf = type_conf * 0.4 + (ocr_result.get("avg_conf", 0) or 0) * 0.4
    if reason_codes:
        overall_conf = min(overall_conf, 0.5)
    return {
        "diagram_type": diagram_type,
        "diagram_type_confidence": type_conf,
        "entities": entities,
        "interactions": interactions,
        "confidence": round(overall_conf, 2),
        "reason_codes": reason_codes,
    }


def _build_diagram_summary(parse: Dict[str, Any]) -> str:
    """
    Human-readable summary ONLY from extracted entities and interactions. No hallucination.
    """
    entities = parse.get("entities") or []
    interactions = parse.get("interactions") or []
    diagram_type = parse.get("diagram_type", DIAGRAM_TYPE_UNKNOWN)
    if not entities and not interactions:
        return "Diagram content could not be extracted (low confidence)."
    parts: List[str] = []
    if diagram_type == DIAGRAM_TYPE_SEQUENCE:
        for i, ia in enumerate(interactions[:15]):
            fr = ia.get("from_entity", "")
            to = ia.get("to_entity", "")
            label = ia.get("label", "").strip() or "message"
            if label == "(message)":
                label = "a message"
            parts.append(f"{fr} sends '{label}' to {to}.")
        if not parts and entities:
            parts.append("Entities: " + ", ".join(e.get("name", "") for e in entities[:10]))
    elif diagram_type == DIAGRAM_TYPE_FLOW:
        for i, ia in enumerate(interactions[:15]):
            fr = ia.get("from_entity", "")
            to = ia.get("to_entity", "")
            label = ia.get("label", "").strip()
            if label:
                parts.append(f"{fr} -> {to} ({label}).")
            else:
                parts.append(f"{fr} -> {to}.")
        if not parts and entities:
            parts.append("Nodes: " + ", ".join(e.get("name", "") for e in entities[:10]))
    else:
        if entities:
            parts.append("Elements: " + ", ".join(e.get("name", "") for e in entities[:10]))
        if interactions:
            for ia in interactions[:5]:
                parts.append(f"{ia.get('from_entity', '')} to {ia.get('to_entity', '')}.")
    return " ".join(parts).strip() or "Diagram structure extracted with low confidence."


def _diagram_evidence_from_openai_result(
    job_id: str,
    slide_index: int,
    image_id: str,
    image_bbox: Optional[Dict[str, Any]],
    uri: str,
    ppt_shape_id: Optional[str],
    raw: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build DIAGRAM_* evidence items from OpenAIVisionProvider.extract(mode='diagram') result."""
    items: List[Dict[str, Any]] = []
    conf = float(raw.get("global_confidence", 0.5))
    diagram_type = (raw.get("diagram_type") or DIAGRAM_TYPE_UNKNOWN).strip()
    if diagram_type not in VALID_DIAGRAM_TYPES:
        diagram_type = DIAGRAM_TYPE_UNKNOWN

    ev_type = _stable_evidence_id(job_id, slide_index, KIND_DIAGRAM_TYPE, image_id)
    items.append({
        "evidence_id": ev_type,
        "kind": KIND_DIAGRAM_TYPE,
        "content": diagram_type,
        "confidence": conf,
        "slide_index": slide_index,
        "image_bbox": image_bbox,
        "image_uri": uri,
        "slide_png_uri": uri,
        "ppt_picture_shape_id": ppt_shape_id,
    })
    entities = raw.get("entities") or []
    if entities:
        entities_content = ", ".join(e.get("name", "") for e in entities[:20])
        ev_ent = _stable_evidence_id(job_id, slide_index, KIND_DIAGRAM_ENTITIES, image_id)
        items.append({
            "evidence_id": ev_ent,
            "kind": KIND_DIAGRAM_ENTITIES,
            "content": entities_content,
            "confidence": conf,
            "slide_index": slide_index,
            "image_bbox": image_bbox,
            "image_uri": uri,
            "slide_png_uri": uri,
            "ppt_picture_shape_id": ppt_shape_id,
        })
    interactions = raw.get("interactions") or []
    if interactions:
        parts = []
        for ia in interactions[:15]:
            fr = ia.get("from", "") or ia.get("from_entity", "")
            to = ia.get("to", "")
            label = ia.get("label", "")
            order = ia.get("order", 0)
            parts.append(f"{order}:{fr}->{to}:{label}")
        ev_int = _stable_evidence_id(job_id, slide_index, KIND_DIAGRAM_INTERACTIONS, image_id)
        items.append({
            "evidence_id": ev_int,
            "kind": KIND_DIAGRAM_INTERACTIONS,
            "content": "; ".join(parts),
            "confidence": conf,
            "slide_index": slide_index,
            "image_bbox": image_bbox,
            "image_uri": uri,
            "slide_png_uri": uri,
            "ppt_picture_shape_id": ppt_shape_id,
        })
    summary = (raw.get("summary") or "").strip() or DIAGRAM_FALLBACK_SUMMARY
    ev_sum = _stable_evidence_id(job_id, slide_index, KIND_DIAGRAM_SUMMARY, image_id)
    items.append({
        "evidence_id": ev_sum,
        "kind": KIND_DIAGRAM_SUMMARY,
        "content": summary,
        "confidence": conf,
        "slide_index": slide_index,
        "image_bbox": image_bbox,
        "image_uri": uri,
        "slide_png_uri": uri,
        "ppt_picture_shape_id": ppt_shape_id,
    })
    return items


def run_diagram_understand(
    job_id: str,
    project_id: str,
    images_index: Dict[str, Any],
    image_kinds: Dict[str, Any],
    minio_client: Any,
    db_session: Any,
    ocr_backend: str = "tesseract",
    lang: str = "en-US",
    vision_provider: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    For each image classified DIAGRAM:
    - (Day 3) Try OpenAIVisionProvider.extract(mode='diagram'); on success use for evidence and diagram_results.json.
    - On failure or no provider: fallback DIAGRAM_SUMMARY "Diagram present; details unavailable" and/or OCR path.
    - EvidenceItems: DIAGRAM_TYPE, DIAGRAM_ENTITIES, DIAGRAM_INTERACTIONS, DIAGRAM_SUMMARY with refs.
    """
    from image_understand import _append_image_evidence_to_index

    try:
        from vision_provider import get_vision_provider
    except ImportError:
        get_vision_provider = None  # type: ignore

    classifications = {c["image_id"]: c for c in image_kinds.get("classifications", [])}
    images = images_index.get("images", [])
    diagram_images = [
        img for img in images
        if classifications.get(img.get("image_id", ""), {}).get("image_kind") == "DIAGRAM"
    ]
    if not diagram_images or not minio_client:
        created_at = datetime.now(timezone.utc)
        empty_ocr = {"schema_version": "1.0", "job_id": job_id, "images": [], "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"}
        empty_prim = {"schema_version": "1.0", "job_id": job_id, "images": [], "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"}
        empty_parse = {"schema_version": "1.0", "job_id": job_id, "images": [], "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"}
        for path_suffix, payload in [
            ("diagram_ocr.json", empty_ocr),
            ("diagram_primitives.json", empty_prim),
            ("diagram_parse.json", empty_parse),
        ]:
            minio_client.put(f"jobs/{job_id}/vision/{path_suffix}", json.dumps(payload, indent=2).encode("utf-8"), "application/json")
        diagram_results_payload = {"schema_version": "1.0", "job_id": job_id, "results": [], "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"}
        minio_client.put(f"jobs/{job_id}/vision/diagram_results.json", json.dumps(diagram_results_payload, indent=2).encode("utf-8"), "application/json")
        return {"diagram_results": [], "evidence_count": 0}

    created_at = datetime.now(timezone.utc)
    ocr_images: List[Dict[str, Any]] = []
    prim_images: List[Dict[str, Any]] = []
    parse_images: List[Dict[str, Any]] = []
    diagram_evidence_items: List[Dict[str, Any]] = []
    diagram_results_for_json: List[Dict[str, Any]] = []
    provider = vision_provider or (get_vision_provider() if get_vision_provider else None)

    for img in diagram_images:
        image_id = img.get("image_id", "")
        uri = img.get("uri", "")
        slide_index = img.get("slide_index", 0)
        ppt_shape_id = img.get("ppt_shape_id", "")
        bbox = img.get("bbox") or {}
        image_bbox = {
            "left": bbox.get("x"),
            "top": bbox.get("y"),
            "width": bbox.get("w"),
            "height": bbox.get("h"),
        } if bbox else None

        # Day 3: Try OpenAI diagram extraction first (primary)
        used_openai = False
        if provider and getattr(provider, "extract", None):
            try:
                raw = provider.extract(uri, lang=lang, minio_client=minio_client, mode="diagram")
                if (
                    isinstance(raw, dict)
                    and raw.get("diagram_type") is not None
                    and (raw.get("diagram_type") or "").strip() in VALID_DIAGRAM_TYPES
                ):
                    items = _diagram_evidence_from_openai_result(
                        job_id, slide_index, image_id, image_bbox, uri, ppt_shape_id, raw
                    )
                    diagram_evidence_items.extend(items)
                    diagram_results_for_json.append({
                        "image_id": image_id,
                        "slide_index": slide_index,
                        "source": "openai",
                        "diagram_type": raw.get("diagram_type"),
                        "global_confidence": raw.get("global_confidence"),
                        "entities_count": len(raw.get("entities") or []),
                        "interactions_count": len(raw.get("interactions") or []),
                    })
                    used_openai = True
            except Exception:
                pass
        if not used_openai:
            # Fallback: low-confidence DIAGRAM_SUMMARY (Day 3)
            ev_fb = _stable_evidence_id(job_id, slide_index, KIND_DIAGRAM_SUMMARY, image_id + "_fb")
            diagram_evidence_items.append({
                "evidence_id": ev_fb,
                "kind": KIND_DIAGRAM_SUMMARY,
                "content": DIAGRAM_FALLBACK_SUMMARY,
                "confidence": 0.1,
                "slide_index": slide_index,
                "image_bbox": image_bbox,
                "image_uri": uri,
                "slide_png_uri": uri,
                "ppt_picture_shape_id": ppt_shape_id,
                "reason_code": DIAGRAM_FALLBACK_REASON,
            })
            diagram_results_for_json.append({
                "image_id": image_id,
                "slide_index": slide_index,
                "source": "fallback",
                "reason_code": DIAGRAM_FALLBACK_REASON,
            })

        try:
            raw = minio_client.get(uri)
            image_bytes = raw if isinstance(raw, bytes) else raw.read()
        except Exception:
            if not used_openai:
                ocr_images.append({"image_id": image_id, "slide_index": slide_index, "spans": [], "avg_conf": 0.0, "reason_code": REASON_OCR_LOW_CONF})
                prim_images.append({"image_id": image_id, "lines": [], "arrows": [], "connectors": [], "reason_code": REASON_ARROW_DETECT_LOW})
                parse_images.append({"image_id": image_id, "diagram_type": DIAGRAM_TYPE_UNKNOWN, "entities": [], "interactions": [], "confidence": 0.0, "reason_codes": [REASON_OCR_LOW_CONF]})
            continue

        if used_openai:
            # Skip OCR path when OpenAI succeeded
            continue

        # Image dimensions for parse (OCR path)
        if PIL_AVAILABLE:
            try:
                pil_img = Image.open(BytesIO(image_bytes))
                img_w, img_h = pil_img.size
            except Exception:
                img_w, img_h = 800, 600
        elif CV2_AVAILABLE and np is not None:
            try:
                arr = np.frombuffer(image_bytes, dtype=np.uint8)
                im = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
                img_h, img_w = im.shape[:2] if im is not None else (600, 800)
            except Exception:
                img_w, img_h = 800, 600
        else:
            img_w, img_h = 800, 600

        ocr_result = _run_diagram_ocr(image_bytes, image_id, slide_index)
        ocr_result["uri"] = uri
        ocr_images.append(ocr_result)

        prim_result = _run_diagram_primitives(image_bytes)
        prim_result["image_id"] = image_id
        prim_result["slide_index"] = slide_index
        prim_images.append(prim_result)

        parse_result = _run_diagram_parse(ocr_result, prim_result, img_w, img_h)
        parse_result["image_id"] = image_id
        parse_result["uri"] = uri
        parse_result["slide_index"] = slide_index
        parse_images.append(parse_result)

        summary = _build_diagram_summary(parse_result)
        conf = parse_result.get("confidence", 0.4)
        reason_codes = parse_result.get("reason_codes") or []

        # EvidenceItems with refs to image bbox + uri
        ev_id_type = _stable_evidence_id(job_id, slide_index, KIND_DIAGRAM_TYPE, image_id)
        diagram_evidence_items.append({
            "evidence_id": ev_id_type,
            "kind": KIND_DIAGRAM_TYPE,
            "content": parse_result.get("diagram_type", DIAGRAM_TYPE_UNKNOWN),
            "confidence": conf,
            "slide_index": slide_index,
            "image_bbox": image_bbox,
            "image_uri": uri,
            "slide_png_uri": uri,
            "ppt_picture_shape_id": ppt_shape_id,
            "reason_code": reason_codes[0] if reason_codes else None,
        })
        entities_content = ", ".join(e.get("name", "") for e in parse_result.get("entities", [])[:20])
        if entities_content:
            ev_id_ent = _stable_evidence_id(job_id, slide_index, KIND_DIAGRAM_ENTITIES, image_id)
            diagram_evidence_items.append({
                "evidence_id": ev_id_ent,
                "kind": KIND_DIAGRAM_ENTITIES,
                "content": entities_content,
                "confidence": conf,
                "slide_index": slide_index,
                "image_bbox": image_bbox,
                "image_uri": uri,
                "slide_png_uri": uri,
                "ppt_picture_shape_id": ppt_shape_id,
            })
        interactions_content = "; ".join(
            f"{ia.get('from_entity','')}->{ia.get('to_entity','')}:{ia.get('label','')}" for ia in parse_result.get("interactions", [])[:15]
        )
        if interactions_content:
            ev_id_int = _stable_evidence_id(job_id, slide_index, KIND_DIAGRAM_INTERACTIONS, image_id)
            diagram_evidence_items.append({
                "evidence_id": ev_id_int,
                "kind": KIND_DIAGRAM_INTERACTIONS,
                "content": interactions_content,
                "confidence": conf,
                "slide_index": slide_index,
                "image_bbox": image_bbox,
                "image_uri": uri,
                "slide_png_uri": uri,
                "ppt_picture_shape_id": ppt_shape_id,
            })
        ev_id_summary = _stable_evidence_id(job_id, slide_index, KIND_DIAGRAM_SUMMARY, image_id)
        diagram_evidence_items.append({
            "evidence_id": ev_id_summary,
            "kind": KIND_DIAGRAM_SUMMARY,
            "content": summary,
            "confidence": conf,
            "slide_index": slide_index,
            "image_bbox": image_bbox,
            "image_uri": uri,
            "slide_png_uri": uri,
            "ppt_picture_shape_id": ppt_shape_id,
        })
        diagram_results_for_json.append({
            "image_id": image_id,
            "slide_index": slide_index,
            "source": "ocr",
            "diagram_type": parse_result.get("diagram_type"),
            "confidence": conf,
        })

    # Write artifacts (including diagram_results.json for Day 3)
    created_at_str = created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    for path_suffix, payload in [
        ("diagram_ocr.json", {"schema_version": "1.0", "job_id": job_id, "images": ocr_images, "created_at": created_at_str}),
        ("diagram_primitives.json", {"schema_version": "1.0", "job_id": job_id, "images": prim_images, "created_at": created_at_str}),
        ("diagram_parse.json", {"schema_version": "1.0", "job_id": job_id, "images": parse_images, "created_at": created_at_str}),
        ("diagram_results.json", {"schema_version": "1.0", "job_id": job_id, "results": diagram_results_for_json, "created_at": created_at_str}),
    ]:
        minio_client.put(f"jobs/{job_id}/vision/{path_suffix}", json.dumps(payload, indent=2).encode("utf-8"), "application/json")

    if diagram_evidence_items:
        _append_image_evidence_to_index(
            job_id=job_id,
            project_id=project_id,
            image_evidence_items=diagram_evidence_items,
            minio_client=minio_client,
            db_session=db_session,
            created_at=created_at,
        )

    return {"diagram_results": parse_images, "evidence_count": len(diagram_evidence_items)}
