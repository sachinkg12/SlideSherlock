"""
OCR module: extract text spans with bbox and confidence from slide PNG.
Produces ocr/text_spans format (ocr_id, bbox, text, conf) for vision pipeline.
Supports Tesseract (pytesseract) or EasyOCR behind a simple interface.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

# Optional: pytesseract
try:
    import pytesseract
    from pytesseract import Output
    PYTESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore
    Output = None  # type: ignore
    PYTESSERACT_AVAILABLE = False

# Optional: EasyOCR
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    easyocr = None  # type: ignore
    EASYOCR_AVAILABLE = False


def _ocr_id(slide_index: int, index: int, bbox: Dict[str, float], text: str) -> str:
    """Stable ocr_id for a text span."""
    key = f"{slide_index}|{index}|{bbox.get('left',0)}|{bbox.get('top',0)}|{text}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def run_ocr_tesseract(
    image: Any,
    slide_index: int = 0,
) -> List[Dict[str, Any]]:
    """
    Run Tesseract OCR on a PIL Image. Returns list of text spans.
    Each span: {ocr_id, bbox: {left, top, width, height}, text, conf}.
    Bbox in pixels.
    """
    if not PYTESSERACT_AVAILABLE:
        return []
    try:
        data = pytesseract.image_to_data(image, output_type=Output.DICT)
        spans: List[Dict[str, Any]] = []
        n = len(data["text"])
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0
            if conf < 0:
                conf = 0
            left = int(data["left"][i])
            top = int(data["top"][i])
            width = int(data["width"][i])
            height = int(data["height"][i])
            bbox = {"left": left, "top": top, "width": width, "height": height}
            ocr_id = _ocr_id(slide_index, i, bbox, text)
            spans.append({
                "ocr_id": ocr_id,
                "bbox": bbox,
                "text": text,
                "conf": conf / 100.0,  # 0-100 -> 0-1
            })
        return spans
    except Exception:
        return []


def run_ocr_easyocr(
    image: Any,
    slide_index: int = 0,
    reader: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Run EasyOCR on image. Expects PIL Image or numpy array.
    Returns same format as run_ocr_tesseract.
    """
    if not EASYOCR_AVAILABLE:
        return []
    try:
        import numpy as np
        if hasattr(image, "mode") and image.mode != "RGB":
            image = image.convert("RGB")
        if hasattr(image, "size"):
            arr = np.array(image)
        else:
            arr = image
        if reader is None:
            reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        results = reader.readtext(arr)
        spans: List[Dict[str, Any]] = []
        for idx, (box_pts, text, conf) in enumerate(results):
            text = (text or "").strip()
            if not text:
                continue
            # box_pts: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            xs = [p[0] for p in box_pts]
            ys = [p[1] for p in box_pts]
            left = min(xs)
            top = min(ys)
            width = max(xs) - left
            height = max(ys) - top
            bbox = {"left": left, "top": top, "width": width, "height": height}
            ocr_id = _ocr_id(slide_index, idx, bbox, text)
            spans.append({
                "ocr_id": ocr_id,
                "bbox": bbox,
                "text": text,
                "conf": float(conf),
            })
        return spans
    except Exception:
        return []


def run_ocr(
    image: Any,
    slide_index: int = 0,
    backend: str = "tesseract",
) -> List[Dict[str, Any]]:
    """
    Run OCR on image (PIL Image). Returns list of {ocr_id, bbox, text, conf}.
    backend: "tesseract" (default) or "easyocr".
    """
    if backend == "easyocr":
        return run_ocr_easyocr(image, slide_index)
    return run_ocr_tesseract(image, slide_index)
