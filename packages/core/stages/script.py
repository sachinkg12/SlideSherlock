"""ScriptStage: Explain plan, context bundles, script generation (per-variant)."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import PipelineContext, StageResult

try:
    from explain_plan import build_explain_plan
except ImportError:
    build_explain_plan = None  # type: ignore

try:
    from script_generator import generate_script
except ImportError:
    generate_script = None  # type: ignore

try:
    from rag import retrieve_chunk_ids
except ImportError:
    retrieve_chunk_ids = None  # type: ignore


class ScriptStage:
    name = "script"

    def run(self, ctx: "PipelineContext") -> "StageResult":
        from pipeline import StageResult

        try:
            from apps.api.models import Artifact, EntityLink, EvidenceItem
        except ImportError:
            from models import Artifact, EntityLink, EvidenceItem  # type: ignore

        if not build_explain_plan or not generate_script or not ctx.llm_provider:
            return StageResult(status="skipped", metrics={"reason": "missing dependencies"})

        if not ctx.unified_graphs:
            return StageResult(status="skipped", metrics={"reason": "no unified graphs"})

        minio_client = ctx.minio_client
        db = ctx.db_session
        job_id = ctx.job_id
        variant = ctx.variant or {}
        variant_id = variant.get("id", "en")
        script_prefix = ctx.script_prefix
        slide_count = ctx.slide_count
        unified_by_slide = ctx.unified_by_slide
        artifacts_written = []

        # Load evidence index
        evidence_path = f"jobs/{job_id}/evidence/index.json"
        try:
            ev_data = minio_client.get(evidence_path)
            evidence_index = json.loads(ev_data.decode("utf-8"))
        except Exception as e:
            print(f"  Warning: could not load evidence index: {e}")
            evidence_index = {"evidence_items": [], "sources": []}
        ctx.evidence_index = evidence_index

        # EntityLink -> entity_to_evidence
        entity_to_evidence: Dict[str, List[str]] = {}
        for link in db.query(EntityLink).join(
            EvidenceItem, EntityLink.evidence_id == EvidenceItem.evidence_id
        ).filter(EvidenceItem.job_id == job_id):
            entity_to_evidence.setdefault(link.entity_id, []).append(link.evidence_id)

        # RAG hook
        rag_chunk_ids: List[str] = []
        docs_enabled = os.environ.get("DOCS_RAG_ENABLED", "").lower() in ("1", "true", "yes")
        if docs_enabled and retrieve_chunk_ids:
            docs_path = f"jobs/{job_id}/docs/chunks.json"
            try:
                doc_data = minio_client.get(docs_path)
                docs_payload = json.loads(doc_data.decode("utf-8"))
                chunks = docs_payload.get("chunks", [])
                if chunks:
                    ev_items = evidence_index.get("evidence_items", [])
                    query = " ".join((ev.get("content", "") or "")[:200] for ev in ev_items[:10]) or "slide diagram"
                    rag_chunk_ids = retrieve_chunk_ids(query, chunks, text_key="text", id_key="id", top_k=5)
            except Exception:
                pass

        explain_plan = build_explain_plan(job_id, ctx.unified_graphs, rag_chunk_ids=rag_chunk_ids if rag_chunk_ids else None)

        # Per-slide context for script (notes, image evidence)
        slides_notes_and_text_for_script: List[Tuple[str, str]] = []
        for i in range(slide_count):
            slide_num = f"{(i + 1):03d}"
            ppt_path = f"jobs/{job_id}/ppt/slide_{slide_num}.json"
            notes, slide_text = "", ""
            try:
                ppt_data = minio_client.get(ppt_path)
                ppt_payload = json.loads(ppt_data.decode("utf-8"))
                notes = (ppt_payload.get("notes") or "").strip()
                slide_text = (ppt_payload.get("slide_text") or "").strip()
            except Exception:
                pass
            slides_notes_and_text_for_script.append((notes, slide_text))

        context_bundles_by_slide: Dict[int, Any] = {}
        try:
            from script_context import build_context_bundles_per_slide
            context_bundles_by_slide = build_context_bundles_per_slide(
                slide_count, slides_notes_and_text_for_script, unified_by_slide, evidence_index
            )
        except ImportError:
            pass

        stub_llm = ctx.llm_provider
        script_draft = generate_script(
            job_id=job_id,
            explain_plan=explain_plan,
            unified_graphs_by_slide=unified_by_slide,
            evidence_index=evidence_index,
            entity_to_evidence=entity_to_evidence,
            llm_provider=stub_llm,
            context_bundles_by_slide=context_bundles_by_slide,
            slides_notes_and_text=slides_notes_and_text_for_script,
        )

        plan_path = f"{script_prefix}explain_plan.json"
        script_path = f"{script_prefix}script.json"
        minio_client.put(plan_path, json.dumps(explain_plan, indent=2).encode("utf-8"), "application/json")
        minio_client.put(script_path, json.dumps(script_draft, indent=2).encode("utf-8"), "application/json")
        artifacts_written.extend([plan_path, script_path])

        for path, payload, art_type in [
            (plan_path, explain_plan, "explain_plan"),
            (script_path, script_draft, "script_draft"),
        ]:
            raw = json.dumps(payload, indent=2).encode("utf-8")
            sha = hashlib.sha256(raw).hexdigest()
            db.add(Artifact(
                artifact_id=str(uuid.uuid4()),
                project_id=ctx.project_id,
                job_id=job_id,
                artifact_type=art_type,
                storage_path=path,
                sha256=sha,
                size_bytes=str(len(raw)),
                metadata_json=json.dumps({"type": art_type, "stage": "script", "variant_id": variant_id}),
                created_at=datetime.utcnow(),
            ))
        print(f"  Explain plan + script written to {script_prefix}")

        # Store for downstream stages
        ctx.verified_script = script_draft
        ctx.script_for_downstream = script_draft

        return StageResult(
            status="ok",
            artifacts_written=artifacts_written,
        )
