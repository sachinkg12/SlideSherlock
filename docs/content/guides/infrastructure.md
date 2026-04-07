---
id: infrastructure
title: Infrastructure Services
sidebar_position: 1
---

# Infrastructure Services

SlideSherlock's infrastructure runs in Docker Compose and consists of three required services and one optional service.

---

## Services

| Service | Image | Port(s) | Purpose |
|---|---|---|---|
| `postgres` | `postgres:15` | 5433 | Job metadata, evidence index, entity links |
| `redis` | `redis:7` | 6379 | RQ job queue |
| `minio` | `minio/minio:latest` | 9000 (API), 9001 (console) | Artifact object store |
| `pgadmin` | `dpage/pgadmin4` | 5050 | PostgreSQL web UI (optional) |

---

## Starting and Stopping

```bash
# Start all services (detached)
make up

# Stop all services (preserves data volumes)
make down

# Stop and remove volumes (clean slate)
docker compose down -v
```

---

## Checking Service Health

```bash
make check-ports
```

Expected output when all ports are free:
```
Port 5433 (PostgreSQL):  ✅ Available
Port 6379 (Redis):       ✅ Available
Port 9000 (MinIO API):   ✅ Available
Port 9001 (MinIO Console): ✅ Available
```

Test Redis specifically:
```bash
make test-redis
# Output: PONG
```

---

## PostgreSQL

**Connection string (default):**
```
postgresql://slidesherlock:slidesherlock@localhost:5433/slidesherlock
```

**Credentials:**
- User: `slidesherlock`
- Password: `slidesherlock`
- Database: `slidesherlock`

### Applying Migrations

```bash
make migrate
# Runs: venv/bin/alembic upgrade head
```

### Creating a New Migration

After changing `apps/api/models.py`:

```bash
venv/bin/alembic revision --autogenerate -m "add new table"
venv/bin/alembic upgrade head
```

### Accessing via pgAdmin

Navigate to `http://localhost:5050`:
- Email: `admin@example.com`
- Password: `admin`

Add a server connection:
- Host: `postgres` (Docker internal hostname)
- Port: `5432` (internal Docker port — not 5433)
- Username: `slidesherlock`
- Password: `slidesherlock`

### Direct SQL Access

```bash
# From host machine
docker compose exec postgres psql -U slidesherlock -d slidesherlock

# Useful queries
SELECT job_id, status, created_at FROM jobs ORDER BY created_at DESC LIMIT 10;
SELECT kind, COUNT(*) FROM evidence_items GROUP BY kind;
```

---

## Redis

**Connection:** `redis://localhost:6379/0`

Redis is used exclusively as the RQ job queue backend. Jobs are enqueued by the API and dequeued by the worker.

```bash
# Test connection
make test-redis
# docker compose exec redis redis-cli ping → PONG

# Check queue depth
docker compose exec redis redis-cli LLEN rq:queue:jobs

# Monitor real-time
docker compose exec redis redis-cli MONITOR
```

---

## MinIO

**API endpoint:** `http://localhost:9000`
**Web console:** `http://localhost:9001`
**Credentials:** `minioadmin` / `minioadmin`
**Bucket:** `slidesherlock`

MinIO provides an S3-compatible API. The pipeline client (`packages/core/storage.py`) wraps `boto3` pointed at the MinIO endpoint.

### Web Console

Browse to `http://localhost:9001` to visually inspect artifacts:

```
slidesherlock/
└── jobs/
    └── {job_id}/
        ├── input.pptx
        ├── evidence/index.json
        ├── graphs/unified/slide_001.json
        ├── script/en/script.json
        ├── output/en/final.mp4
        └── ...
```

### CLI Access (mc)

```bash
# Install MinIO client
brew install minio/stable/mc

# Configure alias
mc alias set local http://localhost:9000 minioadmin minioadmin

# List jobs
mc ls local/slidesherlock/jobs/

# Download a specific artifact
mc cp local/slidesherlock/jobs/{job_id}/output/en/final.mp4 ./final.mp4

# Remove a job's artifacts
mc rm --recursive --force local/slidesherlock/jobs/{job_id}/
```

### Verifying Artifacts

```bash
# Check if pipeline produced all expected outputs for a job
curl http://localhost:8000/jobs/{job_id}/artifacts

# Check MinIO health
curl http://localhost:9000/minio/health/live
```

---

## Production Deployment Notes

For production environments, replace the Docker Compose services with managed equivalents:

| Docker Compose | Cloud Equivalent |
|---|---|
| `postgres:15` | Amazon RDS (PostgreSQL 15) |
| `redis:7` | Amazon ElastiCache (Redis) or Upstash |
| `minio` | Amazon S3 (same boto3 interface — just change `MINIO_ENDPOINT`) |

The boto3 client in `storage.py` is already S3-compatible. Switching to S3 only requires updating the three `MINIO_*` environment variables — no code changes needed.
