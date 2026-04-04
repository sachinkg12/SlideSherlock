"""VerifyStage: Verifier + rewrite loop, verify report, coverage, debug bundle (per-variant)."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import PipelineContext, StageResult

try:
    from verifier import (
        run_rewrite_loop,
        build_verify_report_payload,
        build_coverage_payload,
    )
except ImportError:
    run_rewrite_loop = None  # type: ignore
    build_verify_report_payload = None  # type: ignore
    build_coverage_payload = None  # type: ignore

try:
    from image_understand import write_slide_vision_debug_bundle
except ImportError:
    write_slide_vision_debug_bundle = None  # type: ignore


class VerifyStage:
    name = "verify"

    def run(self, ctx: "PipelineContext") -> "StageResult":
        from pipeline import StageResult

        try:
            from apps.api.models import Artifact
        except ImportError:
            from models import Artifact  # type: ignore

        if not ctx.verified_script:
            return StageResult(status="skipped", metrics={"reason": "no script to verify"})

        minio_client = ctx.minio_client
        db = ctx.db_session
        job_id = ctx.job_id
        variant = ctx.variant or {}
        variant_id = variant.get("id", "en")
        script_prefix = ctx.script_prefix
        script_path = f"{script_prefix}script.json"
        evidence_index = ctx.evidence_index
        unified_by_slide = ctx.unified_by_slide
        artifacts_written = []

        # 12-13. Verifier + rewrite loop
        verified_script = ctx.verified_script
        verify_report: List[Dict[str, Any]] = []
        coverage: Dict[str, Any] = {}

        if run_rewrite_loop and build_verify_report_payload and build_coverage_payload:
            # Load explain_plan from MinIO for the verifier
            explain_plan = {}
            try:
                plan_data = minio_client.get(f"{script_prefix}explain_plan.json")
                explain_plan = json.loads(plan_data.decode("utf-8"))
            except Exception:
                pass

            # Use deterministic rewrites (not LLM) in the verify loop to avoid
            # fork-safety issues with OpenAI httpx client in RQ worker processes.
            # The initial script already has AI-generated text; rewrites only
            # fix evidence grounding issues with safe deterministic templates.
            verified_script, verify_report, coverage = run_rewrite_loop(
                job_id=job_id,
                script_draft=ctx.verified_script,
                evidence_index=evidence_index,
                unified_graphs_by_slide=unified_by_slide,
                explain_plan=explain_plan,
                llm_provider=None,
                max_iters=3,
            )
            verify_report_payload = build_verify_report_payload(job_id, verify_report)
            coverage_payload = build_coverage_payload(job_id, coverage)
            verify_report_path = f"{script_prefix}verify_report.json"
            coverage_path = f"{script_prefix}coverage.json"
            minio_client.put(
                script_path,
                json.dumps(verified_script, indent=2).encode("utf-8"),
                "application/json",
            )
            minio_client.put(
                verify_report_path,
                json.dumps(verify_report_payload, indent=2).encode("utf-8"),
                "application/json",
            )
            minio_client.put(
                coverage_path,
                json.dumps(coverage_payload, indent=2).encode("utf-8"),
                "application/json",
            )
            artifacts_written.extend([script_path, verify_report_path, coverage_path])

            for path, payload, art_type in [
                (script_path, verified_script, "script_verified"),
                (verify_report_path, verify_report_payload, "verify_report"),
                (coverage_path, coverage_payload, "coverage"),
            ]:
                raw = json.dumps(payload, indent=2).encode("utf-8")
                sha = hashlib.sha256(raw).hexdigest()
                db.add(
                    Artifact(
                        artifact_id=str(uuid.uuid4()),
                        project_id=ctx.project_id,
                        job_id=job_id,
                        artifact_type=art_type,
                        storage_path=path,
                        sha256=sha,
                        size_bytes=str(len(raw)),
                        metadata_json=json.dumps(
                            {"type": art_type, "stage": "verify", "variant_id": variant_id}
                        ),
                        created_at=datetime.utcnow(),
                    )
                )
            print(
                f"  Verifier + rewrite loop: script/script.json (verified), verify_report.json, coverage.json written"
            )

        # Store for downstream
        ctx.verified_script = verified_script
        ctx.script_for_downstream = verified_script
        ctx.verify_report = verify_report
        ctx.coverage = coverage

        # Per-slide vision debug bundle
        if write_slide_vision_debug_bundle and minio_client:
            try:
                img_idx_debug = None
                kinds_debug = None
                try:
                    img_idx_debug = json.loads(
                        minio_client.get(f"jobs/{job_id}/images/index.json").decode("utf-8")
                    )
                except Exception:
                    pass
                try:
                    kinds_debug = json.loads(
                        minio_client.get(f"jobs/{job_id}/vision/image_kinds.json").decode("utf-8")
                    )
                except Exception:
                    pass
                write_slide_vision_debug_bundle(
                    job_id=job_id,
                    slide_count=ctx.slide_count,
                    evidence_index=evidence_index,
                    script=verified_script,
                    verify_report=verify_report,
                    minio_client=minio_client,
                    images_index=img_idx_debug,
                    image_kinds=kinds_debug,
                )
                print(f"  Debug: jobs/{job_id}/debug/slide_*_vision_debug.json written")
            except Exception as e:
                import traceback

                print(
                    f"  Warning: write_slide_vision_debug_bundle failed: {e}\n{traceback.format_exc()}"
                )

        return StageResult(
            status="ok",
            artifacts_written=artifacts_written,
        )
