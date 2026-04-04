"""EvidenceStage: Build evidence index, run photo/diagram understand."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import PipelineContext, StageResult

try:
    from evidence_index import build_evidence_index
except ImportError:
    build_evidence_index = None  # type: ignore
    print("Warning: evidence_index not available.")

try:
    from photo_understand import run_photo_understand
except ImportError:
    run_photo_understand = None  # type: ignore

try:
    from diagram_understand import run_diagram_understand
except ImportError:
    run_diagram_understand = None  # type: ignore


class EvidenceStage:
    name = "evidence"

    def run(self, ctx: "PipelineContext") -> "StageResult":
        from pipeline import StageResult

        job_id = ctx.job_id
        db = ctx.db_session
        minio_client = ctx.minio_client
        slides_data = ctx.slides_data
        images_index = ctx.images_index
        image_kinds = ctx.image_kinds

        if not slides_data:
            return StageResult(status="skipped", metrics={"reason": "no slides_data"})

        # 1c. Build Evidence Index BEFORE photo/diagram so they append (not overwrite)
        if build_evidence_index:
            print("  Building evidence index (sources, evidence_items, source_refs)...")
            build_evidence_index(
                job_id=job_id,
                project_id=ctx.project_id,
                slides_data=slides_data,
                db_session=db,
                minio_client=minio_client,
                ppt_artifact_ids_by_slide=None,
                images_index=images_index,
            )
            print(f"  Evidence index written to jobs/{job_id}/evidence/index.json")

        # 1c2. Photo/Diagram understand (appends to evidence index)
        if images_index and ctx.vision_enabled:
            img_count = len(images_index.get("images", []))
            if img_count:
                vision_lang = ctx.vision_config.get("lang", "en-US")
                if run_photo_understand and image_kinds:
                    try:
                        photo_result = run_photo_understand(
                            job_id=job_id,
                            project_id=ctx.project_id,
                            images_index=images_index,
                            image_kinds=image_kinds,
                            minio_client=minio_client,
                            db_session=db,
                            lang=vision_lang,
                        )
                        ev_count = photo_result.get("evidence_count", 0)
                        if ev_count:
                            print(
                                f"  PHOTO understand: {ev_count} evidence items -> jobs/{job_id}/vision/photo_results.json"
                            )
                    except Exception as ep:
                        import traceback

                        print(f"  Warning: photo_understand failed: {ep}\n{traceback.format_exc()}")
                if run_diagram_understand and image_kinds:
                    try:
                        diagram_result = run_diagram_understand(
                            job_id=job_id,
                            project_id=ctx.project_id,
                            images_index=images_index,
                            image_kinds=image_kinds,
                            minio_client=minio_client,
                            db_session=db,
                            lang=vision_lang,
                        )
                        ev_count = diagram_result.get("evidence_count", 0)
                        if ev_count:
                            print(
                                f"  DIAGRAM understand: {ev_count} evidence items -> jobs/{job_id}/vision/diagram_*.json"
                            )
                    except Exception as ed:
                        import traceback

                        print(
                            f"  Warning: diagram_understand failed: {ed}\n{traceback.format_exc()}"
                        )

        return StageResult(status="ok")
