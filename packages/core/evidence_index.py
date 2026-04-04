"""
Evidence Index builder: from PPT slide data (notes, text, shapes, connectors)
create Source, EvidenceItem, SourceRef rows and write evidence/index.json.
evidence_id is stable: hash(job_id, slide_index, kind, offset_key).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# EMU to float for bbox in refs (store as float; 914400 EMU = 1 inch)
def _emu_to_float(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if hasattr(val, "emu"):
        return float(val.emu)
    return 0.0


def _stable_evidence_id(job_id: str, slide_index: int, kind: str, offset_key: str) -> str:
    """Stable evidence_id: same inputs => same id across reruns."""
    payload = f"{job_id}|{slide_index}|{kind}|{offset_key}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _flatten_shapes_and_connectors(slide_payload: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    """Return (list of shape dicts, list of connector dicts) including from group children."""
    shapes: List[Dict] = []
    connectors: List[Dict] = []

    def add(s: Dict) -> None:
        if s.get("ppt_connector_id"):
            connectors.append(s)
        elif s.get("type") == "GROUP" or "children" in s:
            for c in s.get("children", []):
                add(c)
        else:
            shapes.append(s)

    for s in slide_payload.get("shapes", []):
        add(s)
    for c in slide_payload.get("connectors", []):
        add(c)
    for g in slide_payload.get("groups", []):
        for c in g.get("children", []):
            add(c)

    return shapes, connectors


def build_evidence_index(
    job_id: str,
    project_id: str,
    slides_data: List[Dict[str, Any]],
    db_session: Any,
    minio_client: Any,
    ppt_artifact_ids_by_slide: Optional[Dict[int, str]] = None,
    images_index: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    From parsed slide data (list of ppt/slide_i.json payloads), create:
    - Slide, Source, EvidenceItem, SourceRef rows in DB
    - evidence/index.json written to MinIO at jobs/{job_id}/evidence/index.json
    Returns the index payload (sources, evidence_items, etc.) for JSON.
    """
    from apps.api.models import (
        Slide,
        Source,
        EvidenceItem,
        SourceRef,
        Artifact,
    )

    created_at = datetime.utcnow()
    schema_version = "1.0"
    sources_out: List[Dict] = []
    evidence_items_out: List[Dict] = []
    ppt_artifact_ids_by_slide = ppt_artifact_ids_by_slide or {}
    slide_id_by_index: Dict[int, str] = {}

    for slide_payload in slides_data:
        slide_index = slide_payload.get("slide_index", 0)
        notes = (slide_payload.get("notes") or "").strip()
        slide_text = (slide_payload.get("slide_text") or "").strip()
        shapes, connectors = _flatten_shapes_and_connectors(slide_payload)

        # Create Slide row
        slide_title = slide_text[:200] if slide_text else ""
        pptx_ref = f"jobs/{job_id}/ppt/slide_{slide_index:03d}.json"
        slide_id = str(uuid.uuid4())
        slide_row = Slide(
            slide_id=slide_id,
            job_id=job_id,
            slide_index=slide_index,
            slide_title=slide_title or None,
            png_artifact_id=None,
            pptx_ref=pptx_ref,
        )
        db_session.add(slide_row)
        db_session.flush()
        slide_id_by_index[slide_index] = slide_id

        # --- Speaker notes: one Source + one EvidenceItem (TEXT_SPAN) ---
        if notes:
            source_notes_id = str(uuid.uuid4())
            ev_id_notes = _stable_evidence_id(job_id, slide_index, "TEXT_SPAN", "notes")
            source_row = Source(
                source_id=source_notes_id,
                job_id=job_id,
                type="PPT_NOTES",
                artifact_id=ppt_artifact_ids_by_slide.get(slide_index),
                slide_id=slide_id,
                created_at=created_at,
            )
            db_session.add(source_row)
            db_session.flush()

            ev_row = EvidenceItem(
                evidence_id=ev_id_notes,
                job_id=job_id,
                slide_id=slide_id,
                source_id=source_notes_id,
                kind="TEXT_SPAN",
                content=notes,
                content_hash=_content_hash(notes),
                confidence=1.0,
                language=None,
                created_at=created_at,
            )
            db_session.add(ev_row)

            ref_row = SourceRef(
                ref_id=str(uuid.uuid4()),
                evidence_id=ev_id_notes,
                ref_type="PPT",
                slide_index=slide_index,
                ppt_shape_id=None,
                ppt_paragraph_ix=None,
                ppt_run_ix=None,
                bbox_x=None,
                bbox_y=None,
                bbox_w=None,
                bbox_h=None,
                page_num=None,
                char_start=0,
                char_end=len(notes),
                url=None,
            )
            db_session.add(ref_row)

            sources_out.append(
                {
                    "source_id": source_notes_id,
                    "type": "PPT_NOTES",
                    "slide_index": slide_index,
                    "artifact_url": None,
                    "metadata": {},
                }
            )
            evidence_items_out.append(
                {
                    "evidence_id": ev_id_notes,
                    "source_id": source_notes_id,
                    "kind": "TEXT_SPAN",
                    "content": notes,
                    "content_hash": _content_hash(notes),
                    "confidence": 1.0,
                    "slide_index": slide_index,
                    "refs": [
                        {
                            "ref_type": "PPT",
                            "slide_index": slide_index,
                            "char_start": 0,
                            "char_end": len(notes),
                        }
                    ],
                }
            )

        # --- Slide text: one Source + one EvidenceItem (TEXT_SPAN) ---
        if slide_text:
            source_text_id = str(uuid.uuid4())
            ev_id_text = _stable_evidence_id(job_id, slide_index, "TEXT_SPAN", "slide_text")
            source_row = Source(
                source_id=source_text_id,
                job_id=job_id,
                type="PPT_TEXT",
                artifact_id=ppt_artifact_ids_by_slide.get(slide_index),
                slide_id=slide_id,
                created_at=created_at,
            )
            db_session.add(source_row)
            db_session.flush()

            ev_row = EvidenceItem(
                evidence_id=ev_id_text,
                job_id=job_id,
                slide_id=slide_id,
                source_id=source_text_id,
                kind="TEXT_SPAN",
                content=slide_text,
                content_hash=_content_hash(slide_text),
                confidence=1.0,
                language=None,
                created_at=created_at,
            )
            db_session.add(ev_row)

            ref_row = SourceRef(
                ref_id=str(uuid.uuid4()),
                evidence_id=ev_id_text,
                ref_type="PPT",
                slide_index=slide_index,
                ppt_shape_id=None,
                ppt_paragraph_ix=None,
                ppt_run_ix=None,
                bbox_x=None,
                bbox_y=None,
                bbox_w=None,
                bbox_h=None,
                page_num=None,
                char_start=0,
                char_end=len(slide_text),
                url=None,
            )
            db_session.add(ref_row)

            sources_out.append(
                {
                    "source_id": source_text_id,
                    "type": "PPT_TEXT",
                    "slide_index": slide_index,
                    "artifact_url": None,
                    "metadata": {},
                }
            )
            evidence_items_out.append(
                {
                    "evidence_id": ev_id_text,
                    "source_id": source_text_id,
                    "kind": "TEXT_SPAN",
                    "content": slide_text,
                    "content_hash": _content_hash(slide_text),
                    "confidence": 1.0,
                    "slide_index": slide_index,
                    "refs": [
                        {
                            "ref_type": "PPT",
                            "slide_index": slide_index,
                            "char_start": 0,
                            "char_end": len(slide_text),
                        }
                    ],
                }
            )

        # --- Shape labels: one Source + one EvidenceItem (SHAPE_LABEL) per shape with text ---
        for shape in shapes:
            text_runs = shape.get("text_runs") or []
            if not text_runs:
                continue
            content = " ".join(r.get("text", "") for r in text_runs).strip()
            if not content:
                continue
            ppt_shape_id = shape.get("ppt_shape_id", "")
            bbox = shape.get("bbox") or {}
            source_shape_id = str(uuid.uuid4())
            ev_id_shape = _stable_evidence_id(job_id, slide_index, "SHAPE_LABEL", ppt_shape_id)

            source_row = Source(
                source_id=source_shape_id,
                job_id=job_id,
                type="PPT_SHAPE",
                artifact_id=ppt_artifact_ids_by_slide.get(slide_index),
                slide_id=slide_id,
                created_at=created_at,
            )
            db_session.add(source_row)
            db_session.flush()

            ev_row = EvidenceItem(
                evidence_id=ev_id_shape,
                job_id=job_id,
                slide_id=slide_id,
                source_id=source_shape_id,
                kind="SHAPE_LABEL",
                content=content,
                content_hash=_content_hash(content),
                confidence=1.0,
                language=None,
                created_at=created_at,
            )
            db_session.add(ev_row)

            ref_row = SourceRef(
                ref_id=str(uuid.uuid4()),
                evidence_id=ev_id_shape,
                ref_type="PPT",
                slide_index=slide_index,
                ppt_shape_id=ppt_shape_id,
                ppt_paragraph_ix=0,
                ppt_run_ix=0,
                bbox_x=_emu_to_float(bbox.get("left")),
                bbox_y=_emu_to_float(bbox.get("top")),
                bbox_w=_emu_to_float(bbox.get("width")),
                bbox_h=_emu_to_float(bbox.get("height")),
                page_num=None,
                char_start=None,
                char_end=None,
                url=None,
            )
            db_session.add(ref_row)

            ref_item = {"ref_type": "PPT", "slide_index": slide_index, "ppt_shape_id": ppt_shape_id}
            if bbox:
                ref_item["bbox_x"] = _emu_to_float(bbox.get("left"))
                ref_item["bbox_y"] = _emu_to_float(bbox.get("top"))
                ref_item["bbox_w"] = _emu_to_float(bbox.get("width"))
                ref_item["bbox_h"] = _emu_to_float(bbox.get("height"))

            sources_out.append(
                {
                    "source_id": source_shape_id,
                    "type": "PPT_SHAPE",
                    "slide_index": slide_index,
                    "artifact_url": None,
                    "metadata": {"ppt_shape_id": ppt_shape_id},
                }
            )
            evidence_items_out.append(
                {
                    "evidence_id": ev_id_shape,
                    "source_id": source_shape_id,
                    "kind": "SHAPE_LABEL",
                    "content": content,
                    "content_hash": _content_hash(content),
                    "confidence": 1.0,
                    "slide_index": slide_index,
                    "refs": [ref_item],
                }
            )

        # --- Connector labels: one Source + one EvidenceItem (CONNECTOR) per connector with label ---
        for conn in connectors:
            label = (conn.get("label") or "").strip()
            content = label if label else " "
            ppt_connector_id = conn.get("ppt_connector_id", "")
            bbox = conn.get("bbox") or {}
            source_conn_id = str(uuid.uuid4())
            ev_id_conn = _stable_evidence_id(job_id, slide_index, "CONNECTOR", ppt_connector_id)

            source_row = Source(
                source_id=source_conn_id,
                job_id=job_id,
                type="PPT_SHAPE",
                artifact_id=ppt_artifact_ids_by_slide.get(slide_index),
                slide_id=slide_id,
                created_at=created_at,
            )
            db_session.add(source_row)
            db_session.flush()

            ev_row = EvidenceItem(
                evidence_id=ev_id_conn,
                job_id=job_id,
                slide_id=slide_id,
                source_id=source_conn_id,
                kind="CONNECTOR",
                content=content,
                content_hash=_content_hash(content),
                confidence=1.0,
                language=None,
                created_at=created_at,
            )
            db_session.add(ev_row)

            ref_row = SourceRef(
                ref_id=str(uuid.uuid4()),
                evidence_id=ev_id_conn,
                ref_type="PPT",
                slide_index=slide_index,
                ppt_shape_id=ppt_connector_id,
                ppt_paragraph_ix=None,
                ppt_run_ix=None,
                bbox_x=_emu_to_float(bbox.get("left")),
                bbox_y=_emu_to_float(bbox.get("top")),
                bbox_w=_emu_to_float(bbox.get("width")),
                bbox_h=_emu_to_float(bbox.get("height")),
                page_num=None,
                char_start=None,
                char_end=None,
                url=None,
            )
            db_session.add(ref_row)

            ref_item = {
                "ref_type": "PPT",
                "slide_index": slide_index,
                "ppt_shape_id": ppt_connector_id,
            }
            if bbox:
                ref_item["bbox_x"] = _emu_to_float(bbox.get("left"))
                ref_item["bbox_y"] = _emu_to_float(bbox.get("top"))
                ref_item["bbox_w"] = _emu_to_float(bbox.get("width"))
                ref_item["bbox_h"] = _emu_to_float(bbox.get("height"))

            sources_out.append(
                {
                    "source_id": source_conn_id,
                    "type": "PPT_SHAPE",
                    "slide_index": slide_index,
                    "artifact_url": None,
                    "metadata": {"ppt_connector_id": ppt_connector_id},
                }
            )
            evidence_items_out.append(
                {
                    "evidence_id": ev_id_conn,
                    "source_id": source_conn_id,
                    "kind": "CONNECTOR",
                    "content": content,
                    "content_hash": _content_hash(content),
                    "confidence": 1.0,
                    "slide_index": slide_index,
                    "refs": [ref_item],
                }
            )

    # --- IMAGE_ASSET: one EvidenceItem per extracted embedded image ---
    if images_index:
        for img in images_index.get("images", []):
            image_id = img.get("image_id")
            ppt_shape_id = img.get("ppt_shape_id", "")
            slide_index = img.get("slide_index", 0)
            uri = img.get("uri", "")
            mime = img.get("mime", "image/png")
            sha256_val = img.get("sha256", "")
            bbox = img.get("bbox") or {}
            norm = img.get("normalized_bbox") or {}

            ev_id = _stable_evidence_id(
                job_id, slide_index, "IMAGE_ASSET", ppt_shape_id or image_id
            )
            content = f"image_uri={uri}, mime={mime}, sha256={sha256_val}"
            source_img_id = str(uuid.uuid4())
            slide_id = slide_id_by_index.get(slide_index)

            source_row = Source(
                source_id=source_img_id,
                job_id=job_id,
                type="IMAGE_ASSET",
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
                source_id=source_img_id,
                kind="IMAGE_ASSET",
                content=content,
                content_hash=_content_hash(content),
                confidence=1.0,
                language=None,
                created_at=created_at,
            )
            db_session.add(ev_row)

            ref_row = SourceRef(
                ref_id=str(uuid.uuid4()),
                evidence_id=ev_id,
                ref_type="IMAGE",
                slide_index=slide_index,
                ppt_shape_id=ppt_shape_id or None,
                ppt_paragraph_ix=None,
                ppt_run_ix=None,
                bbox_x=_emu_to_float(bbox.get("x")),
                bbox_y=_emu_to_float(bbox.get("y")),
                bbox_w=_emu_to_float(bbox.get("w")),
                bbox_h=_emu_to_float(bbox.get("h")),
                page_num=None,
                char_start=None,
                char_end=None,
                url=uri,
            )
            db_session.add(ref_row)

            ref_item = {
                "ref_type": "IMAGE",
                "slide_index": slide_index,
                "url": uri,
                "bbox_x": _emu_to_float(bbox.get("x")),
                "bbox_y": _emu_to_float(bbox.get("y")),
                "bbox_w": _emu_to_float(bbox.get("w")),
                "bbox_h": _emu_to_float(bbox.get("h")),
            }
            sources_out.append(
                {
                    "source_id": source_img_id,
                    "type": "IMAGE_ASSET",
                    "slide_index": slide_index,
                    "artifact_url": uri,
                    "metadata": {"ppt_shape_id": ppt_shape_id, "normalized_bbox": norm},
                }
            )
            evidence_items_out.append(
                {
                    "evidence_id": ev_id,
                    "source_id": source_img_id,
                    "kind": "IMAGE_ASSET",
                    "content": content,
                    "content_hash": _content_hash(content),
                    "confidence": 1.0,
                    "slide_index": slide_index,
                    "refs": [ref_item],
                }
            )

    # Build index JSON (schema_versioned)
    index_payload = {
        "schema_version": schema_version,
        "job_id": job_id,
        "created_at": created_at.isoformat() + "Z",
        "sources": sources_out,
        "evidence_items": evidence_items_out,
        "entity_links": [],
        "claim_links": [],
        "artifacts": [],
    }

    # Write to MinIO
    storage_path = f"jobs/{job_id}/evidence/index.json"
    index_json = json.dumps(index_payload, indent=2)
    index_bytes = index_json.encode("utf-8")
    minio_client.put(storage_path, index_bytes, "application/json")

    # Create artifact record for evidence/index.json
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
                "schema_version": schema_version,
                "source_count": len(sources_out),
                "evidence_count": len(evidence_items_out),
            }
        ),
        created_at=created_at,
    )
    db_session.add(artifact_row)
    db_session.commit()

    return index_payload
