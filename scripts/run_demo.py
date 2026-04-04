#!/usr/bin/env python3
"""
End-to-end demo: run full pipeline on sample PPTX and produce final.mp4.
Requires: make up, make migrate; Postgres, Redis, MinIO running.
Usage: from repo root, PYTHONPATH=. python scripts/run_demo.py
       or: make demo (after make up make migrate)
"""
import os
import sys

# Add repo root, apps, and packages/core to path (storage.MinIOClient lives in packages/core)
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, "apps", "api"))
core_path = os.path.join(repo_root, "packages", "core")
if core_path not in sys.path:
    sys.path.insert(0, core_path)


def main():
    from apps.api.database import SessionLocal
    from apps.api.models import Project, Job
    from apps.api.worker import render_stage

    # MinIOClient from packages/core/storage.py (core_path must be on sys.path)
    try:
        from storage import MinIOClient
    except ImportError as e:
        print(
            f"ERROR: Could not import MinIOClient from storage. Ensure PYTHONPATH includes {core_path}"
        )
        print(f"  Run: PYTHONPATH={repo_root}:{core_path} python scripts/run_demo.py")
        raise SystemExit(1) from e

    sample_pptx = os.path.join(repo_root, "sample_connectors.pptx")
    if not os.path.exists(sample_pptx):
        create_script = os.path.join(repo_root, "scripts", "create_sample_connectors_ppt.py")
        if os.path.exists(create_script):
            import subprocess

            subprocess.run(
                [sys.executable, create_script, "--output", sample_pptx],
                check=True,
                cwd=repo_root,
                env={**os.environ, "PYTHONPATH": repo_root},
            )
        if not os.path.exists(sample_pptx):
            print(
                "ERROR: sample_connectors.pptx not found. Create with: PYTHONPATH=. python scripts/create_sample_connectors_ppt.py --output sample_connectors.pptx"
            )
            sys.exit(1)

    db = SessionLocal()
    try:
        project = Project(name="Demo Project", description="End-to-end demo")
        db.add(project)
        db.flush()
        job = Job(project_id=project.project_id, status="QUEUED")
        db.add(job)
        db.flush()
        job_id = job.job_id
        input_path = f"jobs/{job_id}/input/deck.pptx"
        job.input_file_path = input_path
        db.commit()
    finally:
        db.close()

    minio_client = MinIOClient()
    with open(sample_pptx, "rb") as f:
        minio_client.put(
            input_path,
            f.read(),
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    print(f"Created job {job_id}, uploaded PPTX to {input_path}")

    print(
        "Running render stage (PPT parse, evidence, graph, script, verifier, timeline, overlay, compose)..."
    )
    render_stage(job_id)

    out_dir = os.path.join(repo_root, "output", "demo")
    os.makedirs(out_dir, exist_ok=True)
    final_local = os.path.join(out_dir, "final.mp4")
    for final_storage in [f"jobs/{job_id}/output/en/final.mp4", f"jobs/{job_id}/output/final.mp4"]:
        try:
            data = minio_client.get(final_storage)
            with open(final_local, "wb") as f:
                f.write(data)
            print(f"Saved final.mp4 to {final_local}")
            break
        except Exception:
            continue
    else:
        print("Warning: could not download final.mp4")
        print(f"  Check MinIO at jobs/{job_id}/output/")


if __name__ == "__main__":
    main()
