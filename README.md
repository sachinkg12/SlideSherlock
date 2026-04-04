# SlideSherlock

[![CI](https://github.com/sachinkg12/SlideSherlock/actions/workflows/ci.yml/badge.svg)](https://github.com/sachinkg12/SlideSherlock/actions/workflows/ci.yml)
[![DOI](https://zenodo.org/badge/1200528949.svg)](https://doi.org/10.5281/zenodo.19413323)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**SlideSherlock** is an evidence-grounded pipeline that converts PowerPoint presentations into narrated explainer videos. Every narrated claim is traceable to specific slide content — no hallucinations, no invented facts.

## Why SlideSherlock?

Existing slide-to-video tools either read bullet points verbatim or hallucinate content that doesn't exist in the source material. SlideSherlock solves this with three novel mechanisms:

1. **Evidence Index** — Every piece of PPTX content (text, shapes, images, connectors) receives a stable, content-addressable evidence ID (`SHA-256(job|slide|kind|offset)`). All downstream narration must cite these IDs.

2. **Verifier Loop** — A closed-loop control system: generate script &rarr; verify against evidence (PASS / REWRITE / REMOVE) &rarr; regenerate &rarr; re-verify until convergence. Not post-hoc filtering — inline verification with iterative correction.

3. **Dual-Provenance Knowledge Graph** — Two independent graphs are built per slide: **G_native** from PPT XML (shapes, connectors, groups) and **G_vision** from rendered PNGs + OCR. These merge into **G_unified** where each node carries provenance (NATIVE / VISION / BOTH), confidence scores, and `needs_review` flags.

## Features

| Feature | Description |
|---------|-------------|
| **10-Stage Pipeline** | Ingest &rarr; Evidence &rarr; Render &rarr; Graph &rarr; Script &rarr; Verify &rarr; Translate &rarr; Narrate &rarr; Audio &rarr; Video |
| **AI Narration** | Optional GPT-4o rewrite: evidence-grounded template &rarr; natural presenter delivery (two-pass, hallucination-free) |
| **Quality Presets** | Draft (fast), Standard (subtitles + crossfade), Pro (vision AI + BGM + loudness normalization) |
| **Multi-Language** | Generate variants from one PPTX. Shared evidence and graphs; only language-dependent stages re-run |
| **Web UI** | React dashboard with real-time stage progress, live evidence trail, inline video player |
| **CLI** | `slidesherlock run deck.pptx --preset pro` with structured JSON logging for experiments |
| **Docker** | `docker compose up` &mdash; one command for the full stack |
| **152 Tests** | Automated test suite covering evidence grounding, verification, graph fusion, and pipeline stages |

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/sachinkg12/SlideSherlock.git
cd SlideSherlock
cp .env.example .env       # Add your OPENAI_API_KEY (optional; stub used otherwise)
docker compose up           # Starts API, worker, Postgres, Redis, MinIO, pgAdmin
```

- **API**: http://localhost:8000
- **Web UI**: http://localhost:3000 (if running `pnpm dev` in `apps/web/`)

### Local Development

```bash
make setup                  # Create venv + install deps
make up                     # Start Postgres, Redis, MinIO (Docker)
make migrate                # Run database migrations
make api                    # Start FastAPI server (port 8000)
make worker                 # Start pipeline worker (separate terminal)
```

### CLI (no Redis/RQ needed)

```bash
slidesherlock run deck.pptx                          # Draft preset, output to ./output/
slidesherlock run deck.pptx --preset pro -o results/  # Pro preset, custom output
slidesherlock doctor                                   # Check system dependencies
```

Each CLI run produces `final.mp4`, `metrics.json`, and `run_log.json` (structured log for experiment aggregation).

## Architecture

```
PPTX
 │
 ▼
┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  Ingest  │──▶│ Evidence  │──▶│  Render  │──▶│  Graph   │   Shared stages
│ parse    │   │ index     │   │ PDF→PNG  │   │ native + │   (run once)
│ extract  │   │ photo/diag│   │          │   │ vision + │
└─────────┘   └──────────┘   └──────────┘   │ merge    │
                                             └────┬─────┘
                                                  │
                    ┌─────────────────────────────┘
                    ▼  (per language variant)
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│  Script  │─▶│  Verify  │─▶│Translate │─▶│ Narrate  │─▶│  Audio   │─▶│  Video   │
│ generate │  │ PASS/    │  │ (l2 only)│  │ AI rewrite│  │ TTS +   │  │ timeline │
│ + context│  │ REWRITE/ │  │          │  │ (optional)│  │ align   │  │ compose  │
│          │  │ REMOVE   │  │          │  │          │  │         │  │          │
└──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
                                                                            │
                                                                            ▼
                                                                       final.mp4
```

The pipeline follows the **Open/Closed Principle**: each stage implements a `Stage` protocol. Adding a new stage requires no changes to existing code — just add a class and register it.

```python
class Stage(Protocol):
    name: str
    def run(self, ctx: PipelineContext) -> StageResult: ...
```

## Pipeline Stages

| Stage | Key Modules | Output |
|-------|-------------|--------|
| **Ingest** | `ppt_parser`, `image_extract`, `image_classifier` | `ppt/slide_*.json`, `images/` |
| **Evidence** | `evidence_index`, `photo_understand`, `diagram_understand` | `evidence/index.json` |
| **Render** | LibreOffice + pdf2image | `render/deck.pdf`, `render/slides/*.png` |
| **Graph** | `native_graph`, `vision_graph`, `merge_engine` | `graphs/unified/slide_*.json` |
| **Script** | `explain_plan`, `script_generator`, `script_context` | `script/{variant}/script.json` |
| **Verify** | `verifier` (closed-loop rewrite) | `verify_report.json`, `coverage.json` |
| **Translate** | `translator_provider` (l2 variants only) | Translated script + notes |
| **Narrate** | `narrate` (GPT-4o, optional) | `ai_narration.json` |
| **Audio** | `audio_prepare`, `tts_provider` | `audio/{variant}/slide_*.wav` |
| **Video** | `timeline_builder`, `overlay_renderer`, `composer` | `output/{variant}/final.mp4` |

## No-Hallucination Design

```
         ┌──────────────────────────────────────────────┐
         │            Evidence Index                      │
         │  SHA-256(job|slide|kind|offset) → source_ref  │
         └──────────────────┬───────────────────────────┘
                            │
                            ▼
┌──────────┐    ┌──────────────────┐    ┌───────────┐
│  Script   │───▶│  Verifier Loop   │───▶│  Verified  │
│ Generator │    │                  │    │  Script    │
│           │◀───│ PASS → keep      │    │           │
│ (claims   │    │ REWRITE → regen  │    │ (all claims│
│  cite     │    │ REMOVE → drop    │    │  grounded) │
│  evidence)│    │                  │    │           │
└──────────┘    └──────────────────┘    └───────────┘
                  max 3 iterations
```

Image claims must specifically cite `IMAGE_*` or `DIAGRAM_*` evidence kinds. The verifier enforces this — no generic claims about visual content without supporting vision evidence.

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/jobs/quick` | POST | Upload PPTX + start pipeline (one step) |
| `/jobs/{id}` | GET | Job status |
| `/jobs/{id}/progress` | GET | Per-stage progress for UI polling |
| `/jobs/{id}/metrics` | GET | Pipeline metrics (durations, counts) |
| `/jobs/{id}/evidence-trail` | GET | Live verifier decisions |
| `/jobs/{id}/output/{variant}/final.mp4` | GET | Stream video (HTTP Range support) |
| `/health` | GET | Health check |

## Web UI

React 18 + TypeScript + Vite + Tailwind CSS + Framer Motion.

```bash
cd apps/web && pnpm install && pnpm dev    # http://localhost:3000
```

Three screens:
1. **Upload** — Drag-drop PPTX, preset selector, AI Narration toggle
2. **Progress** — Real-time stage cards, live evidence trail, confetti on completion
3. **Result** — Video player with seeking, pipeline report, download buttons

## Quality Presets

| Preset | Vision | Subtitles | Transitions | BGM | Notes Overlay |
|--------|--------|-----------|-------------|-----|---------------|
| **Draft** | Off | Off | Cut | Off | Off |
| **Standard** | Off | On | Crossfade | Off | On |
| **Pro** | On | On | Crossfade | On (ducked) | On |

AI Narration is orthogonal to presets — toggle it independently to enable GPT-4o natural delivery rewrite.

## Testing

```bash
make test               # 152 tests across core pipeline and API
make lint               # black --check + flake8 (max-line-length=100)
make doctor             # Check LibreOffice, FFmpeg, Poppler, Tesseract
```

## Batch Experiments

Run the pipeline on a corpus of PPTXs for paper data collection:

```bash
python scripts/batch_run.py /path/to/pptx_dir --preset draft --workers 3 --output results/
```

Produces `batch_summary.json` and `batch_summary.csv` (one row per file, stage timings as columns) for direct use in paper tables.

## System Dependencies

Checked via `make doctor`. All bundled in the Docker image.

| Dependency | Purpose | Install |
|------------|---------|---------|
| **LibreOffice** | PPTX &rarr; PDF | `brew install --cask libreoffice` |
| **FFmpeg** | Video composition | `brew install ffmpeg` |
| **Poppler** | PDF &rarr; PNG | `brew install poppler` |
| **Tesseract** | OCR (vision graph) | `brew install tesseract` |

## Citation

If you use SlideSherlock in your research, please cite:

```bibtex
@software{gupta_slidesherlock_2026,
  author    = {Gupta, Sachin},
  title     = {SlideSherlock: Evidence-Grounded Presentation-to-Video Pipeline},
  year      = {2026},
  doi       = {10.5281/zenodo.19413324},
  url       = {https://github.com/sachinkg12/SlideSherlock},
  license   = {Apache-2.0}
}
```

## License

[Apache License 2.0](LICENSE)

Copyright 2026 Sachin Gupta
