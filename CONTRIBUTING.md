# Contributing to SlideSherlock

Thank you for your interest in contributing! This guide covers the development setup, coding standards, and PR workflow.

## Development Setup

```bash
# Clone and set up
git clone https://github.com/sachinkg12/SlideSherlock.git
cd SlideSherlock

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start infrastructure (Postgres, Redis, MinIO)
docker compose up -d postgres redis minio

# Run database migrations
alembic upgrade head

# Start API server
PYTHONPATH=.:packages/core uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

# Start worker (separate terminal)
USE_SYSTEM_TTS=true PYTHONPATH=.:packages/core python -m rq worker jobs --url redis://localhost:6379
```

### System Dependencies

These must be installed separately (not pip-installable):

- **Python 3.11+**
- **LibreOffice** — PPTX to PDF conversion
- **FFmpeg** — video composition
- **Poppler** (`pdftoppm`) — PDF to PNG
- **Tesseract** — OCR (optional, for vision pipeline)

Run `slidesherlock doctor` to verify all dependencies.

## Running Tests

```bash
PYTHONPATH=.:packages/core pytest apps/api/tests/ packages/core/tests/ -q
```

All 167 tests must pass before submitting a PR.

## Code Style

- **Formatter:** `black` with `--line-length 100`
- **Linter:** `flake8` with config in `.flake8`
- CI enforces both — PRs that fail lint are blocked.

```bash
black --line-length 100 packages/core/ apps/api/ scripts/
flake8 packages/core/ apps/api/ scripts/
```

## Pull Request Workflow

1. **Branch** from `master`: `git checkout -b feature/my-change`
2. **Make changes** — keep PRs focused (one feature/fix per PR)
3. **Run tests + lint** locally before pushing
4. **Push** and open a PR against `master`
5. CI runs automatically (test + lint + frontend + docker)
6. PR requires 1 approval + all CI checks passing

### Commit Messages

Use imperative mood, present tense:
- `Add CLI --dry-run flag`
- `Fix redis.ping() timeout`
- `Update test count in README`

Reference issue numbers with `Closes #N` or `Fixes #N` in the commit body.

## Architecture Overview

SlideSherlock uses the **Open/Closed Principle** throughout:

- **Pipeline stages** — `packages/core/stages/*.py` implement the `Stage` protocol. Adding a stage = one new file + one list entry in `pipeline.py`.
- **Provider registries** — LLM, vision, TTS, translator, and storage providers are dict-based registries. Adding a provider = one `register_*()` call.
- **Database initializers** — SQLite and PostgreSQL are both supported via `register_db_initializer()`.

See the architecture diagram in `README.md` for the full pipeline flow.

## Labels

| Label | Use for |
|-------|---------|
| `bug` | Something broken |
| `enhancement` | New feature or improvement |
| `documentation` | Docs, README, guides |
| `good first issue` | Simple, well-scoped tasks for newcomers |
