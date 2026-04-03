"""
PHOTO understanding pipeline: caption + objects + actions as EvidenceItems.
Runs after images extracted and classified. For PHOTO images only.
Outputs: jobs/{job_id}/vision/photo_results.json, appends IMAGE_CAPTION/OBJECTS/ACTIONS/TAGS to evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from vision_provider import (
    KIND_IMAGE_ACTIONS,
    KIND_IMAGE_CAPTION,
    KIND_IMAGE_OBJECTS,
    KIND_IMAGE_TAGS,
    get_vision_provider,
)

# Classifier output
KIND_PHOTO = "PHOTO"

# Threshold for NO-HALLUCINATION fallback (caption/objects below this => generic fallback text)
VISION_CONFIDENCE_THRESHOLD = float(os.environ.get("VISION_PHOTO_CONFIDENCE_THRESHOLD", "0.5"))
# Only run vision for PHOTO images with classifier confidence >= this (avoid low-confidence runs)
PHOTO_CLASSIFIER_MIN_CONFIDENCE = float(os.environ.get("VISION_PHOTO_CLASSIFIER_MIN_CONFIDENCE", "0.5"))

# Strict fallback: no invented content (Day 2)
STRICT_FALLBACK_CAPTION = "Image present; details unavailable"
STRICT_FALLBACK_REASON = "VISION_UNAVAILABLE"


def _stable_evidence_id(job_id: str, slide_index: int, kind: str, offset_key: str) -> str:
    payload = f"{job_id}|{slide_index}|{kind}|photo|{offset_key}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def run_photo_understand(
    job_id: str,
    project_id: str,
    images_index: Dict[str, Any],
    image_kinds: Dict[str, Any],
    minio_client: Any,
    db_session: Any,
    lang: str = "en-US",
    vision_provider: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    For each image classified PHOTO:
    1) Call VisionProvider.caption and extract
    2) Save jobs/{job_id}/vision/photo_results.json
    3) Convert to EvidenceItems and append to evidence index
    Returns: {photo_results: [...], evidence_count: N}
    """
    vision_provider = vision_provider or get_vision_provider()
    images = images_index.get("images", [])
    classifications = {c["image_id"]: c for c in image_kinds.get("classifications", [])}

    photo_images = [
        img
        for img in images
        if classifications.get(img.get("image_id", ""), {}).get("image_kind") == KIND_PHOTO
        and float(classifications.get(img.get("image_id", ""), {}).get("confidence", 0)) >= PHOTO_CLASSIFIER_MIN_CONFIDENCE
    ]
    if not photo_images or not minio_client:
        payload = {
            "schema_version": "1.0",
            "job_id": job_id,
            "results": [],
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        path = f"jobs/{job_id}/vision/photo_results.json"
        minio_client.put(path, json.dumps(payload, indent=2).encode("utf-8"), "application/json")
        return {"photo_results": [], "evidence_count": 0}

    created_at = datetime.utcnow()
    results: List[Dict[str, Any]] = []
    image_evidence_items: List[Dict[str, Any]] = []

    for img in photo_images:
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

        try:
            caption_res = vision_provider.caption(uri, lang=lang, minio_client=minio_client)
            extract_res = vision_provider.extract(uri, lang=lang, minio_client=minio_client, mode="photo")
        except Exception as e:
            reason = getattr(e, "reason_code", None) or STRICT_FALLBACK_REASON
            caption_res = {
                "caption": STRICT_FALLBACK_CAPTION,
                "confidence": 0.1,
                "reason_code": reason,
            }
            extract_res = {
                "objects": [],
                "actions": [],
                "scene_tags": [],
                "global_confidence": 0.1,
                "reason_code": reason,
            }

        caption = (caption_res.get("caption") or "").strip() or STRICT_FALLBACK_CAPTION
        caption_conf = float(caption_res.get("confidence", 0.1))
        if caption_conf < VISION_CONFIDENCE_THRESHOLD:
            caption = STRICT_FALLBACK_CAPTION
            caption_conf = 0.1
            caption_res["reason_code"] = "LOW_CONFIDENCE"

        objects = extract_res.get("objects") or []
        actions = extract_res.get("actions") or []
        tags = extract_res.get("scene_tags") or []
        global_conf = float(extract_res.get("global_confidence", 0.1))

        results.append({
            "image_id": image_id,
            "uri": uri,
            "slide_index": slide_index,
            "caption": caption,
            "caption_confidence": caption_conf,
            "objects": objects,
            "actions": actions,
            "scene_tags": tags,
            "global_confidence": global_conf,
        })

        # Convert to EvidenceItems
        ev_id_caption = _stable_evidence_id(job_id, slide_index, KIND_IMAGE_CAPTION, image_id)
        image_evidence_items.append({
            "evidence_id": ev_id_caption,
            "kind": KIND_IMAGE_CAPTION,
            "content": caption,
            "confidence": caption_conf,
            "slide_index": slide_index,
            "image_bbox": image_bbox,
            "image_uri": uri,
            "slide_png_uri": uri,
            "ppt_picture_shape_id": ppt_shape_id,
        })

        objects_content = "; ".join(f"{o.get('label', '')}({o.get('conf', 0):.2f})" for o in objects[:10])
        if objects_content:
            ev_id_objects = _stable_evidence_id(job_id, slide_index, KIND_IMAGE_OBJECTS, image_id)
            image_evidence_items.append({
                "evidence_id": ev_id_objects,
                "kind": KIND_IMAGE_OBJECTS,
                "content": objects_content,
                "confidence": global_conf,
                "slide_index": slide_index,
                "image_bbox": image_bbox,
                "image_uri": uri,
                "slide_png_uri": uri,
                "ppt_picture_shape_id": ppt_shape_id,
            })

        actions_content = "; ".join(f"{a.get('verb_phrase', '')}({a.get('conf', 0):.2f})" for a in actions[:10])
        if actions_content:
            ev_id_actions = _stable_evidence_id(job_id, slide_index, KIND_IMAGE_ACTIONS, image_id)
            image_evidence_items.append({
                "evidence_id": ev_id_actions,
                "kind": KIND_IMAGE_ACTIONS,
                "content": actions_content,
                "confidence": global_conf,
                "slide_index": slide_index,
                "image_bbox": image_bbox,
                "image_uri": uri,
                "slide_png_uri": uri,
                "ppt_picture_shape_id": ppt_shape_id,
            })

        tags_content = "; ".join(f"{t.get('tag', '')}({t.get('conf', 0):.2f})" for t in tags[:10])
        if tags_content:
            ev_id_tags = _stable_evidence_id(job_id, slide_index, KIND_IMAGE_TAGS, image_id)
            image_evidence_items.append({
                "evidence_id": ev_id_tags,
                "kind": KIND_IMAGE_TAGS,
                "content": tags_content,
                "confidence": global_conf,
                "slide_index": slide_index,
                "image_bbox": image_bbox,
                "image_uri": uri,
                "slide_png_uri": uri,
                "ppt_picture_shape_id": ppt_shape_id,
            })

        if not objects_content and not actions_content and not tags_content:
            ev_id_objects = _stable_evidence_id(job_id, slide_index, KIND_IMAGE_OBJECTS, image_id)
            image_evidence_items.append({
                "evidence_id": ev_id_objects,
                "kind": KIND_IMAGE_OBJECTS,
                "content": "(no objects detected)",
                "confidence": 0.1,
                "slide_index": slide_index,
                "image_bbox": image_bbox,
                "image_uri": uri,
                "slide_png_uri": uri,
                "ppt_picture_shape_id": ppt_shape_id,
            })

    payload = {
        "schema_version": "1.0",
        "job_id": job_id,
        "results": results,
        "created_at": created_at.isoformat() + "Z",
    }
    path = f"jobs/{job_id}/vision/photo_results.json"
    minio_client.put(path, json.dumps(payload, indent=2).encode("utf-8"), "application/json")

    if image_evidence_items:
        from image_understand import _append_image_evidence_to_index

        _append_image_evidence_to_index(
            job_id=job_id,
            project_id=project_id,
            image_evidence_items=image_evidence_items,
            minio_client=minio_client,
            db_session=db_session,
            created_at=created_at,
        )

    return {"photo_results": results, "evidence_count": len(image_evidence_items)}
