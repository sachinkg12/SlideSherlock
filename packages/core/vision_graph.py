"""
Vision graph (G_vision): build from slide PNG using OCR text regions as node candidates.
Optional: detect lines (Hough) for edge candidates.
Output: graphs/vision/slide_i.json compatible with merge engine.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple

try:
    from ocr import run_ocr
except ImportError:
    run_ocr = None  # type: ignore

# Optional: OpenCV for line detection
try:
    import cv2
    import numpy as np

    CV2_AVAILABLE = True
except ImportError:
    cv2 = None  # type: ignore
    np = None  # type: ignore
    CV2_AVAILABLE = False


def _node_id_v(slide_index: int, det_id: str) -> str:
    """Stable vision node_id from slide_index + det_id."""
    return hashlib.sha256(f"v|{slide_index}|{det_id}".encode("utf-8")).hexdigest()


def _edge_id_v(slide_index: int, line_idx: int) -> str:
    """Stable vision edge_id from slide_index + line index."""
    return hashlib.sha256(f"ve|{slide_index}|{line_idx}".encode("utf-8")).hexdigest()


def _bbox_center(bbox: Dict[str, float]) -> Tuple[float, float]:
    left = bbox.get("left", 0) or 0
    top = bbox.get("top", 0) or 0
    w = bbox.get("width", 0) or 0
    h = bbox.get("height", 0) or 0
    return (left + w / 2.0, top + h / 2.0)


def _detect_lines_opencv(image: Any, slide_index: int) -> List[Dict[str, Any]]:
    """
    Optional: detect line segments via Hough transform. Returns list of edges
    with bbox-like endpoints (x1,y1,x2,y2) and no src/dst node resolution yet.
    """
    if not CV2_AVAILABLE or image is None:
        return []
    try:
        if hasattr(image, "size"):
            arr = np.array(image)
            if len(arr.shape) == 3:
                gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            else:
                gray = arr
        else:
            gray = image
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=50,
            minLineLength=30,
            maxLineGap=10,
        )
        if lines is None:
            return []
        out: List[Dict[str, Any]] = []
        for idx, line in enumerate(lines):
            x1, y1, x2, y2 = line[0]
            eid = _edge_id_v(slide_index, idx)
            out.append(
                {
                    "edge_id": eid,
                    "det_type": "line",
                    "bbox": {
                        "left": min(x1, x2),
                        "top": min(y1, y2),
                        "width": abs(x2 - x1),
                        "height": abs(y2 - y1),
                    },
                    "endpoints": {
                        "begin": {"x": float(x1), "y": float(y1)},
                        "end": {"x": float(x2), "y": float(y2)},
                    },
                    "confidence": 0.6,
                }
            )
        return out
    except Exception:
        return []


def build_vision_graph_slide(
    image: Any,
    slide_index: int,
    ocr_backend: str = "tesseract",
    detect_lines: bool = False,
) -> Dict[str, Any]:
    """
    Build G_vision for one slide from PNG (PIL Image).
    - Nodes: from OCR text regions (bbox + text as label), stable node_id_v.
    - Edges: empty by default; if detect_lines=True and OpenCV available, add line detections (no src/dst yet).
    Returns {slide_index, nodes, edges, text_spans} and text_spans for ocr/slide_i.json.
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    text_spans: List[Dict[str, Any]] = []

    if run_ocr is None:
        return {
            "slide_index": slide_index,
            "nodes": nodes,
            "edges": edges,
            "text_spans": text_spans,
        }

    # OCR -> text spans and node candidates
    spans = run_ocr(image, slide_index=slide_index, backend=ocr_backend)
    for s in spans:
        text_spans.append(
            {
                "ocr_id": s["ocr_id"],
                "bbox": s["bbox"],
                "text": s["text"],
                "conf": s["conf"],
            }
        )
        nid = _node_id_v(slide_index, s["ocr_id"])
        bbox = s["bbox"]
        center = _bbox_center(bbox)
        nodes.append(
            {
                "node_id": nid,
                "det_id": s["ocr_id"],
                "det_type": "text_region",
                "bbox": bbox,
                "center": {"x": center[0], "y": center[1]},
                "label_text": s["text"],
                "confidence": s["conf"],
            }
        )

    # Optional: Hough lines as edge candidates (no src/dst node resolution in vision layer)
    if detect_lines:
        line_edges = _detect_lines_opencv(image, slide_index)
        for e in line_edges:
            edges.append(
                {
                    "edge_id": e["edge_id"],
                    "det_type": e.get("det_type", "line"),
                    "bbox": e["bbox"],
                    "endpoints": e["endpoints"],
                    "label_text": None,
                    "confidence": e.get("confidence", 0.6),
                    "src_node_id": None,
                    "dst_node_id": None,
                }
            )

    return {
        "slide_index": slide_index,
        "nodes": nodes,
        "edges": edges,
        "text_spans": text_spans,
    }
