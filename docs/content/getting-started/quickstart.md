---
id: quickstart
title: Quick Start
sidebar_position: 3
---

# Quick Start

This guide gets you from zero to a narrated video in under 10 minutes, assuming [prerequisites](prerequisites) are installed and the [installation](installation) steps are complete.

---

## 1 — Start the infrastructure

```bash
make up
```

Wait for Docker Compose to report all services healthy (approx 10–15 seconds).

---

## 2 — Start the API server

Open a terminal and run:

```bash
make api
```

The FastAPI server starts on **port 8000** with hot-reload enabled:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Application startup complete.
```

Verify it is healthy:

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

---

## 3 — Start the worker

Open a second terminal and run:

```bash
make worker
```

The RQ worker starts listening on the `jobs` queue:

```
Starting RQ worker...
Worker rq:worker:... started, version 1.16.x
Listening on jobs...
```

:::tip macOS note
`make worker` automatically sets `NO_PROXY=*` and `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` to prevent fork-safety crashes on macOS. These are set internally by the Makefile — no manual action needed.
:::

---

## 4 — Submit your first job

### Option A — Using the demo script

```bash
make demo
```

This runs `scripts/run_demo.py` against `sample_connectors.pptx` and writes the output to `output/demo/final.mp4`.

### Option B — Using the REST API directly

**Step 1:** Create a project:

```bash
PROJECT=$(curl -s -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "My First Project"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['project_id'])")
echo "Project: $PROJECT"
```

**Step 2:** Create a job:

```bash
JOB=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d "{\"project_id\": \"$PROJECT\", \"name\": \"My First Video\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "Job: $JOB"
```

**Step 3:** Upload the PPTX:

```bash
curl -X POST "http://localhost:8000/jobs/$JOB/upload_pptx" \
  -F "file=@/path/to/your/slides.pptx"
```

The job status moves to `RUNNING` and the worker immediately begins processing.

---

## 5 — Monitor progress

```bash
curl http://localhost:8000/jobs/$JOB
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PROCESSING",
  "stage": "SCRIPT_GENERATION",
  "created_at": "2024-01-15T10:23:00Z",
  "updated_at": "2024-01-15T10:23:42Z"
}
```

Poll until `status` is `DONE`:

```bash
# Simple polling loop (bash)
while true; do
  STATUS=$(curl -s http://localhost:8000/jobs/$JOB | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "Status: $STATUS"
  [ "$STATUS" = "DONE" ] && break
  [ "$STATUS" = "FAILED" ] && echo "Job failed" && break
  sleep 5
done
```

---

## 6 — Download the video

```bash
# Get the artifact URLs
curl http://localhost:8000/jobs/$JOB/artifacts

# Download the final video (en variant)
curl "http://localhost:8000/jobs/$JOB/artifacts/final_video" -o final.mp4
```

Or retrieve directly from MinIO at `http://localhost:9001` (credentials: `minioadmin` / `minioadmin`) under `slidesherlock/jobs/{job_id}/output/en/final.mp4`.

---

## Pipeline Duration

Typical processing times on a standard developer laptop:

| Stage | Approximate Duration |
|---|---|
| PPTX parsing + image extraction | 2–5 s |
| Evidence index build | 1–3 s |
| Native graph construction | 1–2 s |
| LibreOffice PPTX → PDF | 5–15 s |
| Poppler PDF → PNG | 2–5 s |
| Script generation (stub LLM) | < 1 s |
| Verification loop | < 1 s |
| Audio (system TTS, 10 slides) | 15–30 s |
| Overlay rendering (FFmpeg) | 10–30 s |
| Final composition | 5–20 s |

Total with stubs: **~60–120 seconds** for a 10-slide presentation.
With OpenAI API: add ~5–15 s per slide for vision + LLM calls (cached on rerun).

---

## What to Do Next

- **Change quality**: set `SLIDESHERLOCK_PRESET=standard make worker` for subtitles and crossfades
- **Enable real AI**: add `OPENAI_API_KEY` and `VISION_PROVIDER=openai` to `.env`
- **Request a second language**: add `requested_language=hi-IN` when creating the job
- **Run the test suite**: `make test`
