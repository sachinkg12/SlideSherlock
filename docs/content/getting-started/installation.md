---
id: installation
title: Installation
sidebar_position: 2
---

# Installation

All commands are run from the **repository root** (the directory containing `Makefile` and `docker-compose.yml`).

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/sachinkg12/SlideSherlock.git
cd SlideSherlock
```

---

## Step 2 — Start infrastructure services

SlideSherlock requires three services running via Docker Compose:

- **PostgreSQL 15** — job metadata, evidence index, entity links
- **Redis 7** — RQ job queue
- **MinIO** — S3-compatible object store for all pipeline artifacts

```bash
make up
```

Expected output:
```
Starting docker-compose services...
✅ postgres is healthy
✅ redis is healthy
✅ minio is ready
Services started.
  MinIO console: http://localhost:9001
  pgAdmin:       http://localhost:5050
```

:::tip Verify ports are free
```bash
make check-ports
```
If any port is already in use, stop the conflicting process before running `make up`.
:::

---

## Step 3 — Create the Python virtual environment

```bash
make setup
```

This command:
1. Detects the best available Python version (prefers 3.12, falls back to 3.11)
2. Creates a `venv/` directory at the project root
3. Upgrades `pip`
4. Installs all Python dependencies from `requirements.txt`

```bash
# Equivalent manual steps
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

:::info Virtual environment location
The Makefile commands automatically use `venv/bin/python` and `venv/bin/pip`. You do **not** need to activate the venv manually to use `make` commands.
:::

---

## Step 4 — Configure secrets

Copy the example environment file and fill in any optional API keys:

```bash
cp .env.example .env
```

Edit `.env` — only the values you need:

```bash
# Infrastructure (pre-filled defaults work with docker-compose)
DATABASE_URL=postgresql://slidesherlock:slidesherlock@localhost:5433/slidesherlock
REDIS_URL=redis://localhost:6379/0
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=slidesherlock

# Optional — AI providers (leave blank to use stubs)
OPENAI_API_KEY=sk-...
VISION_PROVIDER=openai

# Optional — TTS
USE_SYSTEM_TTS=true          # macOS offline TTS
```

:::caution .env is git-ignored
The `.env` file is listed in `.gitignore`. Never commit API keys to version control.
:::

---

## Step 5 — Run database migrations

```bash
make migrate
```

This runs `alembic upgrade head`, applying all migrations in `alembic/versions/` to create the schema:

- `projects`, `jobs`, `artifacts`
- `slides`, `sources`, `evidence_items`, `source_refs`
- `claim_links`, `entity_links`

---

## Step 6 — Verify the setup

```bash
# Check system dependencies
make doctor

# Check ports
make check-ports

# Test Redis connection
make test-redis
```

If `make doctor` reports all green, you are ready to start the API server and worker.

---

## Updating Dependencies

To update Python packages after pulling changes:

```bash
make install
```

This is equivalent to `pip install -r requirements.txt` inside the virtualenv — it updates existing packages and installs any newly added ones.

---

## Cleaning Up

To remove build artefacts and the virtual environment:

```bash
make clean
```

:::warning
`make clean` deletes the entire `venv/` directory. You will need to run `make setup` again afterwards.
:::

To stop Docker services without removing data volumes:

```bash
make down
```
