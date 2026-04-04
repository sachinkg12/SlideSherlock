"""GraphStage: Build vision graphs, merge with native -> G_unified, image understand."""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import PipelineContext, StageResult

try:
    from vision_graph import build_vision_graph_slide
except ImportError:
    build_vision_graph_slide = None  # type: ignore

try:
    from merge_engine import merge_graphs
except ImportError:
    merge_graphs = None  # type: ignore

try:
    from image_understand import run_image_understand
except ImportError:
    run_image_understand = None  # type: ignore


class GraphStage:
    name = "graph"

    def run(self, ctx: "PipelineContext") -> "StageResult":
        from pipeline import StageResult

        minio_client = ctx.minio_client
        db = ctx.db_session
        job_id = ctx.job_id
        slide_count = ctx.slide_count
        slide_metadata = ctx.slide_metadata
        slides = ctx.slides_pil
        slides_data = ctx.slides_data

        if not slide_count:
            return StageResult(status="skipped", metrics={"reason": "no slides"})

        # 7. Vision pipeline (optional) + merge -> G_unified
        vision_enabled = os.environ.get("VISION_ENABLED", "").lower() in ("1", "true", "yes")
        image_understand_enabled = os.environ.get("IMAGE_UNDERSTAND_ENABLED", "1").lower() in (
            "1",
            "true",
            "yes",
        )
        all_merge_flags = []
        vision_graphs_by_slide: Dict[int, Dict[str, Any]] = {}

        if merge_graphs:
            for i in range(slide_count):
                slide_index = i + 1
                slide_num = f"{slide_index:03d}"
                native_path = f"jobs/{job_id}/graphs/native/slide_{slide_num}.json"
                try:
                    native_data = minio_client.get(native_path)
                    g_native = json.loads(native_data.decode("utf-8"))
                except Exception as e:
                    print(f"  Warning: could not load {native_path}: {e}")
                    continue
                width_px = slide_metadata[i]["width"]
                height_px = slide_metadata[i]["height"]
                g_vision = None
                if vision_enabled and build_vision_graph_slide and i < len(slides):
                    slide_img = slides[i]
                    try:
                        vision_out = build_vision_graph_slide(
                            slide_img, slide_index, ocr_backend="tesseract", detect_lines=False
                        )
                        g_vision = {
                            "slide_index": slide_index,
                            "nodes": vision_out["nodes"],
                            "edges": vision_out["edges"],
                        }
                        # Write ocr/slide_i.json (text_spans)
                        ocr_path = f"jobs/{job_id}/ocr/slide_{slide_num}.json"
                        minio_client.put(
                            ocr_path,
                            json.dumps(
                                {
                                    "slide_index": slide_index,
                                    "text_spans": vision_out["text_spans"],
                                },
                                indent=2,
                            ).encode("utf-8"),
                            "application/json",
                        )
                        # Write graphs/vision/slide_i.json
                        vision_path = f"jobs/{job_id}/graphs/vision/slide_{slide_num}.json"
                        minio_client.put(
                            vision_path,
                            json.dumps(g_vision, indent=2).encode("utf-8"),
                            "application/json",
                        )
                    except Exception as e:
                        print(f"  Warning: vision failed for slide {slide_index}: {e}")
                if g_vision:
                    vision_graphs_by_slide[slide_index] = g_vision
                g_unified, flags = merge_graphs(
                    g_native,
                    g_vision,
                    slide_width_px=float(width_px),
                    slide_height_px=float(height_px),
                )
                unified_path = f"jobs/{job_id}/graphs/unified/slide_{slide_num}.json"
                minio_client.put(
                    unified_path,
                    json.dumps(g_unified, indent=2).encode("utf-8"),
                    "application/json",
                )
                all_merge_flags.append(flags)
            if all_merge_flags:
                merge_flags_path = f"jobs/{job_id}/graphs/unified/flags.json"
                merge_flags_payload = {
                    "job_id": job_id,
                    "slides": all_merge_flags,
                    "created_at": datetime.utcnow().isoformat() + "Z",
                }
                minio_client.put(
                    merge_flags_path,
                    json.dumps(merge_flags_payload, indent=2).encode("utf-8"),
                    "application/json",
                )
                print(f"  Unified graph written to jobs/{job_id}/graphs/unified/slide_*.json")

        ctx.vision_graphs_by_slide = vision_graphs_by_slide

        # 7b. Image understand stage
        if run_image_understand and image_understand_enabled and slides_data:
            try:
                print("  Running image understand (vision evidence with provenance)...")
                img_result = run_image_understand(
                    job_id=job_id,
                    project_id=ctx.project_id,
                    slide_count=slide_count,
                    slides_data=slides_data,
                    slides_png=slides,
                    minio_client=minio_client,
                    db_session=db,
                    vision_graphs_by_slide=vision_graphs_by_slide,
                )
                print(
                    f"  Image understand: {img_result.get('image_evidence_count', 0)} evidence items, vision/* written"
                )
            except Exception as e:
                import traceback

                print(f"  Warning: image_understand failed: {e}\n{traceback.format_exc()}")

        # Load unified graphs for downstream stages
        unified_graphs = []
        for i in range(slide_count):
            slide_index = i + 1
            slide_num = f"{slide_index:03d}"
            unified_path = f"jobs/{job_id}/graphs/unified/slide_{slide_num}.json"
            try:
                data = minio_client.get(unified_path)
                unified_graphs.append(json.loads(data.decode("utf-8")))
            except Exception as e:
                print(f"  Warning: could not load {unified_path}: {e}")

        ctx.unified_graphs = unified_graphs
        ctx.unified_by_slide = {
            g.get("slide_index", i + 1): g for i, g in enumerate(unified_graphs)
        }

        return StageResult(
            status="ok",
            metrics={"unified_graph_count": len(unified_graphs)},
        )
