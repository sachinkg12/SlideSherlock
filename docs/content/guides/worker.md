---
id: worker
title: Running the Worker
sidebar_position: 3
---

# Running the Worker

The RQ worker dequeues jobs from Redis and executes the full `render_stage` pipeline.

---

## Starting the Worker

```bash
make worker
```

Internally runs:

```bash
cd apps/worker && \
  NO_PROXY='*' \
  OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
  PYTHONPATH=$(pwd)/../..:$(pwd)/..:/path/to/packages/core:$PYTHONPATH \
  ../../venv/bin/python worker.py
```

The two environment variables (`NO_PROXY`, `OBJC_DISABLE_INITIALIZE_FORK_SAFETY`) prevent macOS fork-safety crashes when RQ forks a work-horse process. They are set automatically by the Makefile.

---

## Worker Output

When idle:
```
Worker rq:worker:host.1234 started, version 1.16.x
Listening on jobs...
```

When processing a job:
```
jobs: apps.api.worker.render_stage('550e8400-...') (550e8400-...)
Stage: INGEST — parsing PPTX...
Stage: EVIDENCE — building index...
Stage: GRAPH — native graph (5 nodes, 3 edges)...
Stage: RENDER — LibreOffice PPTX→PDF...
Stage: SCRIPT/en — generating draft...
Stage: VERIFY/en — 12/12 PASS, 0 REWRITE, 0 REMOVE
Stage: AUDIO/en — synthesising 8 slides...
Stage: TIMELINE/en — 22 actions generated...
Stage: OVERLAY/en — rendering slide overlays...
Stage: COMPOSE/en — composing final video...
Job 550e8400-... completed in 87.3s
```

---

## Running Multiple Workers

Each worker processes one job at a time. To increase throughput, start additional worker processes in separate terminals:

```bash
# Terminal 1
make worker

# Terminal 2
make worker

# Terminal 3
make worker
```

All workers share the same Redis queue. RQ automatically distributes jobs across available workers.

:::caution Job isolation
Each worker holds an exclusive lock on its current `job_id`. Multiple workers will not process the same job simultaneously.
:::

---

## Applying a Quality Preset

Set the preset before starting the worker. All jobs processed by this worker will use the preset unless the job's `config_json` overrides it.

```bash
# Draft preset (fast, no vision, no BGM)
SLIDESHERLOCK_PRESET=draft make worker

# Standard preset (notes, crossfade, subtitles)
SLIDESHERLOCK_PRESET=standard make worker

# Pro preset (full vision, BGM, loudness normalisation)
SLIDESHERLOCK_PRESET=pro make worker
```

Export form (for `.env` or shell scripts):

```bash
eval $(PYTHONPATH=$(pwd):$(pwd)/packages/core \
  venv/bin/python scripts/slidesherlock_cli.py preset pro --export)
make worker
```

---

## Worker with Specific Providers

```bash
# Enable OpenAI vision and TTS
OPENAI_API_KEY=sk-... \
VISION_PROVIDER=openai \
SLIDESHERLOCK_PRESET=pro \
make worker
```

---

## Viewing Worker Status

```bash
# Check the queue depth
docker compose exec redis redis-cli LLEN rq:queue:jobs

# List active workers
docker compose exec redis redis-cli SMEMBERS rq:workers

# Inspect a failed job
docker compose exec redis redis-cli LRANGE rq:queue:failed 0 -1
```

---

## Error Handling

When a job fails, the worker:
1. Sets `job.status = FAILED` and writes the traceback to `job.error_message` in PostgreSQL
2. Moves the job to the RQ failed job registry in Redis

To retry a failed job, re-upload the PPTX or re-enqueue via the admin interface.

### Viewing Errors

```bash
# From the API
curl http://localhost:8000/jobs/{job_id}
# {"status": "FAILED", "error_message": "LibreOffice not found. Install: brew install --cask libreoffice"}

# From PostgreSQL directly
docker compose exec postgres psql -U slidesherlock -d slidesherlock \
  -c "SELECT job_id, status, error_message FROM jobs WHERE status='FAILED' ORDER BY updated_at DESC LIMIT 5;"
```
