---
id: overview
title: Architecture Overview
sidebar_position: 1
---

# Architecture Overview

SlideSherlock is built around a single design principle: **artifact-first, evidence-grounded processing**. Every stage in the pipeline writes its outputs to an object store (MinIO) with stable, deterministic paths, and every narration claim must be traceable to an entry in the evidence index stored in PostgreSQL.

---

## System Context

```mermaid
C4Context
    title System Context — SlideSherlock

    Person(user, "Presenter / Author", "Uploads PPTX, downloads narrated video")

    System_Boundary(ss, "SlideSherlock") {
        System(platform, "SlideSherlock Platform", "Converts PPTX to narrated video\nwith hallucination-free narration")
    }

    System_Ext(openai, "OpenAI API", "GPT-4o vision, LLM, TTS (optional)")
    System_Ext(lo, "LibreOffice", "PPTX to PDF (local subprocess)")
    System_Ext(ff, "FFmpeg + Poppler", "Video encoding + PDF rasterisation")

    Rel(user, platform, "POST /jobs (PPTX upload)\nGET /jobs/{id} (status + video URL)", "HTTPS / REST")
    Rel(platform, openai, "Vision, LLM, TTS calls (when configured)", "HTTPS")
    Rel(platform, lo, "PPTX to PDF conversion", "Local subprocess")
    Rel(platform, ff, "PDF to PNG + video composition", "Local subprocess")
```

---

## Container Architecture

```mermaid
graph TB
    subgraph Client
        C["curl / Web UI"]
    end

    subgraph Docker["Docker Compose Infrastructure"]
        PG["PostgreSQL 15\n:5433\nJob metadata + Evidence DB"]
        RD["Redis 7\n:6379\nRQ Job Queue"]
        MN["MinIO\n:9000 / :9001\nArtifact Object Store"]
    end

    subgraph App["Application (Python 3.12)"]
        API["FastAPI API\n:8000\napps/api/main.py"]
        WK["RQ Worker\napps/worker/worker.py"]
        CORE["Core Pipeline Library\npackages/core/"]
    end

    subgraph External["External Services (optional)"]
        OAI["OpenAI API\nGPT-4o + TTS"]
        LO["LibreOffice\nheadless"]
        FF["FFmpeg + Poppler"]
    end

    C -->|"POST /jobs\nGET /jobs/{id}"| API
    API --> PG
    API --> MN
    API -->|"enqueue render_stage(job_id)"| RD
    RD -->|"dequeue"| WK
    WK -->|"invoke"| CORE
    CORE --> PG
    CORE --> MN
    CORE -->|"vision / LLM / TTS"| OAI
    CORE -->|"PPTX → PDF"| LO
    CORE -->|"PDF → PNG\nvideo compose"| FF
```

---

## Database Schema (Key Tables)

```mermaid
erDiagram
    projects {
        uuid project_id PK
        string name
        timestamp created_at
    }

    jobs {
        uuid job_id PK
        uuid project_id FK
        string status
        string input_file_path
        string requested_language
        json config_json
        string error_message
    }

    artifacts {
        uuid artifact_id PK
        uuid job_id FK
        string artifact_type
        string storage_path
        string sha256
        bigint size_bytes
    }

    slides {
        uuid slide_id PK
        uuid job_id FK
        int slide_index
        string slide_title
    }

    sources {
        uuid source_id PK
        uuid job_id FK
        uuid slide_id FK
        string type
    }

    evidence_items {
        string evidence_id PK
        uuid job_id FK
        uuid slide_id FK
        uuid source_id FK
        string kind
        text content
        float confidence
    }

    source_refs {
        uuid ref_id PK
        string evidence_id FK
        string ref_type
        float bbox_x
        float bbox_y
        float bbox_w
        float bbox_h
        string ppt_shape_id
    }

    projects ||--o{ jobs : "has"
    jobs ||--o{ artifacts : "produces"
    jobs ||--o{ slides : "contains"
    slides ||--o{ sources : "has"
    sources ||--o{ evidence_items : "yields"
    evidence_items ||--o{ source_refs : "referenced by"
```

---

## MinIO Artifact Structure

All pipeline outputs are stored under a single bucket (`slidesherlock`) with the following path convention:

```
jobs/{job_id}/
├── input.pptx                         ← uploaded presentation
├── ppt/
│   └── slide_N.json                   ← parsed slide data (shapes, connectors, notes)
├── images/
│   ├── index.json                     ← image inventory with stable image IDs
│   └── slide_N/img_K.png              ← extracted embedded images
├── vision/
│   ├── image_kinds.json               ← PHOTO / DIAGRAM / CHART classification
│   ├── photo_results.json             ← vision captions for photos
│   └── diagram_N.json                 ← diagram analysis per image
├── evidence/
│   └── index.json                     ← complete evidence index
├── graphs/
│   ├── native/slide_N.json            ← G_native (from PPT shapes)
│   ├── vision/slide_N.json            ← G_vision (from OCR, optional)
│   └── unified/slide_N.json           ← G_unified (merged)
├── render/
│   ├── deck.pdf                       ← LibreOffice output
│   └── slides/slide_N.png             ← 150 DPI PNG frames
├── script/{variant}/
│   ├── explain_plan.json              ← narration plan
│   ├── script.json                    ← verified script
│   ├── script_translated.json         ← translated script (l2 variant)
│   └── narration_per_slide.json       ← per-slide narration text
├── audio/{variant}/
│   └── slide_N.wav                    ← synthesised speech per slide
├── timing/{variant}/
│   ├── alignment.json
│   └── slide_N_duration.json
├── timeline/{variant}/
│   └── timeline.json                  ← HIGHLIGHT / TRACE / ZOOM actions
├── overlays/{variant}/
│   └── slide_N_overlay.mp4            ← annotated slide video
├── output/{variant}/
│   ├── final.mp4                      ← final narrated video
│   └── final.srt                      ← subtitles
├── verify_report.json                 ← verifier verdicts
├── coverage.json                      ← evidence coverage statistics
├── metrics.json
└── summary.json
```

`{variant}` is `en` by default, or any BCP-47 language code when multi-language output is requested.

---

## Orchestration Model

The entire pipeline is **a single Python function**: `render_stage(job_id)` in `apps/api/worker.py`. It runs sequentially, writing each stage's outputs to MinIO before proceeding to the next. This design means:

- **Reproducibility**: Re-running from any point is safe because all intermediate results are persisted with stable paths
- **Debuggability**: You can inspect any intermediate artifact in MinIO without re-running the full pipeline
- **Idempotency**: Evidence IDs and graph node IDs are deterministic hashes — re-running on the same input produces the same IDs

The worker process is a standard [RQ](https://python-rq.org/) worker — it pulls `job_id` values off a Redis queue and executes `render_stage`.
