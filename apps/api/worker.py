"""Worker: thin wrapper that delegates to the pipeline orchestrator."""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Job, JobStatus, Artifact
from datetime import datetime
import time
import sys
import os
import uuid
import json

# Add packages/core to path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "core")
)
from storage import MinIOClient  # noqa: E402


def process_job(job_id: str):
    """Process a job - dummy implementation that marks it as DONE and uploads to MinIO"""
    db: Session = SessionLocal()
    job = None
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            print(f"Job {job_id} not found")
            return

        # Update status to PROCESSING
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.utcnow()
        db.commit()

        # Simulate some work
        print(f"Processing job {job_id}...")
        time.sleep(2)  # Dummy work

        # Upload dummy artifact to MinIO
        try:
            minio_client = MinIOClient()
            artifact_data = f"Dummy artifact for job {job_id}".encode("utf-8")
            storage_path = f"jobs/{job_id}/artifact.txt"
            minio_client.put(storage_path, artifact_data, "text/plain")
            print(f"Uploaded artifact to MinIO: {storage_path}")

            # Create artifact record
            artifact = Artifact(
                artifact_id=str(uuid.uuid4()),
                project_id=job.project_id,
                job_id=job_id,
                artifact_type="dummy",
                storage_path=storage_path,
                metadata='{"type": "dummy"}',
                created_at=datetime.utcnow(),
            )
            db.add(artifact)
        except Exception as e:
            print(f"Warning: Failed to upload to MinIO: {e}")

        # Update status to DONE
        job.status = JobStatus.DONE
        job.updated_at = datetime.utcnow()
        db.commit()

        print(f"Job {job_id} completed successfully")
    except Exception as e:
        print(f"Error processing job {job_id}: {e}")
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def render_stage(job_id: str):
    """Render stage: delegates to the pipeline orchestrator."""
    from pipeline import run_pipeline
    run_pipeline(job_id)
