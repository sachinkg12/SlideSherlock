"""
Image type classifier: PHOTO vs DIAGRAM vs UNKNOWN.
Deterministic heuristics only; never infers content.
Uses: text density (OCR), edge/line density (Canny/Hough), color variance.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image
    import numpy as np
    PIL_AVAILABLE = True
except ImportError:
    Image = None  # type: ignore
    np = None  # type: ignore
    PIL_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None  # type: ignore
    CV2_AVAILABLE = False

try:
    from ocr import run_ocr
except ImportError:
    run_ocr = None  # type: ignore

KIND_PHOTO = "PHOTO"
KIND_DIAGRAM = "DIAGRAM"
KIND_UNKNOWN = "UNKNOWN"


def _config_min_confidence_photo() -> float:
    # vision.classifier.min_confidence_photo -> VISION_CLASSIFIER_MIN_CONFIDENCE_PHOTO
    v = os.environ.get("VISION_CLASSIFIER_MIN_CONFIDENCE_PHOTO", "0.5")
    try:
        return max(0.0, min(1.0, float(v)))
    except ValueError:
        return 0.5


def _config_min_confidence_diagram() -> float:
    # vision.classifier.min_confidence_diagram -> VISION_CLASSIFIER_MIN_CONFIDENCE_DIAGRAM
    v = os.environ.get("VISION_CLASSIFIER_MIN_CONFIDENCE_DIAGRAM", "0.5")
    try:
        return max(0.0, min(1.0, float(v)))
    except ValueError:
        return 0.5


def _image_to_array(image: Any) -> Any:
    """Convert PIL Image or bytes to numpy array (RGB)."""
    if not PIL_AVAILABLE or np is None:
        return None
    if hasattr(image, "size"):
        return np.array(image)
    if isinstance(image, bytes):
        from io import BytesIO
        try:
            return np.array(Image.open(BytesIO(image)).convert("RGB"))
        except Exception:
            return None
    return None


def _text_density(image: Any) -> Tuple[float, str]:
    """OCR char count / pixel count. Diagrams typically higher. Returns (density, reason)."""
    if not run_ocr or not PIL_AVAILABLE:
        return 0.0, "ocr_unavailable"
    try:
        if isinstance(image, bytes):
            from io import BytesIO
            img = Image.open(BytesIO(image)).convert("RGB")
        else:
            img = image
        spans = run_ocr(img, slide_index=0, backend="tesseract")
        total_chars = sum(len(s.get("text", "")) for s in spans)
        w, h = img.size
        pixels = w * h
        density = total_chars / pixels if pixels else 0.0
        return min(1.0, density * 1e5), f"text_density={round(density * 1e5, 2)}e-5"
    except Exception:
        return 0.0, "text_density_error"


def _line_density(image: Any) -> Tuple[float, int, str]:
    """Canny edge + Hough line count / pixel. Diagrams typically higher. Returns (density, line_count, reason)."""
    if not CV2_AVAILABLE or np is None:
        return 0.0, 0, "opencv_unavailable"
    arr = _image_to_array(image)
    if arr is None or arr.size == 0:
        return 0.0, 0, "image_load_failed"
    try:
        if len(arr.shape) == 3:
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        else:
            gray = arr
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(
            edges, rho=1, theta=np.pi / 180, threshold=50,
            minLineLength=30, maxLineGap=10,
        )
        line_count = len(lines) if lines is not None else 0
        pixels = gray.size
        density = line_count / pixels if pixels else 0.0
        return min(1.0, density * 1e6), line_count, f"line_density={round(density * 1e6, 2)}e-6,lines={line_count}"
    except Exception:
        return 0.0, 0, "line_density_error"


def _color_variance(image: Any) -> Tuple[float, str]:
    """Std of pixel values. Photos typically higher (natural variation). Returns (variance_norm, reason)."""
    if not np or not PIL_AVAILABLE:
        return 0.0, "numpy_unavailable"
    arr = _image_to_array(image)
    if arr is None or arr.size == 0:
        return 0.0, "image_load_failed"
    try:
        std = float(np.std(arr))
        norm = min(1.0, std / 80.0)
        return norm, f"color_variance={round(std, 2)}"
    except Exception:
        return 0.0, "color_variance_error"


def _structured_line_ratio(image: Any) -> Tuple[float, str]:
    """Fraction of Hough lines that are near horizontal or vertical. Diagrams often have more."""
    if not CV2_AVAILABLE or np is None:
        return 0.0, "opencv_unavailable"
    arr = _image_to_array(image)
    if arr is None or arr.size == 0:
        return 0.0, "image_load_failed"
    try:
        if len(arr.shape) == 3:
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        else:
            gray = arr
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(
            edges, rho=1, theta=np.pi / 180, threshold=50,
            minLineLength=30, maxLineGap=10,
        )
        if lines is None or len(lines) == 0:
            return 0.0, "structured_lines=0"
        structured = 0
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            if dx < 2 or dy < 2:
                structured += 1
            elif dx > 0:
                slope = dy / dx
                if slope < 0.2 or slope > 5.0:
                    structured += 1
        ratio = structured / len(lines)
        return ratio, f"structured_line_ratio={round(ratio, 2)}"
    except Exception:
        return 0.0, "structured_line_error"


def classify_image(image: Any) -> Dict[str, Any]:
    """
    Classify image as PHOTO, DIAGRAM, or UNKNOWN.
    Deterministic heuristics only; never infers content.
    Returns: {image_kind, confidence, reasons}.
    """
    reasons: List[str] = []
    text_dens, r1 = _text_density(image)
    reasons.append(r1)
    line_dens, line_count, r2 = _line_density(image)
    reasons.append(r2)
    color_var, r3 = _color_variance(image)
    reasons.append(r3)
    struct_ratio, r4 = _structured_line_ratio(image)
    reasons.append(r4)

    min_photo = _config_min_confidence_photo()
    min_diagram = _config_min_confidence_diagram()

    diagram_score = (text_dens * 0.3 + line_dens * 0.4 + struct_ratio * 0.3)
    photo_score = (color_var * 0.5 + (1.0 - line_dens) * 0.3 + (1.0 - text_dens) * 0.2)

    if diagram_score >= min_diagram and diagram_score > photo_score:
        kind = KIND_DIAGRAM
        confidence = min(1.0, diagram_score)
    elif photo_score >= min_photo and photo_score > diagram_score:
        kind = KIND_PHOTO
        confidence = min(1.0, photo_score)
    else:
        kind = KIND_UNKNOWN
        confidence = max(0.2, min(diagram_score, photo_score))

    return {
        "image_kind": kind,
        "confidence": round(confidence, 4),
        "reasons": reasons,
        "signals": {
            "text_density": round(text_dens, 4),
            "line_density": round(line_dens, 4),
            "line_count": line_count,
            "color_variance": round(color_var, 4),
            "structured_line_ratio": round(struct_ratio, 4),
        },
    }


def run_classify_images(
    job_id: str,
    images_index: Dict[str, Any],
    minio_client: Any,
    force_kind_by_slide: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Classify each image in images_index. Fetch from MinIO, classify, write artifact.
    force_kind_by_slide: {"3": "DIAGRAM", "5": "PHOTO"} overrides classifier for that slide.
    Output: jobs/{job_id}/vision/image_kinds.json
    Returns: {classifications: [{image_id, image_kind, confidence, reasons, ...}], ...}
    """
    images = images_index.get("images", [])
    force_kind_by_slide = force_kind_by_slide or {}
    if not images or not minio_client:
        payload = {
            "schema_version": "1.0",
            "job_id": job_id,
            "classifications": [],
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        path = f"jobs/{job_id}/vision/image_kinds.json"
        minio_client.put(path, json.dumps(payload, indent=2).encode("utf-8"), "application/json")
        return payload

    classifications: List[Dict[str, Any]] = []
    for img in images:
        image_id = img.get("image_id", "")
        uri = img.get("uri", "")
        try:
            data = minio_client.get(uri)
            result = classify_image(data)
            slide_index = img.get("slide_index")
            kind = result["image_kind"]
            reasons = list(result["reasons"])
            # User override: force_kind_by_slide
            forced = force_kind_by_slide.get(str(slide_index)) or force_kind_by_slide.get(str(int(slide_index)))
            if forced and forced.upper() in (KIND_PHOTO, KIND_DIAGRAM, KIND_UNKNOWN):
                kind = forced.upper()
                reasons = reasons + ["force_kind_by_slide"]
            classifications.append({
                "image_id": image_id,
                "ppt_shape_id": img.get("ppt_shape_id"),
                "slide_index": slide_index,
                "uri": uri,
                "image_kind": kind,
                "confidence": result["confidence"],
                "reasons": reasons,
                "signals": result.get("signals", {}),
            })
        except Exception as e:
            classifications.append({
                "image_id": image_id,
                "ppt_shape_id": img.get("ppt_shape_id"),
                "slide_index": img.get("slide_index"),
                "uri": uri,
                "image_kind": KIND_UNKNOWN,
                "confidence": 0.0,
                "reasons": [f"classify_error:{str(e)[:100]}"],
            })

    payload = {
        "schema_version": "1.0",
        "job_id": job_id,
        "classifications": classifications,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    path = f"jobs/{job_id}/vision/image_kinds.json"
    minio_client.put(path, json.dumps(payload, indent=2).encode("utf-8"), "application/json")
    return payload
