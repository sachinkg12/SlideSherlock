"""RenderStage: PPTX->PDF->PNG, upload to MinIO, write manifest, caption fallback, vision summary."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import PipelineContext, StageResult

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None
    print("Warning: pdf2image not available. Install with: pip install pdf2image")

try:
    from slide_caption_fallback import run_slide_caption_fallback
except ImportError:
    run_slide_caption_fallback = None  # type: ignore

try:
    from image_understand import write_vision_summary
except ImportError:
    write_vision_summary = None  # type: ignore

try:
    from variants import build_output_variants
except ImportError:
    build_output_variants = None  # type: ignore


class RenderStage:
    name = "render"

    def run(self, ctx: "PipelineContext") -> "StageResult":
        from pipeline import StageResult

        try:
            from apps.api.models import Artifact
        except ImportError:
            from models import Artifact  # type: ignore

        minio_client = ctx.minio_client
        db = ctx.db_session
        job_id = ctx.job_id
        temp_dir = ctx.temp_dir
        pptx_path = ctx.config.get("pptx_path", os.path.join(temp_dir, "input.pptx"))
        artifacts_written = []

        # 2. Convert PPTX to PDF using LibreOffice headless
        pdf_basename = os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf"
        pdf_path = os.path.join(temp_dir, pdf_basename)
        print("  Converting PPTX to PDF using LibreOffice...")

        libreoffice_bin = "libreoffice"
        if os.path.exists("/Applications/LibreOffice.app/Contents/MacOS/soffice"):
            libreoffice_bin = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        elif os.path.exists("/Applications/LibreOffice.app/Contents/MacOS/soffice.bin"):
            libreoffice_bin = "/Applications/LibreOffice.app/Contents/MacOS/soffice.bin"

        libreoffice_cmd = [
            libreoffice_bin,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            temp_dir,
            pptx_path,
        ]
        # Retry once on failure — LibreOffice crashes are often transient
        # (process leak, temp file lock, zombie soffice.bin).
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            result = subprocess.run(
                libreoffice_cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0 and os.path.exists(pdf_path):
                break
            if attempt < max_attempts:
                import time

                print(f"  LibreOffice attempt {attempt} failed, retrying in 2s...")
                time.sleep(2)
        if result.returncode != 0:
            raise Exception(f"LibreOffice conversion failed: {result.stderr or result.stdout}")

        if not os.path.exists(pdf_path):
            raise Exception(f"PDF file not created at {pdf_path}")

        pdf_size = os.path.getsize(pdf_path)
        print(f"  Created PDF: {pdf_size} bytes")

        # 3. Convert PDF to PNG slides using pdf2image
        if not convert_from_path:
            raise Exception("pdf2image not available. Install with: pip install pdf2image")

        print("  Converting PDF to PNG slides...")
        slides = convert_from_path(pdf_path, dpi=150)
        slide_count = len(slides)
        print(f"  Created {slide_count} PNG slides")

        # 4. Upload PDF to MinIO
        pdf_storage_path = f"jobs/{job_id}/render/deck.pdf"
        print(f"  Uploading PDF to {pdf_storage_path}...")
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
        pdf_sha256 = hashlib.sha256(pdf_data).hexdigest()
        minio_client.put(pdf_storage_path, pdf_data, "application/pdf")
        print(f"  Uploaded PDF: {pdf_sha256[:16]}...")
        artifacts_written.append(pdf_storage_path)

        pdf_artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            project_id=ctx.project_id,
            job_id=job_id,
            artifact_type="pdf",
            storage_path=pdf_storage_path,
            sha256=pdf_sha256,
            size_bytes=str(pdf_size),
            metadata_json=json.dumps({"type": "render_pdf", "slide_count": slide_count}),
            created_at=datetime.utcnow(),
        )
        db.add(pdf_artifact)

        # 5. Upload PNG slides to MinIO and collect metadata
        slide_metadata = []
        for i, slide_img in enumerate(slides, start=1):
            slide_num = f"{i:03d}"
            slide_storage_path = f"jobs/{job_id}/render/slides/slide_{slide_num}.png"
            print(f"  Uploading slide {i}/{slide_count} to {slide_storage_path}...")

            from io import BytesIO

            png_buffer = BytesIO()
            slide_img.save(png_buffer, format="PNG")
            png_data = png_buffer.getvalue()
            png_sha256 = hashlib.sha256(png_data).hexdigest()
            png_size = len(png_data)

            width, height = slide_img.size

            minio_client.put(slide_storage_path, png_data, "image/png")
            artifacts_written.append(slide_storage_path)

            png_artifact = Artifact(
                artifact_id=str(uuid.uuid4()),
                project_id=ctx.project_id,
                job_id=job_id,
                artifact_type="png",
                storage_path=slide_storage_path,
                sha256=png_sha256,
                size_bytes=str(png_size),
                metadata_json=json.dumps(
                    {
                        "type": "render_slide",
                        "slide_number": i,
                        "width": width,
                        "height": height,
                    }
                ),
                created_at=datetime.utcnow(),
            )
            db.add(png_artifact)

            slide_metadata.append(
                {
                    "slide_number": i,
                    "filename": f"slide_{slide_num}.png",
                    "storage_path": slide_storage_path,
                    "width": width,
                    "height": height,
                    "size_bytes": png_size,
                    "sha256": png_sha256,
                }
            )

        # 5b. Slide-level caption fallback
        if ctx.vision_enabled and run_slide_caption_fallback and slide_count:
            try:
                vision_lang = ctx.vision_config.get("lang", "en-US")
                cap_result = run_slide_caption_fallback(
                    job_id=job_id,
                    project_id=ctx.project_id,
                    slide_count=slide_count,
                    minio_client=minio_client,
                    db_session=db,
                    lang=vision_lang,
                )
                n = cap_result.get("evidence_count", 0)
                if n:
                    print(
                        f"  Slide caption fallback: {n} SLIDE_CAPTION evidence item(s) for slides {cap_result.get('slides_captioned', [])}"
                    )
            except Exception as e:
                import traceback

                print(f"  Warning: slide_caption_fallback failed: {e}\n{traceback.format_exc()}")

        # 5c. Debug: vision summary
        if write_vision_summary and minio_client:
            try:
                write_vision_summary(job_id=job_id, minio_client=minio_client)
            except Exception as e:
                import traceback

                print(f"  Warning: write_vision_summary failed: {e}\n{traceback.format_exc()}")

        # 6. Generate manifest.json (with output_variants)
        try:
            from apps.api.models import Job as JobModel
        except ImportError:
            from models import Job as JobModel  # type: ignore

        job_obj = db.query(JobModel).filter(JobModel.job_id == job_id).first()
        requested_lang = getattr(job_obj, "requested_language", None) or None
        output_variants = (
            build_output_variants(requested_lang)
            if build_output_variants
            else [
                {"id": "en", "lang": "en-US", "voice_id": "default_en", "notes_translate": False},
            ]
        )

        manifest = {
            "job_id": job_id,
            "stage": "render",
            "slide_count": slide_count,
            "output_variants": output_variants,
            "pdf": {
                "storage_path": pdf_storage_path,
                "size_bytes": pdf_size,
                "sha256": pdf_sha256,
            },
            "slides": slide_metadata,
            "created_at": datetime.utcnow().isoformat(),
        }

        manifest_json = json.dumps(manifest, indent=2)
        manifest_storage_path = f"jobs/{job_id}/render/manifest.json"
        manifest_sha256 = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()

        print(f"  Uploading manifest to {manifest_storage_path}...")
        minio_client.put(manifest_storage_path, manifest_json.encode("utf-8"), "application/json")
        artifacts_written.append(manifest_storage_path)

        manifest_artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            project_id=ctx.project_id,
            job_id=job_id,
            artifact_type="manifest",
            storage_path=manifest_storage_path,
            sha256=manifest_sha256,
            size_bytes=str(len(manifest_json)),
            metadata_json=json.dumps({"type": "render_manifest", "stage": "render"}),
            created_at=datetime.utcnow(),
        )
        db.add(manifest_artifact)

        # Store results in context
        ctx.slide_count = slide_count
        ctx.slide_metadata = slide_metadata
        ctx.slides_pil = list(slides)
        ctx.output_variants = output_variants

        return StageResult(
            status="ok",
            artifacts_written=artifacts_written,
            metrics={"slide_count": slide_count, "pdf_size": pdf_size},
        )
