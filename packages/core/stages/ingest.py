"""IngestStage: Download PPTX, parse slides, extract images, classify images."""
from __future__ import annotations

import json
import hashlib
import os
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import PipelineContext, StageResult

try:
    from ppt_parser import parse_pptx
except ImportError:
    parse_pptx = None  # type: ignore
    print("Warning: ppt_parser not available. Install python-pptx for PPT parsing.")

try:
    from image_extract import extract_images_from_pptx
except ImportError:
    extract_images_from_pptx = None  # type: ignore

try:
    from image_classifier import run_classify_images
except ImportError:
    run_classify_images = None  # type: ignore


class IngestStage:
    name = "ingest"

    def run(self, ctx: "PipelineContext") -> "StageResult":
        from pipeline import StageResult

        try:
            from apps.api.models import Artifact
        except ImportError:
            from models import Artifact  # type: ignore

        minio_client = ctx.minio_client
        db = ctx.db_session
        job_id = ctx.job_id
        input_file_path = ctx.config.get("input_file_path", "")
        artifacts_written = []

        # 1. Download PPTX from MinIO
        pptx_path = os.path.join(ctx.temp_dir, "input.pptx")
        print(f"  Downloading PPTX from {input_file_path}...")
        pptx_data = minio_client.get(input_file_path)
        with open(pptx_path, "wb") as f:
            f.write(pptx_data)
        print(f"  Downloaded {len(pptx_data)} bytes")

        # Store pptx_path for later stages
        ctx.config["pptx_path"] = pptx_path

        # 1b. Parse PPTX
        if parse_pptx:
            print("  Parsing PPTX (slide text, notes, shapes, connectors, groups)...")
            slides_data = parse_pptx(pptx_path)
            for slide_payload in slides_data:
                slide_idx = slide_payload["slide_index"]
                slide_num = f"{slide_idx:03d}"
                storage_path_ppt = f"jobs/{job_id}/ppt/slide_{slide_num}.json"
                slide_json = json.dumps(slide_payload, indent=2)
                slide_json_bytes = slide_json.encode("utf-8")
                slide_sha256 = hashlib.sha256(slide_json_bytes).hexdigest()
                minio_client.put(storage_path_ppt, slide_json_bytes, "application/json")
                print(f"  Uploaded {storage_path_ppt}")
                artifacts_written.append(storage_path_ppt)

                meta = {
                    "type": "ppt_slide",
                    "slide_index": slide_idx,
                    "shape_count": len(slide_payload.get("shapes", [])),
                    "connector_count": len(slide_payload.get("connectors", [])),
                    "group_count": len(slide_payload.get("groups", [])),
                    "has_notes": bool(slide_payload.get("notes", "").strip()),
                }
                ppt_artifact = Artifact(
                    artifact_id=str(uuid.uuid4()),
                    project_id=ctx.project_id,
                    job_id=job_id,
                    artifact_type="ppt_slide",
                    storage_path=storage_path_ppt,
                    sha256=slide_sha256,
                    size_bytes=str(len(slide_json_bytes)),
                    metadata_json=json.dumps(meta),
                    created_at=datetime.utcnow(),
                )
                db.add(ppt_artifact)
            if slides_data:
                db.commit()
                print(f"  Parsed {len(slides_data)} slides -> ppt/slide_*.json")

                # 1b2. Extract embedded images
                images_index = None
                image_kinds = None
                if extract_images_from_pptx:
                    try:
                        images_index = extract_images_from_pptx(pptx_path, job_id, minio_client)
                        img_count = len(images_index.get("images", []))
                        if img_count:
                            print(f"  Extracted {img_count} embedded image(s) -> jobs/{job_id}/images/")
                            if ctx.vision_enabled and run_classify_images:
                                try:
                                    force_kind = ctx.vision_config.get("force_kind_by_slide") or {}
                                    image_kinds = run_classify_images(
                                        job_id, images_index, minio_client,
                                        force_kind_by_slide=force_kind,
                                    )
                                    print(f"  Image classifier: jobs/{job_id}/vision/image_kinds.json")
                                except Exception as ec:
                                    import traceback
                                    print(f"  Warning: image classifier failed: {ec}\n{traceback.format_exc()}")
                    except Exception as e:
                        import traceback
                        print(f"  Warning: image extraction failed: {e}\n{traceback.format_exc()}")

                ctx.slides_data = slides_data
                ctx.images_index = images_index
                ctx.image_kinds = image_kinds

                # 1d. Build G_native graph
                try:
                    from native_graph import build_native_graph_and_persist
                except ImportError:
                    build_native_graph_and_persist = None  # type: ignore

                if build_native_graph_and_persist:
                    print("  Building native graph (nodes, edges, clusters, EntityLinks)...")
                    build_native_graph_and_persist(
                        job_id=job_id,
                        project_id=ctx.project_id,
                        slides_data=slides_data,
                        db_session=db,
                        minio_client=minio_client,
                    )
                    print(f"  Native graph written to jobs/{job_id}/graphs/native/slide_*.json")
            else:
                ctx.slides_data = []
        else:
            ctx.slides_data = []
            print("  Skipping PPT parse (python-pptx not available)")

        return StageResult(
            status="ok",
            artifacts_written=artifacts_written,
            metrics={"slide_count": len(ctx.slides_data)},
        )
