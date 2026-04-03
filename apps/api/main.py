from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from sqlalchemy.orm import Session
import json
import redis
from rq import Queue
from datetime import datetime
import uuid
import hashlib
import sys
import os

try:
    from .database import SessionLocal, engine, Base
    from .models import Project, Job, Artifact
    from .schemas import (
        ProjectCreate,
        ProjectResponse,
        JobCreate,
        JobResponse,
        JobStatus,
    )
except ImportError:
    # Fallback for when running as script
    from apps.api.database import SessionLocal, engine, Base
    from apps.api.models import Project, Job, Artifact
    from apps.api.schemas import (
        ProjectCreate,
        ProjectResponse,
        JobCreate,
        JobResponse,
        JobStatus,
    )

# Add packages/core to path for MinIO client
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "core")
)
try:
    from storage import MinIOClient  # noqa: E402
except ImportError:
    MinIOClient = None

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="SlideSherlock API", version="1.0.0")

# Redis connection for RQ
# Note: RQ works better with decode_responses=False for binary serialization
try:
    redis_conn = redis.Redis(host="localhost", port=6379, db=0, decode_responses=False)
    redis_conn.ping()  # Test connection
    job_queue = Queue("jobs", connection=redis_conn)
except redis.ConnectionError:
    print("Warning: Redis not available. Job queue disabled.")
    job_queue = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/projects", response_model=ProjectResponse)
async def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project"""
    db_project = Project(
        project_id=str(uuid.uuid4()),
        name=project.name,
        description=project.description,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return ProjectResponse.model_validate(db_project)


@app.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: Session = Depends(get_db)):
    """Get a project by ID"""
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse.model_validate(project)


@app.post("/jobs", response_model=JobResponse)
async def create_job(job: JobCreate, db: Session = Depends(get_db)):
    """Create a new job"""
    # Verify project exists
    project = db.query(Project).filter(Project.project_id == job.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    job_id = str(uuid.uuid4())
    config_json = None
    if getattr(job, "config", None) is not None:
        config_json = json.dumps(job.config) if isinstance(job.config, dict) else str(job.config)
    db_job = Job(
        job_id=job_id,
        project_id=job.project_id,
        status=JobStatus.QUEUED,  # Start as QUEUED, will move to RUNNING when PPTX is uploaded
        input_file_path=None,
        requested_language=job.requested_language,
        config_json=config_json,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(db_job)
    db.commit()
    db.refresh(db_job)

    # Don't enqueue process_job here - wait for PPTX upload
    # The upload endpoint will queue the render stage

    return _job_to_response(db_job, None)


def _job_to_response(job: Job, minio_client=None) -> JobResponse:
    """Convert Job to JobResponse, optionally fetching output_variants and variant_statuses from manifest."""
    data = {
        "job_id": job.job_id,
        "project_id": job.project_id,
        "status": job.status,
        "input_file_path": job.input_file_path,
        "requested_language": getattr(job, "requested_language", None),
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
    output_variants = None
    variant_statuses = None
    if minio_client:
        try:
            manifest_data = minio_client.get(f"jobs/{job.job_id}/render/manifest.json")
            manifest = json.loads(manifest_data.decode("utf-8"))
            output_variants = manifest.get("output_variants")
            if output_variants:
                variant_statuses = []
                for v in output_variants:
                    vid = v.get("id", "en")
                    final_path = f"jobs/{job.job_id}/output/{vid}/final.mp4"
                    exists = minio_client.exists(final_path)
                    variant_statuses.append({
                        "variant_id": vid,
                        "status": "ready" if exists else "pending",
                        "output_url": f"/jobs/{job.job_id}/output/{vid}/final.mp4" if exists else None,
                    })
            else:
                legacy_path = f"jobs/{job.job_id}/output/final.mp4"
                if minio_client.exists(legacy_path):
                    output_variants = [{"id": "en", "lang": "en-US", "voice_id": "default_en", "notes_translate": False}]
                    variant_statuses = [{"variant_id": "en", "status": "ready", "output_url": f"jobs/{job.job_id}/output/final.mp4"}]
        except Exception:
            pass
    data["output_variants"] = output_variants
    data["variant_statuses"] = variant_statuses
    return JobResponse(**data)


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get a job by ID"""
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    minio_client = MinIOClient() if MinIOClient else None
    return _job_to_response(job, minio_client)


@app.post("/jobs/{job_id}/upload_pptx")
async def upload_pptx(
    job_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload PPTX file for a job"""
    # Verify job exists
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(
            status_code=400, detail="File must be a PPTX file (.pptx extension)"
        )

    # Read file content
    file_content = await file.read()
    file_size = len(file_content)

    # Calculate SHA256 hash
    sha256_hash = hashlib.sha256(file_content).hexdigest()

    # Store file in MinIO at jobs/{job_id}/input/deck.pptx
    storage_path = f"jobs/{job_id}/input/deck.pptx"
    if not MinIOClient:
        raise HTTPException(status_code=500, detail="MinIO client not available")

    try:
        minio_client = MinIOClient()
        minio_client.put(
            storage_path,
            file_content,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to upload file to storage: {str(e)}"
        )

    # Create artifact record
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        project_id=job.project_id,
        job_id=job_id,
        artifact_type="pptx",
        storage_path=storage_path,
        sha256=sha256_hash,
        size_bytes=str(file_size),
        metadata_json=(
            '{"filename": "' + file.filename + '", "content_type": '
            '"application/vnd.openxmlformats-officedocument.presentationml.presentation"}'
        ),
        created_at=datetime.utcnow(),
    )
    db.add(artifact)

    # Update job status: QUEUED -> RUNNING
    if job.status == JobStatus.QUEUED or job.status == JobStatus.PENDING:
        job.status = JobStatus.RUNNING
    job.input_file_path = storage_path
    job.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    db.refresh(artifact)

    # Queue render stage in Redis
    if job_queue:
        try:
            from .worker import render_stage
        except ImportError:
            from apps.api.worker import render_stage
        job_queue.enqueue(render_stage, job_id)
    else:
        print(
            f"Warning: Render stage not enqueued for job {job_id} (Redis unavailable)"
        )

    return {
        "job_id": job_id,
        "artifact_id": artifact.artifact_id,
        "storage_path": storage_path,
        "sha256": sha256_hash,
        "size_bytes": file_size,
        "status": job.status.value,
    }


@app.get("/jobs/{job_id}/progress")
async def get_job_progress(job_id: str, db: Session = Depends(get_db)):
    """Return stage-level progress for a job (which stages completed, current stage, percentage)."""
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    minio_client = MinIOClient() if MinIOClient else None
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not available")

    # Try to read metrics.json (written at end of pipeline)
    metrics = None
    try:
        metrics_data = minio_client.get(f"jobs/{job_id}/metrics.json")
        metrics = json.loads(metrics_data.decode("utf-8"))
    except Exception:
        pass

    # Determine which stages have completed by checking known artifacts
    stage_checks = {
        "ingest": f"jobs/{job_id}/ppt/slide_001.json",
        "evidence": f"jobs/{job_id}/evidence/index.json",
        "render": f"jobs/{job_id}/render/manifest.json",
        "graph": f"jobs/{job_id}/graphs/unified/flags.json",
    }
    completed_stages = []
    for stage_name, check_path in stage_checks.items():
        try:
            if minio_client.exists(check_path):
                completed_stages.append(stage_name)
        except Exception:
            pass

    # Check per-variant stages
    try:
        manifest_data = minio_client.get(f"jobs/{job_id}/render/manifest.json")
        manifest = json.loads(manifest_data.decode("utf-8"))
        for v in manifest.get("output_variants", []):
            vid = v.get("id", "en")
            variant_checks = {
                f"script_{vid}": f"jobs/{job_id}/script/{vid}/script.json",
                f"verify_{vid}": f"jobs/{job_id}/script/{vid}/verify_report.json",
                f"audio_{vid}": f"jobs/{job_id}/script/{vid}/narration_per_slide.json",
                f"video_{vid}": f"jobs/{job_id}/output/{vid}/final.mp4",
            }
            for stage_name, check_path in variant_checks.items():
                try:
                    if minio_client.exists(check_path):
                        completed_stages.append(stage_name)
                except Exception:
                    pass
    except Exception:
        pass

    total_stages = len(stage_checks) + 4  # 4 per-variant stages (approximate)
    pct = int(100 * len(completed_stages) / total_stages) if total_stages else 0

    current_stage = None
    if job.status.value == "PROCESSING":
        # The current stage is the first one not in completed_stages
        all_ordered = list(stage_checks.keys())
        for s in all_ordered:
            if s not in completed_stages:
                current_stage = s
                break

    return {
        "job_id": job_id,
        "status": job.status.value,
        "completed_stages": completed_stages,
        "current_stage": current_stage,
        "percentage": min(pct, 100),
        "metrics": metrics,
    }


@app.get("/jobs/{job_id}/metrics")
async def get_job_metrics(job_id: str, db: Session = Depends(get_db)):
    """Return metrics.json content for a job."""
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    minio_client = MinIOClient() if MinIOClient else None
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not available")

    try:
        metrics_data = minio_client.get(f"jobs/{job_id}/metrics.json")
        return json.loads(metrics_data.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=404, detail="Metrics not available yet")


@app.get("/jobs/{job_id}/evidence-trail")
async def get_evidence_trail(job_id: str, limit: int = 50, db: Session = Depends(get_db)):
    """Return last N verifier decisions from verify_report.json."""
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    minio_client = MinIOClient() if MinIOClient else None
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not available")

    decisions = []
    # Try all variant verify reports
    try:
        manifest_data = minio_client.get(f"jobs/{job_id}/render/manifest.json")
        manifest = json.loads(manifest_data.decode("utf-8"))
        for v in manifest.get("output_variants", []):
            vid = v.get("id", "en")
            try:
                report_data = minio_client.get(f"jobs/{job_id}/script/{vid}/verify_report.json")
                report = json.loads(report_data.decode("utf-8"))
                for d in report.get("decisions", []):
                    d["variant_id"] = vid
                    decisions.append(d)
            except Exception:
                pass
    except Exception:
        pass

    # Return last N
    return {
        "job_id": job_id,
        "decisions": decisions[-limit:],
        "total": len(decisions),
    }


@app.post("/jobs/quick")
async def quick_create_job(
    name: str = "Quick Project",
    file: UploadFile = File(...),
    requested_language: str = None,
    db: Session = Depends(get_db),
):
    """Combined create project + job + upload in one call."""
    # 1. Create project
    db_project = Project(
        project_id=str(uuid.uuid4()),
        name=name,
        description="Created via /jobs/quick",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)

    # 2. Create job
    job_id = str(uuid.uuid4())
    db_job = Job(
        job_id=job_id,
        project_id=db_project.project_id,
        status=JobStatus.QUEUED,
        input_file_path=None,
        requested_language=requested_language,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(db_job)
    db.commit()

    # 3. Upload PPTX
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(
            status_code=400, detail="File must be a PPTX file (.pptx extension)"
        )

    file_content = await file.read()
    file_size = len(file_content)
    sha256_hash = hashlib.sha256(file_content).hexdigest()

    storage_path = f"jobs/{job_id}/input/deck.pptx"
    if not MinIOClient:
        raise HTTPException(status_code=500, detail="MinIO client not available")

    try:
        minio_client = MinIOClient()
        minio_client.put(
            storage_path,
            file_content,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to upload file to storage: {str(e)}"
        )

    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        project_id=db_project.project_id,
        job_id=job_id,
        artifact_type="pptx",
        storage_path=storage_path,
        sha256=sha256_hash,
        size_bytes=str(file_size),
        metadata_json=(
            '{"filename": "' + file.filename + '", "content_type": '
            '"application/vnd.openxmlformats-officedocument.presentationml.presentation"}'
        ),
        created_at=datetime.utcnow(),
    )
    db.add(artifact)

    db_job.status = JobStatus.RUNNING
    db_job.input_file_path = storage_path
    db_job.updated_at = datetime.utcnow()
    db.commit()

    # Queue render stage
    if job_queue:
        try:
            from .worker import render_stage
        except ImportError:
            from apps.api.worker import render_stage
        job_queue.enqueue(render_stage, job_id)

    return {
        "project_id": db_project.project_id,
        "job_id": job_id,
        "status": db_job.status.value,
        "storage_path": storage_path,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
