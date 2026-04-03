"""
Slide-level fallback caption (Prompt 7): last resort for image-only slides.
Trigger only when: speaker notes absent/short AND no high-confidence image evidence.
Runs VisionProvider.caption on full slide PNG; stores EvidenceItem kind=SLIDE_CAPTION.
Writes jobs/{job_id}/vision/slide_caption_results.json. Script generator may use SLIDE_CAPTION and MUST hedge when confidence low.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from vision_provider import get_vision_provider
except ImportError:
    get_vision_provider = None  # type: ignore

# Evidence kind for last-resort slide caption
KIND_SLIDE_CAPTION = "SLIDE_CAPTION"

# Same as script_context: notes below this = "absent/short"
MIN_NOTES_WORDS = 5
# Same as script_context: image evidence above this = "high confidence", skip fallback
IMAGE_CONFIDENCE_THRESHOLD = float(
    __import__("os").environ.get("VISION_SCRIPT_IMAGE_CONFIDENCE_THRESHOLD", "0.5")
)


def _word_count(text: str) -> int:
    return len((text or "").split())


def _stable_evidence_id(job_id: str, slide_index: int) -> str:
    payload = f"{job_id}|{slide_index}|{KIND_SLIDE_CAPTION}|slide"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _slide_needs_fallback(
    slide_index: int,
    notes: str,
    evidence_items: List[Dict[str, Any]],
) -> bool:
    """True if notes are short, no high-confidence image evidence, and no existing SLIDE_CAPTION."""
    if _word_count(notes or "") >= MIN_NOTES_WORDS:
        return False
    from script_context import IMAGE_EVIDENCE_KINDS
    for ev in evidence_items:
        if ev.get("slide_index") != slide_index:
            continue
        kind = (ev.get("kind") or "").strip()
        if kind == KIND_SLIDE_CAPTION:
            return False  # Already have fallback caption
        if kind not in IMAGE_EVIDENCE_KINDS:
            continue
        if float(ev.get("confidence", 0)) >= IMAGE_CONFIDENCE_THRESHOLD:
            return False
    return True


def run_slide_caption_fallback(
    job_id: str,
    project_id: str,
    slide_count: int,
    minio_client: Any,
    db_session: Any,
    slides_notes_and_text: Optional[List[Tuple[str, str]]] = None,
    evidence_index: Optional[Dict[str, Any]] = None,
    vision_provider: Optional[Any] = None,
    lang: str = "en-US",
) -> Dict[str, Any]:
    """
    For each slide: if notes absent/short and no high-confidence image evidence,
    run VisionProvider.caption on full slide PNG and append SLIDE_CAPTION evidence.
    Returns: {slides_captioned: [slide_index, ...], evidence_count: N}
    """
    from image_understand import _append_image_evidence_to_index

    if not minio_client or not get_vision_provider:
        return {"slides_captioned": [], "evidence_count": 0}

    vision_provider = vision_provider or get_vision_provider()
    evidence_items = list((evidence_index or {}).get("evidence_items", []))

    if evidence_index is None:
        try:
            raw = minio_client.get(f"jobs/{job_id}/evidence/index.json")
            evidence_index = __import__("json").loads(raw.decode("utf-8"))
            evidence_items = evidence_index.get("evidence_items", [])
        except Exception:
            evidence_index = {"evidence_items": []}
            evidence_items = []

    if slides_notes_and_text is None:
        slides_notes_and_text = []
        for i in range(slide_count):
            slide_num = f"{(i + 1):03d}"
            notes, slide_text = "", ""
            try:
                ppt_data = minio_client.get(f"jobs/{job_id}/ppt/slide_{slide_num}.json")
                ppt = __import__("json").loads(ppt_data.decode("utf-8"))
                notes = (ppt.get("notes") or "").strip()
                slide_text = (ppt.get("slide_text") or "").strip()
            except Exception:
                pass
            slides_notes_and_text.append((notes, slide_text))

    created_at = datetime.now(timezone.utc)
    slide_evidence_items: List[Dict[str, Any]] = []
    slides_captioned: List[int] = []

    for i in range(slide_count):
        slide_index = i + 1
        notes = slides_notes_and_text[i][0] if i < len(slides_notes_and_text) else ""
        if not _slide_needs_fallback(slide_index, notes, evidence_items):
            continue
        slide_uri = f"jobs/{job_id}/render/slides/slide_{slide_index:03d}.png"
        try:
            caption_res = vision_provider.caption(
                slide_uri, lang=lang, minio_client=minio_client
            )
        except Exception:
            caption_res = {
                "caption": "Image present; details unavailable",
                "confidence": 0.1,
                "reason_code": "VISION_UNAVAILABLE",
            }
        caption = (caption_res.get("caption") or "").strip() or "Image present; details unavailable"
        confidence = float(caption_res.get("confidence", 0.3))
        ev_id = _stable_evidence_id(job_id, slide_index)
        # Full slide bbox (normalized 0,0,1,1)
        image_bbox = {"left": 0, "top": 0, "width": 1, "height": 1}
        slide_evidence_items.append({
            "evidence_id": ev_id,
            "kind": KIND_SLIDE_CAPTION,
            "content": caption,
            "confidence": confidence,
            "slide_index": slide_index,
            "image_bbox": image_bbox,
            "image_uri": slide_uri,
            "slide_png_uri": slide_uri,
            "ppt_picture_shape_id": None,
            "reason_code": caption_res.get("reason_code"),
        })
        slides_captioned.append(slide_index)

    if slide_evidence_items:
        _append_image_evidence_to_index(
            job_id=job_id,
            project_id=project_id,
            image_evidence_items=slide_evidence_items,
            minio_client=minio_client,
            db_session=db_session,
            created_at=created_at,
        )

    # Artifact: slide_caption_results.json (Day 2) — always write when stage runs
    slide_caption_results = [
        {
            "slide_index": ev.get("slide_index"),
            "caption": ev.get("content", ""),
            "confidence": ev.get("confidence", 0),
            "reason_code": ev.get("reason_code"),
        }
        for ev in slide_evidence_items
    ]
    results_payload = {
        "schema_version": "1.0",
        "job_id": job_id,
        "slides": slide_caption_results,
        "slides_captioned": slides_captioned,
        "created_at": created_at.isoformat(),
    }
    minio_client.put(
        f"jobs/{job_id}/vision/slide_caption_results.json",
        json.dumps(results_payload, indent=2).encode("utf-8"),
        "application/json",
    )

    return {"slides_captioned": slides_captioned, "evidence_count": len(slide_evidence_items)}
