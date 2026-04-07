---
id: common-issues
title: Common Issues
sidebar_position: 1
---

# Troubleshooting Common Issues

This page covers the most frequently encountered problems and their solutions.

---

## Infrastructure

### Docker services fail to start

**Symptom:** `make up` exits with errors; containers are not healthy.

```bash
# Check which containers failed
docker compose ps

# View logs for a specific service
docker compose logs postgres
docker compose logs redis
docker compose logs minio
```

**Common causes:**

| Error | Solution |
|---|---|
| Port already in use (5432, 6379, 9000, 9001) | Stop the conflicting process or change the port in `docker-compose.yml` |
| Docker daemon not running | Start Docker Desktop |
| Insufficient disk space | Free at least 5 GB of disk space |
| Existing volume conflict | `docker compose down -v` to reset all volumes (⚠ destroys data) |

---

### Port conflicts

**Symptom:** `Bind for 0.0.0.0:5432 failed: port is already allocated`

```bash
# Find the process using the port (macOS/Linux)
lsof -i :5432

# Kill it (replace PID)
kill -9 <PID>

# Or change the mapped port in docker-compose.yml
# ports:
#   - "5433:5432"   ← host port changed to 5433
```

---

### Redis connection refused

**Symptom:** Worker starts but immediately exits with `ConnectionRefusedError: [Errno 111] Connection refused`

```bash
# Verify Redis is running
docker compose ps redis

# Test connectivity
docker compose exec redis redis-cli ping
# Expected: PONG

# Check REDIS_URL in .env
grep REDIS_URL .env
# Should be: REDIS_URL=redis://localhost:6379/0
```

---

### MinIO bucket not found

**Symptom:** API or worker logs show `NoSuchBucket: The specified bucket does not exist`

```bash
# Run setup to create the bucket
make setup

# Or manually create via mc CLI
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/slidesherlock

# Verify
mc ls local/
```

---

## Installation

### Python virtual environment not found

**Symptom:** `make api` fails with `venv/bin/python: No such file or directory`

```bash
# Create the virtual environment
python3.12 -m venv venv

# Install all dependencies
pip install -r apps/api/requirements.txt
pip install -r packages/core/requirements.txt
```

---

### `make doctor` reports missing tools

**Symptom:** One or more tools show `✗ not found`

```bash
# LibreOffice (macOS)
brew install --cask libreoffice

# Poppler (macOS)
brew install poppler

# FFmpeg (macOS)
brew install ffmpeg

# Tesseract OCR (optional, for vision pipeline)
brew install tesseract

# Verify after installing
make doctor
```

**Expected passing output:**

```
✓ LibreOffice found: /Applications/LibreOffice.app
✓ pdfinfo found: /opt/homebrew/bin/pdfinfo
✓ pdftoppm found: /opt/homebrew/bin/pdftoppm
✓ ffmpeg found: /opt/homebrew/bin/ffmpeg
✓ PostgreSQL reachable
✓ Redis reachable
✓ MinIO reachable
```

---

### Database migration fails

**Symptom:** `make migrate` shows `relation "jobs" already exists` or `Target database is not up to date`

```bash
# Check current migration state
docker compose exec postgres psql -U slidesherlock -d slidesherlock \
  -c "SELECT version_num FROM alembic_version;"

# Re-run migrations (safe to run multiple times)
PYTHONPATH=$(pwd) venv/bin/alembic -c apps/api/alembic.ini upgrade head

# If schema is corrupted, reset (⚠ destroys all data)
docker compose exec postgres psql -U slidesherlock -d slidesherlock \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
make migrate
```

---

## Worker

### macOS fork-safety crash

**Symptom:** Worker crashes immediately with `objc[XXXX]: +[__NSCFConstantString initialize] may have been in progress in another thread when fork() was called`

**Solution:** Always start the worker with the required macOS flags. Use `make worker` — it sets these automatically:

```bash
NO_PROXY='*' \
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
make worker
```

Never start the worker directly with `python worker.py` on macOS without these flags.

---

### Job stuck in PROCESSING

**Symptom:** `GET /jobs/{job_id}` returns `status: PROCESSING` for more than 10 minutes.

```bash
# Step 1: Check worker terminal for the last logged stage
# The worker will print the stage it's currently executing.

# Step 2: Query PostgreSQL for error details
docker compose exec postgres psql -U slidesherlock -d slidesherlock \
  -c "SELECT status, stage, error_message FROM jobs WHERE job_id='$JOB_ID';"

# Step 3: Check Redis for failed jobs
docker compose exec redis redis-cli LRANGE rq:queue:failed 0 -1
```

Common causes:

| Stage stuck on | Likely cause |
|---|---|
| `RENDER` | LibreOffice not found or crashed |
| `AUDIO` | TTS not configured (`USE_SYSTEM_TTS` not set) |
| `SCRIPT` | LLM provider misconfigured or API key invalid |
| `COMPOSE` | FFmpeg missing or input PNG frames corrupt |

---

### Worker exits with `rq.timeouts.JobTimeoutException`

**Symptom:** Large presentations (>30 slides) fail with timeout.

```bash
# Increase the job timeout in apps/worker/worker.py
# Change: DEFAULT_JOB_TIMEOUT = 600
# To:     DEFAULT_JOB_TIMEOUT = 1800
```

---

## Pipeline Stages

### LibreOffice render failure

**Symptom:** Stage `RENDER` fails; worker logs `LibreOffice conversion returned non-zero exit code`

```bash
# Test conversion manually
/Applications/LibreOffice.app/Contents/MacOS/soffice \
  --headless --convert-to pdf test.pptx --outdir /tmp/
ls -la /tmp/test.pdf

# Check for LibreOffice lock files left from a crash
rm -f ~/.config/libreoffice/4/user/registrymodifications.xcu.lock

# Verify headless mode works
/Applications/LibreOffice.app/Contents/MacOS/soffice --headless --version
```

---

### Missing slide PNG frames

**Symptom:** `render/slides/` directory is empty or has fewer files than expected.

```bash
# Verify pdftoppm is installed and working
pdftoppm -r 150 /tmp/test.pdf /tmp/slide

# Check output
ls /tmp/slide*.png
```

Ensure `poppler` is installed and `pdftoppm` is on your `PATH`:

```bash
which pdftoppm
# Should output: /opt/homebrew/bin/pdftoppm
```

---

### TTS / Audio errors

**Symptom:** Stage `AUDIO` fails or produces silent audio files.

```bash
# Check TTS configuration
echo $USE_SYSTEM_TTS    # 'true' for macOS say / espeak
echo $OPENAI_API_KEY    # Required for OpenAI TTS

# Test system TTS manually (macOS)
say "Hello world" -o /tmp/test.aiff
ffmpeg -i /tmp/test.aiff /tmp/test.wav

# Test espeak (Linux)
espeak "Hello world" --stdout > /tmp/test.wav
```

If using OpenAI TTS:

```bash
# Verify key is valid
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])"
```

---

### Vision provider errors

**Symptom:** Stage `EVIDENCE` fails or image evidence shows `SLIDE_CAPTION` for every image (no `PHOTO` or `DIAGRAM` claims).

```bash
# Check vision configuration
echo $VISION_PROVIDER   # 'stub' (default), 'openai', or 'tesseract'
echo $OPENAI_API_KEY    # Required when VISION_PROVIDER=openai

# With stub provider, all images get fallback SLIDE_CAPTION — this is expected behaviour
# To enable full vision analysis:
export VISION_PROVIDER=openai
export OPENAI_API_KEY=sk-...
make worker
```

---

### Script generation produces empty segments

**Symptom:** `script.json` has 0 segments, or the verifier removes all segments (`remove > 0`).

```bash
# Check LLM provider
echo $LLM_PROVIDER      # 'stub' (default) or 'openai'
echo $OPENAI_API_KEY    # Required for real LLM

# Inspect verify report
curl -s "http://localhost:8000/jobs/$JOB_ID/artifacts/verify_report" | \
  python3 -c "import sys,json; r=json.load(sys.stdin); print(r)"
```

With the stub LLM provider, script generation returns deterministic test output — not real narration. Use `LLM_PROVIDER=openai` with a valid API key for production use.

---

### FFmpeg composition failure

**Symptom:** Stage `COMPOSE` fails with `ffmpeg: command not found` or `No such file or directory`

```bash
# Verify FFmpeg is installed
which ffmpeg
ffmpeg -version

# macOS install
brew install ffmpeg

# Verify it handles H.264
ffmpeg -codecs | grep h264
```

---

## API Server

### API server won't start — port 8000 in use

```bash
# Find and kill the process on port 8000
lsof -i :8000
kill -9 <PID>

# Or start on a different port
PORT=8080 make api
```

---

### `422 Unprocessable Entity` on job creation

**Symptom:** `POST /jobs` returns 422 with validation errors.

The most common cause is passing `requested_language` as an empty string instead of omitting it:

```bash
# Wrong — empty string fails BCP-47 validation
curl -X POST http://localhost:8000/jobs \
  -d '{"project_id": "...", "name": "test", "requested_language": ""}'

# Correct — omit the field entirely for English-only
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"project_id": "...", "name": "test"}'
```

---

### Artifact returns 404 after job is DONE

**Symptom:** `GET /jobs/{job_id}/artifacts/final_video` returns 404 even though the job status is `DONE`.

```bash
# List all available artifacts
curl "http://localhost:8000/jobs/$JOB_ID/artifacts"

# Check MinIO directly
mc ls local/slidesherlock/jobs/$JOB_ID/

# Verify the variant ID
# Default is 'en' — use ?variant=en explicitly if needed
curl "http://localhost:8000/jobs/$JOB_ID/artifacts/final_video?variant=en"
```

---

## Getting More Help

```bash
# Full worker log with timestamps
make worker 2>&1 | tee worker.log

# Full API log
make api 2>&1 | tee api.log

# Database state
docker compose exec postgres psql -U slidesherlock -d slidesherlock \
  -c "SELECT job_id, status, stage, error_message, updated_at FROM jobs ORDER BY updated_at DESC LIMIT 10;"

# MinIO artifact inventory for a job
mc ls --recursive local/slidesherlock/jobs/$JOB_ID/
```

If the issue is not listed here, check the worker terminal output — it prints the stage name and exception traceback before marking the job as `FAILED`.
