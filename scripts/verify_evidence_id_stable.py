#!/usr/bin/env python3
"""
Verify acceptance: evidence_id stable across reruns for same input.

Usage:
  From repo root, with venv and infra (Postgres, MinIO) up:
    PYTHONPATH=. venv/bin/python scripts/verify_evidence_id_stable.py <JOB_ID>

  Or after running ./test_api.sh or ./test_render.sh, copy the printed JOB_ID and run:
    PYTHONPATH=. venv/bin/python scripts/verify_evidence_id_stable.py <JOB_ID>

What it does:
  1. Loads ppt/slide_*.json from MinIO for the given job (same input as evidence index).
  2. Clears evidence data for that job (slides, sources, evidence_items, source_refs, etc.).
  3. Runs the evidence index builder -> records evidence_ids (run 1).
  4. Clears evidence data again, runs the builder again -> records evidence_ids (run 2).
  5. Asserts run 1 and run 2 have the same set of evidence_ids (stable across reruns).
"""
import json
import sys
import os

# Repo root on path so we can import apps.api and packages.core
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# After worker/API path setup we need apps.api and packages.core
sys.path.insert(0, os.path.join(repo_root, "packages", "core"))


def main():
    if len(sys.argv) != 2:
        print("Usage: PYTHONPATH=. venv/bin/python scripts/verify_evidence_id_stable.py <JOB_ID>")
        print(
            "  Get JOB_ID from ./test_api.sh or ./test_render.sh output after uploading test.pptx"
        )
        sys.exit(1)
    job_id = sys.argv[1].strip()

    from apps.api.database import SessionLocal
    from apps.api.models import (
        Job,
        Slide,
        Source,
        EvidenceItem,
        SourceRef,
        ClaimLink,
        EntityLink,
        Artifact,
    )
    from storage import MinIOClient
    from evidence_index import build_evidence_index

    db = SessionLocal()
    minio = MinIOClient()

    # Resolve project_id from job
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        print(f"Job not found: {job_id}")
        sys.exit(1)
    project_id = job.project_id

    # Load ppt/slide_*.json from MinIO (same input as evidence index)
    prefix = f"jobs/{job_id}/ppt/"
    try:
        resp = minio.client.list_objects_v2(Bucket=minio.bucket, Prefix=prefix)
        keys = [c["Key"] for c in resp.get("Contents", []) if c["Key"].endswith(".json")]
    except Exception as e:
        print(f"Failed to list MinIO keys: {e}")
        sys.exit(1)
    keys.sort()
    if not keys:
        print(
            f"No ppt/slide_*.json found under {prefix}. Run the pipeline first (upload test.pptx, let worker run)."
        )
        sys.exit(1)

    slides_data = []
    for key in keys:
        data = minio.get(key)
        slides_data.append(json.loads(data.decode("utf-8")))

    def clear_evidence_for_job():
        # Delete in FK order (child tables first)
        subq = db.query(EvidenceItem.evidence_id).filter(EvidenceItem.job_id == job_id)
        db.query(EntityLink).filter(EntityLink.evidence_id.in_(subq)).delete(
            synchronize_session=False
        )
        subq = db.query(EvidenceItem.evidence_id).filter(EvidenceItem.job_id == job_id)
        db.query(ClaimLink).filter(ClaimLink.evidence_id.in_(subq)).delete(
            synchronize_session=False
        )
        subq = db.query(EvidenceItem.evidence_id).filter(EvidenceItem.job_id == job_id)
        db.query(SourceRef).filter(SourceRef.evidence_id.in_(subq)).delete(
            synchronize_session=False
        )
        db.query(EvidenceItem).filter(EvidenceItem.job_id == job_id).delete()
        db.query(Source).filter(Source.job_id == job_id).delete()
        db.query(Slide).filter(Slide.job_id == job_id).delete()
        db.query(Artifact).filter(
            Artifact.job_id == job_id,
            Artifact.artifact_type == "evidence_index",
        ).delete()
        db.commit()

    def get_evidence_ids():
        rows = db.query(EvidenceItem.evidence_id).filter(EvidenceItem.job_id == job_id).all()
        return sorted(r[0] for r in rows)

    # Run 1
    clear_evidence_for_job()
    build_evidence_index(
        job_id=job_id,
        project_id=project_id,
        slides_data=slides_data,
        db_session=db,
        minio_client=minio,
        ppt_artifact_ids_by_slide=None,
    )
    ids_run1 = get_evidence_ids()

    # Run 2
    clear_evidence_for_job()
    build_evidence_index(
        job_id=job_id,
        project_id=project_id,
        slides_data=slides_data,
        db_session=db,
        minio_client=minio,
        ppt_artifact_ids_by_slide=None,
    )
    ids_run2 = get_evidence_ids()

    db.close()

    if ids_run1 == ids_run2:
        print("evidence_id stable across reruns: OK")
        print(f"  Run 1: {len(ids_run1)} evidence_ids")
        print(f"  Run 2: {len(ids_run2)} evidence_ids (identical set)")
        sys.exit(0)
    else:
        print("evidence_id stable across reruns: MISMATCH")
        only1 = set(ids_run1) - set(ids_run2)
        only2 = set(ids_run2) - set(ids_run1)
        if only1:
            print(f"  Only in run 1: {len(only1)} ids")
        if only2:
            print(f"  Only in run 2: {len(only2)} ids")
        sys.exit(1)


if __name__ == "__main__":
    main()
