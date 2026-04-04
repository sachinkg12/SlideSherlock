# SlideSherlock

[![DOI](https://zenodo.org/badge/1200528949.svg)](https://doi.org/10.5281/zenodo.19413323)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Convert any PowerPoint presentation into a narrated explainer video with visual guidance — highlights, traces, and zooms synchronized to the narration.

## Key Features

- **Evidence-Grounded Narration** — Every narrated claim is traceable to specific slide content via stable evidence IDs (SHA-256). No hallucinations.
- **Verifier Loop** — Script segments are verified against the evidence index with PASS/REWRITE/REMOVE verdicts. Ungrounded claims are iteratively rewritten until convergence.
- **Dual-Provenance Graph Fusion** — Structural extraction from PPT XML (shapes, connectors, groups) merged with vision-based extraction (rendered PNG + OCR) into a unified graph with per-node provenance and confidence scores.
- **Quality Presets** — Draft (fast, no vision), Standard (narration + subtitles), Pro (vision AI + background music + loudness normalization).
- **Multi-Language Variants** — Generate videos in multiple languages from a single PPTX. Shared evidence and graphs; only language-dependent stages re-run.

## Quick Start (Docker)

```bash
git clone https://github.com/sachinkg12/SlideSherlock.git
cd SlideSherlock
cp .env.example .env    # Add your OpenAI API key
docker compose up
# API available at http://localhost:8000
```

## Quick Start (Local)

```bash
make setup              # Create venv + install Python deps
make up                 # Start Postgres, Redis, MinIO
make migrate            # Run database migrations
make api                # Start API server (port 8000)
make worker             # Start pipeline worker (separate terminal)
```

**System dependencies** (checked via `make doctor`):
- Python 3.11+
- LibreOffice (PPTX → PDF)
- FFmpeg (video composition)
- Poppler / pdftoppm (PDF → PNG)
- Tesseract (OCR for vision graph)

## Architecture

```
PPTX Upload
    │
    ▼
┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  Ingest  │──▶│ Evidence  │──▶│  Render  │──▶│  Graph   │
│ parse +  │   │ index +   │   │ PDF→PNG  │   │ native+  │
│ extract  │   │ photo/diag│   │          │   │ vision+  │
└─────────┘   └──────────┘   └──────────┘   │ merge    │
                                             └──────────┘
                                                  │
                    ┌─────────────────────────────┘
                    ▼ (per language variant)
              ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
              │  Script   │──▶│  Verify  │──▶│  Audio   │──▶│  Video   │
              │ generate  │   │ PASS/    │   │ TTS +    │   │ timeline │
              │ + context │   │ REWRITE/ │   │ align    │   │ overlay  │
              │           │   │ REMOVE   │   │          │   │ compose  │
              └──────────┘   └──────────┘   └──────────┘   └──────────┘
                                                                 │
                                                                 ▼
                                                            final.mp4
```

Each stage implements a `Stage` protocol and runs independently. The pipeline is open for extension (add a stage) and closed for modification (existing stages untouched).

## Pipeline Stages

| Stage | Key Modules | Output |
|-------|-------------|--------|
| Ingest | `ppt_parser`, `image_extract`, `image_classifier` | `ppt/slide_*.json`, `images/` |
| Evidence | `evidence_index`, `photo_understand`, `diagram_understand` | `evidence/index.json` |
| Render | LibreOffice + pdf2image | `render/deck.pdf`, `render/slides/slide_*.png` |
| Graph | `native_graph`, `vision_graph`, `merge_engine` | `graphs/unified/slide_*.json` |
| Script | `explain_plan`, `script_generator`, `script_context` | `script/{variant}/script.json` |
| Verify | `verifier` (rewrite loop) | `verify_report.json`, `coverage.json` |
| Audio | `audio_prepare`, `tts_provider` | `audio/{variant}/slide_*.wav` |
| Video | `timeline_builder`, `overlay_renderer`, `composer` | `output/{variant}/final.mp4` |

## API

```bash
# Create project
curl -X POST http://localhost:8000/projects -H "Content-Type: application/json" \
  -d '{"name": "My Project"}'

# Create job + upload PPTX (one step)
curl -X POST http://localhost:8000/jobs/quick \
  -F "file=@presentation.pptx" -F "name=My Project"

# Check progress
curl http://localhost:8000/jobs/{job_id}/progress

# Get pipeline metrics
curl http://localhost:8000/jobs/{job_id}/metrics

# View evidence trail (verifier decisions)
curl http://localhost:8000/jobs/{job_id}/evidence-trail
```

## Testing

```bash
make test               # Run all tests
make lint               # black --check + flake8

# Run a single test file
PYTHONPATH=$(pwd):$(pwd)/packages/core venv/bin/pytest packages/core/tests/test_verifier.py -v
```

## Quality Presets

```bash
SLIDESHERLOCK_PRESET=draft make worker      # Fast: no vision, no BGM
SLIDESHERLOCK_PRESET=standard make worker   # Narration + subtitles + crossfade
SLIDESHERLOCK_PRESET=pro make worker        # Vision AI + BGM + loudness normalize
```

## License

MIT
