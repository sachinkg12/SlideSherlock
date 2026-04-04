"""
Image understanding stage (NO-HALLUCINATION policy).
Extracts facts from images via vision extractor; stores evidence with provenance.
Outputs: jobs/{job_id}/vision/*, appends to evidence/index.json and DB.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from vision_provider import (
    ImageExtractionResult,
    get_vision_extractor,
)

# Re-export kinds for convenience
KIND_IMAGE_CAPTION = "IMAGE_CAPTION"
KIND_IMAGE_OBJECTS = "IMAGE_OBJECTS"
KIND_IMAGE_ACTIONS = "IMAGE_ACTIONS"
KIND_IMAGE_TAGS = "IMAGE_TAGS"
KIND_DIAGRAM_ENTITIES = "DIAGRAM_ENTITIES"
KIND_DIAGRAM_INTERACTIONS = "DIAGRAM_INTERACTIONS"
KIND_DIAGRAM_SUMMARY = "DIAGRAM_SUMMARY"
KIND_SLIDE_CAPTION = "SLIDE_CAPTION"

IMAGE_EVIDENCE_KINDS = frozenset(
    {
        KIND_IMAGE_CAPTION,
        KIND_IMAGE_OBJECTS,
        KIND_IMAGE_ACTIONS,
        KIND_IMAGE_TAGS,
        KIND_DIAGRAM_ENTITIES,
        KIND_DIAGRAM_INTERACTIONS,
        KIND_DIAGRAM_SUMMARY,
        KIND_SLIDE_CAPTION,
    }
)


def _stable_evidence_id(job_id: str, slide_index: int, kind: str, offset_key: str) -> str:
    payload = f"{job_id}|{slide_index}|{kind}|img|{offset_key}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _flatten_shapes(slide_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return flat list of shapes including picture shapes from groups."""
    shapes: List[Dict[str, Any]] = []

    def add(s: Dict) -> None:
        if s.get("type") == "GROUP" or "children" in s:
            for c in s.get("children", []):
                add(c)
        else:
            shapes.append(s)

    for s in slide_payload.get("shapes", []):
        add(s)
    for g in slide_payload.get("groups", []):
        for c in g.get("children", []):
            add(c)
    return shapes


def _is_picture_shape(shape: Dict[str, Any]) -> bool:
    t = (shape.get("type") or "").upper()
    return "PICTURE" in t or "IMAGE" in t or "PHOTO" in t


def run_image_understand(
    job_id: str,
    project_id: str,
    slide_count: int,
    slides_data: List[Dict[str, Any]],
    slides_png: List[Any],  # PIL Images
    minio_client: Any,
    db_session: Any,
    vision_graphs_by_slide: Optional[Dict[int, Dict[str, Any]]] = None,
    vision_extractor: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Run image understanding stage. For each slide:
    - Detect picture shapes or treat full slide as image
    - Extract via vision extractor (caption, objects, diagram entities)
    - Write jobs/{job_id}/vision/slide_XXX.json
    - Append image evidence to evidence/index.json and DB

    Returns: {vision_artifacts: [...], image_evidence_count: N}
    """
    from evidence_index import _emu_to_float

    vision_extractor = vision_extractor or get_vision_extractor()
    vision_graphs_by_slide = vision_graphs_by_slide or {}
    created_at = datetime.utcnow()

    vision_artifacts: List[Dict[str, Any]] = []
    image_evidence_items: List[Dict[str, Any]] = []
    slide_png_uri_base = f"jobs/{job_id}/render/slides/"

    for slide_index in range(1, slide_count + 1):
        slide_num = f"{slide_index:03d}"
        slide_png_uri = f"{slide_png_uri_base}slide_{slide_num}.png"

        slide_payload = next(
            (s for s in slides_data if s.get("slide_index") == slide_index),
            {},
        )
        slide_img = slides_png[slide_index - 1] if slide_index <= len(slides_png) else None
        if slide_img is None:
            continue

        from io import BytesIO

        buf = BytesIO()
        slide_img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        extractions: List[ImageExtractionResult] = []
        vision_graph = vision_graphs_by_slide.get(slide_index)

        shapes = _flatten_shapes(slide_payload)
        picture_shapes = [s for s in shapes if _is_picture_shape(s)]

        if picture_shapes:
            for pic in picture_shapes:
                bbox = pic.get("bbox") or {}
                ppt_shape_id = pic.get("ppt_shape_id")
                results = vision_extractor.extract_photo(
                    image_bytes=image_bytes,
                    slide_index=slide_index,
                    image_bbox={
                        "left": _emu_to_float(bbox.get("left")),
                        "top": _emu_to_float(bbox.get("top")),
                        "width": _emu_to_float(bbox.get("width")),
                        "height": _emu_to_float(bbox.get("height")),
                    }
                    if bbox
                    else None,
                    slide_png_uri=slide_png_uri,
                    ppt_picture_shape_id=ppt_shape_id,
                )
                extractions.extend(results)
        else:
            diagram_results = vision_extractor.extract_diagram(
                image_bytes=image_bytes,
                slide_index=slide_index,
                vision_graph=vision_graph,
                slide_png_uri=slide_png_uri,
            )
            extractions.extend(diagram_results)

        if not extractions:
            extractions.append(
                ImageExtractionResult(
                    slide_index=slide_index,
                    content="This slide contains an image.",
                    kind=KIND_IMAGE_CAPTION,
                    confidence=0.3,
                    reason_code="NO_EXTRACTION",
                    slide_png_uri=slide_png_uri,
                )
            )

        vision_slide_payload = {
            "slide_index": slide_index,
            "slide_png_uri": slide_png_uri,
            "extractions": [
                {
                    "kind": e.kind,
                    "content": e.content,
                    "confidence": e.confidence,
                    "reason_code": e.reason_code,
                    "image_bbox": e.image_bbox,
                    "ppt_picture_shape_id": e.ppt_picture_shape_id,
                }
                for e in extractions
            ],
            "created_at": created_at.isoformat() + "Z",
        }

        vision_path = f"jobs/{job_id}/vision/slide_{slide_num}.json"
        minio_client.put(
            vision_path,
            json.dumps(vision_slide_payload, indent=2).encode("utf-8"),
            "application/json",
        )
        vision_artifacts.append({"path": vision_path, "slide_index": slide_index})

        for ix, e in enumerate(extractions):
            ev_id = _stable_evidence_id(job_id, slide_index, e.kind, str(ix))
            image_evidence_items.append(
                {
                    "evidence_id": ev_id,
                    "kind": e.kind,
                    "content": e.content,
                    "confidence": e.confidence,
                    "reason_code": e.reason_code,
                    "slide_index": slide_index,
                    "image_bbox": e.image_bbox,
                    "image_uri": e.image_uri,
                    "ppt_picture_shape_id": e.ppt_picture_shape_id,
                    "slide_png_uri": e.slide_png_uri,
                }
            )

    if image_evidence_items:
        _append_image_evidence_to_index(
            job_id=job_id,
            project_id=project_id,
            image_evidence_items=image_evidence_items,
            minio_client=minio_client,
            db_session=db_session,
            created_at=created_at,
        )

    return {
        "vision_artifacts": vision_artifacts,
        "image_evidence_count": len(image_evidence_items),
    }


def _append_image_evidence_to_index(
    job_id: str,
    project_id: str,
    image_evidence_items: List[Dict[str, Any]],
    minio_client: Any,
    db_session: Any,
    created_at: datetime,
) -> None:
    """Read evidence index, append image evidence, write back and insert DB rows."""
    from apps.api.models import (
        Artifact,
        EvidenceItem,
        Slide,
        Source,
        SourceRef,
    )

    storage_path = f"jobs/{job_id}/evidence/index.json"
    try:
        raw = minio_client.get(storage_path)
        index_payload = json.loads(raw.decode("utf-8"))
    except Exception:
        index_payload = {
            "schema_version": "1.0",
            "job_id": job_id,
            "sources": [],
            "evidence_items": [],
            "entity_links": [],
            "claim_links": [],
            "artifacts": [],
        }

    sources_out = list(index_payload.get("sources", []))
    evidence_items_out = list(index_payload.get("evidence_items", []))

    slide_by_index: Dict[int, str] = {}
    for row in db_session.query(Slide).filter(Slide.job_id == job_id).all():
        slide_by_index[row.slide_index] = row.slide_id

    for ev in image_evidence_items:
        ev_id = ev["evidence_id"]
        kind = ev["kind"]
        content = ev["content"]
        confidence = ev.get("confidence", 0.5)
        slide_index = ev.get("slide_index", 1)
        image_bbox = ev.get("image_bbox")
        ppt_shape_id = ev.get("ppt_picture_shape_id")
        slide_png_uri = ev.get("slide_png_uri")

        source_id = str(uuid.uuid4())
        sources_out.append(
            {
                "source_id": source_id,
                "type": "IMAGE",
                "slide_index": slide_index,
                "artifact_url": slide_png_uri,
                "metadata": {
                    "image_bbox": image_bbox,
                    "ppt_picture_shape_id": ppt_shape_id,
                },
            }
        )

        image_uri = ev.get("image_uri") or slide_png_uri
        ref_item = {
            "ref_type": "IMAGE",
            "slide_index": slide_index,
            "url": slide_png_uri,
            "image_uri": image_uri,
        }
        if image_bbox:
            ref_item["bbox_x"] = image_bbox.get("left")
            ref_item["bbox_y"] = image_bbox.get("top")
            ref_item["bbox_w"] = image_bbox.get("width")
            ref_item["bbox_h"] = image_bbox.get("height")
        if ppt_shape_id:
            ref_item["ppt_shape_id"] = ppt_shape_id

        evidence_items_out.append(
            {
                "evidence_id": ev_id,
                "source_id": source_id,
                "kind": kind,
                "content": content,
                "content_hash": _content_hash(content),
                "confidence": confidence,
                "slide_index": slide_index,
                "reason_code": ev.get("reason_code"),
                "refs": [ref_item],
            }
        )

        slide_id = slide_by_index.get(slide_index)
        source_row = Source(
            source_id=source_id,
            job_id=job_id,
            type="IMAGE",
            artifact_id=None,
            slide_id=slide_id,
            created_at=created_at,
        )
        db_session.add(source_row)
        db_session.flush()

        ev_row = EvidenceItem(
            evidence_id=ev_id,
            job_id=job_id,
            slide_id=slide_id,
            source_id=source_id,
            kind=kind,
            content=content,
            content_hash=_content_hash(content),
            confidence=confidence,
            language=None,
            created_at=created_at,
        )
        db_session.add(ev_row)

        ref_url = ev.get("image_uri") or slide_png_uri
        ref_row = SourceRef(
            ref_id=str(uuid.uuid4()),
            evidence_id=ev_id,
            ref_type="IMAGE",
            slide_index=slide_index,
            ppt_shape_id=ppt_shape_id,
            bbox_x=image_bbox.get("left") if image_bbox else None,
            bbox_y=image_bbox.get("top") if image_bbox else None,
            bbox_w=image_bbox.get("width") if image_bbox else None,
            bbox_h=image_bbox.get("height") if image_bbox else None,
            url=ref_url,
        )
        db_session.add(ref_row)

    index_payload["sources"] = sources_out
    index_payload["evidence_items"] = evidence_items_out
    index_payload["created_at"] = created_at.isoformat() + "Z"

    index_json = json.dumps(index_payload, indent=2)
    index_bytes = index_json.encode("utf-8")
    minio_client.put(storage_path, index_bytes, "application/json")

    index_sha256 = hashlib.sha256(index_bytes).hexdigest()
    artifact_row = Artifact(
        artifact_id=str(uuid.uuid4()),
        project_id=project_id,
        job_id=job_id,
        artifact_type="evidence_index",
        storage_path=storage_path,
        sha256=index_sha256,
        size_bytes=str(len(index_bytes)),
        metadata_json=json.dumps(
            {
                "type": "evidence_index",
                "image_evidence_appended": len(image_evidence_items),
            }
        ),
        created_at=created_at,
    )
    db_session.add(artifact_row)
    db_session.commit()


def write_vision_summary(job_id: str, minio_client: Any) -> Dict[str, Any]:
    """
    Write jobs/{job_id}/debug/vision_summary.json with counts per kind and failures histogram.
    Call after photo_understand and slide_caption_fallback (and diagram if any) so evidence index is up to date.
    """
    from datetime import datetime

    storage_path = f"jobs/{job_id}/evidence/index.json"
    try:
        raw = minio_client.get(storage_path)
        index_payload = json.loads(raw.decode("utf-8"))
    except Exception:
        index_payload = {"evidence_items": []}

    evidence_items = list(index_payload.get("evidence_items", []))
    counts_by_kind: Dict[str, int] = {}
    failures: Dict[str, int] = {}

    for ev in evidence_items:
        kind = (ev.get("kind") or "").strip()
        if kind not in IMAGE_EVIDENCE_KINDS and kind != "IMAGE_ASSET":
            continue
        counts_by_kind[kind] = counts_by_kind.get(kind, 0) + 1
        reason = ev.get("reason_code")
        if reason:
            failures[reason] = failures.get(reason, 0) + 1
        elif float(ev.get("confidence", 1)) < 0.5:
            failures["LOW_CONFIDENCE"] = failures.get("LOW_CONFIDENCE", 0) + 1

    total_image_evidence = sum(counts_by_kind.values())
    total_failures = sum(failures.values())
    # Day 3: top failure reasons for debug bundle
    top_failure_reasons = sorted(
        (list(failures.items())),
        key=lambda x: -x[1],
    )[:10]

    summary = {
        "schema_version": "1.0",
        "job_id": job_id,
        "counts_by_kind": counts_by_kind,
        "failures": failures,
        "top_failure_reasons": top_failure_reasons,
        "total_image_evidence_items": total_image_evidence,
        "total_failures_or_low_confidence": total_failures,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    debug_path = f"jobs/{job_id}/debug/vision_summary.json"
    minio_client.put(
        debug_path,
        json.dumps(summary, indent=2).encode("utf-8"),
        "application/json",
    )
    return summary


def write_slide_vision_debug_bundle(
    job_id: str,
    slide_count: int,
    evidence_index: Dict[str, Any],
    script: Dict[str, Any],
    verify_report: List[Dict[str, Any]],
    minio_client: Any,
    images_index: Optional[Dict[str, Any]] = None,
    image_kinds: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Day 3: For each slide write jobs/{job_id}/debug/slide_{i:03}_vision_debug.json with:
    embedded images (list + kinds + confidences), evidence_ids created for IMAGE_* and DIAGRAM_*,
    evidence_ids used by script segments, narration excerpt, verifier verdict summary.
    """
    from datetime import datetime

    evidence_items = list(evidence_index.get("evidence_items", []))
    segments = list(script.get("segments", []))
    report_by_claim = {r.get("claim_id"): r for r in (verify_report or [])}

    classifications_by_image: Dict[str, Dict[str, Any]] = {}
    if image_kinds:
        for c in image_kinds.get("classifications", []):
            classifications_by_image[c.get("image_id", "")] = c

    images_by_slide: Dict[int, List[Dict[str, Any]]] = {}
    for img in (images_index or {}).get("images", []):
        si = img.get("slide_index", 0)
        if si not in images_by_slide:
            images_by_slide[si] = []
        kind_info = classifications_by_image.get(img.get("image_id", ""), {})
        images_by_slide[si].append(
            {
                "image_id": img.get("image_id"),
                "uri": img.get("uri"),
                "kind": kind_info.get("image_kind"),
                "confidence": kind_info.get("confidence"),
            }
        )

    for i in range(slide_count):
        slide_index = i + 1
        evidence_ids_created = [
            ev.get("evidence_id")
            for ev in evidence_items
            if ev.get("slide_index") == slide_index
            and (
                (ev.get("kind") or "").strip() in IMAGE_EVIDENCE_KINDS
                or (ev.get("kind") or "").startswith("DIAGRAM_")
            )
        ]
        segs_for_slide = [s for s in segments if s.get("slide_index") == slide_index]
        evidence_ids_used = []
        narration_excerpt = ""
        for s in segs_for_slide:
            evidence_ids_used.extend(s.get("evidence_ids") or [])
            if not narration_excerpt and (s.get("text") or "").strip():
                narration_excerpt = (s.get("text") or "").strip()[:500]
        evidence_ids_used = list(dict.fromkeys(evidence_ids_used))

        verifier_entries = []
        for s in segs_for_slide:
            r = report_by_claim.get(s.get("claim_id"))
            if r:
                verifier_entries.append(
                    {
                        "claim_id": r.get("claim_id"),
                        "verdict": r.get("verdict"),
                        "reason_codes": r.get("reason_codes") or r.get("reasons") or [],
                    }
                )

        payload = {
            "schema_version": "1.0",
            "job_id": job_id,
            "slide_index": slide_index,
            "embedded_images": images_by_slide.get(slide_index, []),
            "evidence_ids_created": evidence_ids_created,
            "evidence_ids_used_by_script": evidence_ids_used,
            "narration_excerpt": narration_excerpt,
            "verifier_verdict_summary": verifier_entries,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        path = f"jobs/{job_id}/debug/slide_{slide_index:03d}_vision_debug.json"
        minio_client.put(path, json.dumps(payload, indent=2).encode("utf-8"), "application/json")
