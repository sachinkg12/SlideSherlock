---
id: api-server
title: Running the API Server
sidebar_position: 2
---

# Running the API Server

The FastAPI server handles job creation, file uploads, status polling, and artifact retrieval.

---

## Starting the Server

```bash
make api
```

Internally runs:

```bash
PYTHONPATH=$(pwd):$PYTHONPATH \
  venv/bin/uvicorn apps.api.main:app \
  --reload \
  --host 0.0.0.0 \
  --port 8000
```

The `--reload` flag enables hot-reload on file changes (development mode only — omit for production).

---

## Verifying the Server

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

Interactive API documentation:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

---

## Custom Port

```bash
PORT=9080 make api
# or
PYTHONPATH=$(pwd) venv/bin/uvicorn apps.api.main:app --host 0.0.0.0 --port 9080
```

---

## Production Mode

For production, remove `--reload` and add worker configuration:

```bash
PYTHONPATH=$(pwd):$PYTHONPATH \
  venv/bin/gunicorn apps.api.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 \
  --bind 0.0.0.0:8000
```

Install gunicorn first:
```bash
venv/bin/pip install gunicorn
```

---

## Environment

The API server reads all configuration from environment variables (see [Environment Variables](../configuration/environment-variables)). Set them in `.env` or export them before running.

At startup, the server:
1. Connects to PostgreSQL and creates any missing tables (`Base.metadata.create_all`)
2. Tests the Redis connection — if Redis is unavailable, the job queue is disabled with a warning
3. Initialises the MinIO client

If any of these fail, the server starts but returns errors on job submission endpoints.
