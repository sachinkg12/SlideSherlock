from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Request
from fastapi.responses import StreamingResponse, Response
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
    from .database import SessionLocal, init_db
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
    from apps.api.database import SessionLocal, init_db
    from apps.api.models import Project, Job, Artifact
    from apps.api.schemas import (
        ProjectCreate,
        ProjectResponse,
        JobCreate,
        JobResponse,
        JobStatus,
    )

# Add packages/core to path for MinIO client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "core"))
try:
    from storage import MinIOClient  # noqa: E402
except ImportError:
    MinIOClient = None

# Initialize database schema (dialect-aware via OCP registry).
# - sqlite: create_all() (no alembic support)
# - postgresql: no-op (alembic owns the schema)
init_db()

app = FastAPI(title="SlideSherlock API", version="1.0.0")

# Redis connection for RQ
# Note: RQ works better with decode_responses=False for binary serialization
try:
    redis_conn = redis.Redis(
        host="localhost",
        port=6379,
        db=0,
        decode_responses=False,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    redis_conn.ping()
    job_queue = Queue("jobs", connection=redis_conn)
except (redis.ConnectionError, redis.TimeoutError, OSError):
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
                    variant_statuses.append(
                        {
                            "variant_id": vid,
                            "status": "ready" if exists else "pending",
                            "output_url": f"/jobs/{job.job_id}/output/{vid}/final.mp4"
                            if exists
                            else None,
                        }
                    )
            else:
                legacy_path = f"jobs/{job.job_id}/output/final.mp4"
                if minio_client.exists(legacy_path):
                    output_variants = [
                        {
                            "id": "en",
                            "lang": "en-US",
                            "voice_id": "default_en",
                            "notes_translate": False,
                        }
                    ]
                    variant_statuses = [
                        {
                            "variant_id": "en",
                            "status": "ready",
                            "output_url": f"jobs/{job.job_id}/output/final.mp4",
                        }
                    ]
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
        raise HTTPException(status_code=400, detail="File must be a PPTX file (.pptx extension)")

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
        raise HTTPException(status_code=500, detail=f"Failed to upload file to storage: {str(e)}")

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
        job_queue.enqueue(render_stage, job_id, job_timeout=1800)
    else:
        print(f"Warning: Render stage not enqueued for job {job_id} (Redis unavailable)")

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
    try:
        metrics_data = minio_client.get(f"jobs/{job_id}/metrics.json")
        json.loads(metrics_data.decode("utf-8"))
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
                f"narrate_{vid}": f"jobs/{job_id}/script/{vid}/ai_narration.json",
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

    # Build ordered stage list matching the UI's STAGE_REGISTRY
    all_stage_names = [
        "ingest",
        "evidence",
        "render",
        "graph",
        "script",
        "verify",
        "translate",
        "narrate",
        "audio",
        "video",
    ]

    # Normalise completed_stages: strip variant suffix (e.g. "script_en" → "script")
    completed_base = set()
    for cs in completed_stages:
        base = cs.split("_")[0] if "_" in cs else cs
        completed_base.add(base)

    # Determine current stage
    current_stage = None
    if job.status.value == "PROCESSING":
        for s in all_stage_names:
            if s not in completed_base:
                current_stage = s
                break

    # Build per-stage status objects
    stages = []
    for name in all_stage_names:
        if name in completed_base:
            status = "done"
        elif name == current_stage:
            status = "running"
        elif job.status.value == "FAILED" and name == current_stage:
            status = "failed"
        else:
            status = "pending"
        stages.append(
            {
                "name": name,
                "status": status,
                "started_at": None,
                "finished_at": None,
                "duration_s": None,
                "detail": None,
                "metrics": None,
            }
        )

    total_stages = len(all_stage_names)
    pct = int(100 * len(completed_base) / total_stages) if total_stages else 0

    # Map job status to UI status
    status_map = {
        "QUEUED": "queued",
        "PROCESSING": "running",
        "DONE": "done",
        "FAILED": "failed",
    }
    ui_status = status_map.get(job.status.value, "running")

    # If video stage is done, the job is done regardless of DB status
    if "video" in completed_base:
        ui_status = "done"
        pct = 100

    return {
        "job_id": job_id,
        "status": ui_status,
        "filename": (job.input_file_path or "").split("/")[-1]
        if job.input_file_path
        else "Presentation",
        "preset": "standard",
        "percent": min(pct, 100),
        "stages": stages,
        "error": job.error_message,
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
        raw = json.loads(metrics_data.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=404, detail="Metrics not available yet")

    # Transform raw pipeline metrics to UI-friendly shape
    stages = raw.get("stages", {})
    slide_count = stages.get("ingest", {}).get("metrics", {}).get("slide_count", 0)
    graph_count = stages.get("graph", {}).get("metrics", {}).get("unified_graph_count", 0)
    total_duration_s = raw.get("pipeline_duration_ms", 0) / 1000.0

    # Read verify report for pass/rewrite/remove counts
    verify_stats = {"pass": 0, "rewrite": 0, "remove": 0, "iterations": 0}
    try:
        manifest_data = minio_client.get(f"jobs/{job_id}/render/manifest.json")
        manifest = json.loads(manifest_data.decode("utf-8"))
        for v in manifest.get("output_variants", []):
            vid = v.get("id", "en")
            try:
                report_data = minio_client.get(f"jobs/{job_id}/script/{vid}/verify_report.json")
                report = json.loads(report_data.decode("utf-8"))
                for d in report.get("decisions", []):
                    verdict = d.get("verdict", "").upper()
                    if verdict == "PASS":
                        verify_stats["pass"] += 1
                    elif verdict == "REWRITE":
                        verify_stats["rewrite"] += 1
                    elif verdict == "REMOVE":
                        verify_stats["remove"] += 1
                verify_stats["iterations"] = report.get("iterations", 1)
            except Exception:
                pass
    except Exception:
        pass

    total_claims = verify_stats["pass"] + verify_stats["rewrite"] + verify_stats["remove"]
    pass_rate = verify_stats["pass"] / total_claims if total_claims > 0 else 1.0
    coverage = 1.0 if total_claims > 0 else 0.0

    return {
        "evidence_coverage": coverage,
        "verification_pass_rate": pass_rate,
        "verifier_iterations": verify_stats["iterations"],
        "claims_pass": verify_stats["pass"],
        "claims_rewrite": verify_stats["rewrite"],
        "claims_remove": verify_stats["remove"],
        "graph_nodes": graph_count,
        "dual_provenance_pct": 0.0,
        "total_duration_s": total_duration_s,
        "slide_count": slide_count,
    }


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


@app.get("/jobs/{job_id}/output/{variant_id}/final.mp4")
async def get_video(job_id: str, variant_id: str, request: Request, download: int = 0):
    """Stream the final video from MinIO with Range request support for seeking."""
    minio_client = MinIOClient() if MinIOClient else None
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not available")

    object_path = f"jobs/{job_id}/output/{variant_id}/final.mp4"
    try:
        data = minio_client.get(object_path)
    except Exception:
        raise HTTPException(status_code=404, detail="Video not found")

    total = len(data)
    range_header = request.headers.get("range")

    if range_header:
        # Parse Range: bytes=start-end
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else total - 1
        end = min(end, total - 1)
        chunk = data[start : end + 1]
        return Response(
            content=chunk,
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(chunk)),
            },
        )

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(total),
    }
    if download:
        headers["Content-Disposition"] = f'attachment; filename="slidesherlock_{job_id[:8]}.mp4"'
    return Response(content=data, media_type="video/mp4", headers=headers)


@app.get("/jobs/{job_id}/evidence-report")
async def get_evidence_report(job_id: str):
    """Generate and serve a self-contained HTML evidence trail report."""
    minio_client = MinIOClient() if MinIOClient else None
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not available")
    try:
        ei = json.loads(minio_client.get(f"jobs/{job_id}/evidence/index.json").decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=404, detail="Evidence index not found")
    # Find coverage + verify report (try multiple paths for variant)
    cov = {}
    vr = {}
    for prefix in [f"jobs/{job_id}/script/en/", f"jobs/{job_id}/script/"]:
        try:
            cov = json.loads(minio_client.get(f"{prefix}coverage.json").decode("utf-8"))
            vr = json.loads(minio_client.get(f"{prefix}verify_report.json").decode("utf-8"))
            break
        except Exception:
            continue
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "core"))
        from evidence_report import generate_evidence_report

        html = generate_evidence_report(ei, cov, vr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="evidence_report_{job_id[:8]}.html"',
        },
    )


@app.get("/jobs/{job_id}/output/{variant_id}/subtitles.vtt")
async def get_subtitles_vtt(job_id: str, variant_id: str):
    """Serve subtitles as WebVTT (converted from .srt) for HTML5 <track> element."""
    minio_client = MinIOClient() if MinIOClient else None
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not available")
    srt_path = f"jobs/{job_id}/output/{variant_id}/final.srt"
    try:
        srt_data = minio_client.get(srt_path).decode("utf-8")
    except Exception:
        raise HTTPException(status_code=404, detail="Subtitles not found")
    # Convert SRT → WebVTT (add header, replace comma with dot in timestamps)
    vtt_lines = ["WEBVTT", ""]
    for line in srt_data.strip().split("\n"):
        vtt_lines.append(line.replace(",", ".") if "-->" in line else line)
    vtt_content = "\n".join(vtt_lines)
    return Response(
        content=vtt_content,
        media_type="text/vtt",
        headers={"Content-Type": "text/vtt; charset=utf-8"},
    )


@app.get("/jobs/{job_id}/output/{file_path:path}")
async def get_artifact(job_id: str, file_path: str):
    """Stream any output artifact from MinIO."""
    minio_client = MinIOClient() if MinIOClient else None
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not available")

    object_path = f"jobs/{job_id}/output/{file_path}"
    try:
        data = minio_client.get(object_path)
        content_type = "application/octet-stream"
        if file_path.endswith(".json"):
            content_type = "application/json"
        elif file_path.endswith(".mp4"):
            content_type = "video/mp4"
        return StreamingResponse(
            iter([data]),
            media_type=content_type,
            headers={"Content-Length": str(len(data))},
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Artifact not found")


@app.post("/jobs/quick")
async def quick_create_job(
    name: str = "Quick Project",
    file: UploadFile = File(...),
    requested_language: str = None,
    ai_narration: bool = False,
    preset: str = "draft",
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
        raise HTTPException(status_code=400, detail="File must be a PPTX file (.pptx extension)")

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
        raise HTTPException(status_code=500, detail=f"Failed to upload file to storage: {str(e)}")

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

    # Store preset + AI narration preference in job config_json (read by pipeline)
    config = {"preset": preset}
    if ai_narration:
        config["llm_provider"] = "openai"
    db_job.config_json = json.dumps(config)
    db.commit()

    # Queue render stage
    if job_queue:
        try:
            from .worker import render_stage
        except ImportError:
            from apps.api.worker import render_stage
        job_queue.enqueue(render_stage, job_id, job_timeout=1800)

    return {
        "project_id": db_project.project_id,
        "job_id": job_id,
        "status": db_job.status.value,
        "storage_path": storage_path,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
