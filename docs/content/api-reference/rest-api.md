---
id: rest-api
title: REST API Reference
sidebar_position: 1
---

# REST API Reference

Base URL: `http://localhost:8000`

Interactive documentation: [`/docs`](http://localhost:8000/docs) (Swagger UI) · [`/redoc`](http://localhost:8000/redoc) (ReDoc)

---

## Health

### `GET /health`

Check server health.

**Response `200`**
```json
{"status": "ok"}
```

---

## Projects

### `POST /projects`

Create a new project.

**Request body**
```json
{
  "name": "string (required)",
  "description": "string (optional)"
}
```

**Response `200`**
```json
{
  "project_id": "uuid",
  "name": "string",
  "description": "string | null",
  "created_at": "ISO-8601 datetime",
  "updated_at": "ISO-8601 datetime"
}
```

---

### `GET /projects/{project_id}`

Get a project by ID.

**Path parameters**

| Parameter | Type | Description |
|---|---|---|
| `project_id` | UUID | Project identifier |

**Response `200`** — same schema as `POST /projects`

**Response `404`**
```json
{"detail": "Project not found"}
```

---

## Jobs

### `POST /jobs`

Create a new job within a project.

**Request body**
```json
{
  "project_id": "uuid (required)",
  "name": "string (required)",
  "requested_language": "BCP-47 string (optional, e.g. 'hi-IN', 'es-ES')",
  "config_json": {
    "preset": "draft | standard | pro (optional)",
    "vision": {
      "enabled": true,
      "force_kind_by_slide": {
        "3": "DIAGRAM",
        "5": "PHOTO"
      },
      "min_confidence_for_specific_claims": 0.65
    }
  }
}
```

**Response `200`**
```json
{
  "job_id": "uuid",
  "project_id": "uuid",
  "status": "PENDING",
  "name": "string",
  "requested_language": "string | null",
  "created_at": "ISO-8601 datetime",
  "updated_at": "ISO-8601 datetime"
}
```

---

### `POST /jobs/quick`

**Recommended one-step submission.** Creates a project, creates a job, uploads the PPTX, and enqueues the pipeline in a single call.

**Request** — `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file | ✓ | `.pptx` file |
| `name` | string | ✗ | Job name (defaults to filename) |
| `preset` | string | ✗ | `draft` / `standard` / `pro` (default: `draft`) |

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `ai_narration` | boolean | `false` | When `true`, enables the GPT-4o-mini narration rewrite (NarrateStage). Requires `OPENAI_API_KEY` and `LLM_PROVIDER=openai` on the worker. The flag is persisted to `job.config_json.ai_narration` and read by the pipeline. |
| `requested_language` | string | _(none)_ | BCP-47 code for an additional language variant |

**Example**

```bash
curl -X POST "http://localhost:8000/jobs/quick?ai_narration=true" \
  -F "file=@deck.pptx" \
  -F "preset=pro" \
  -F "name=Architecture overview"
```

**Response `200`**
```json
{
  "project_id": "uuid",
  "job_id": "uuid",
  "status": "QUEUED",
  "config_json": {"preset": "pro", "ai_narration": true}
}
```

---

### `POST /jobs/{job_id}/upload_pptx`

Upload a PPTX file and start processing. This call transitions the job from `PENDING` to `QUEUED` and enqueues the render pipeline.

**Path parameters**

| Parameter | Type | Description |
|---|---|---|
| `job_id` | UUID | Job identifier |

**Request** — `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `file` | file | `.pptx` file (required) |

**Response `200`**
```json
{
  "job_id": "uuid",
  "status": "QUEUED",
  "message": "File uploaded. Job queued for processing.",
  "input_file_path": "jobs/{job_id}/input.pptx"
}
```

**Response `400`**
```json
{"detail": "File must be a .pptx file"}
```

**Response `404`**
```json
{"detail": "Job not found"}
```

---

### `GET /jobs/{job_id}`

Get job status and output variant information.

**Path parameters**

| Parameter | Type | Description |
|---|---|---|
| `job_id` | UUID | Job identifier |

**Response `200`**
```json
{
  "job_id": "uuid",
  "project_id": "uuid",
  "name": "string",
  "status": "PENDING | QUEUED | RUNNING | PROCESSING | DONE | FAILED",
  "stage": "INGEST | EVIDENCE | GRAPH | RENDER | SCRIPT | VERIFY | AUDIO | TIMELINE | OVERLAY | COMPOSE | null",
  "requested_language": "string | null",
  "output_variants": [
    {
      "variant_id": "en",
      "language": "en-US",
      "status": "DONE",
      "final_video_url": "/jobs/{job_id}/artifacts/final_video?variant=en",
      "srt_url": "/jobs/{job_id}/artifacts/subtitles?variant=en"
    }
  ],
  "error_message": "string | null",
  "created_at": "ISO-8601 datetime",
  "updated_at": "ISO-8601 datetime",
  "duration_seconds": 107.3
}
```

**Job Status Values**

| Status | Description |
|---|---|
| `PENDING` | Job created, awaiting PPTX upload |
| `QUEUED` | PPTX uploaded, waiting for a worker |
| `RUNNING` | Worker has picked up the job |
| `PROCESSING` | Pipeline is actively running |
| `DONE` | All stages completed successfully |
| `FAILED` | An error occurred; check `error_message` |

---

### `GET /projects/{project_id}/jobs`

List all jobs in a project.

**Response `200`**
```json
[
  {
    "job_id": "uuid",
    "name": "string",
    "status": "string",
    "created_at": "ISO-8601 datetime"
  }
]
```

---

## Artifacts

### `GET /jobs/{job_id}/artifacts`

List all artifacts produced by a job.

**Response `200`**
```json
[
  {
    "artifact_id": "uuid",
    "artifact_type": "final_video",
    "storage_path": "jobs/{job_id}/output/en/final.mp4",
    "size_bytes": 45678901,
    "sha256": "abc123...",
    "created_at": "ISO-8601 datetime"
  }
]
```

**Artifact Types**

| Type | Description |
|---|---|
| `pptx` | Uploaded input PPTX |
| `pdf` | LibreOffice-rendered PDF |
| `png` | Per-slide PNG frames |
| `evidence` | `evidence/index.json` |
| `native_graph` | `graphs/native/slide_N.json` |
| `unified_graph` | `graphs/unified/slide_N.json` |
| `script_draft` | `script/{variant}/script.json` (before verification) |
| `script_verified` | `script/{variant}/script.json` (after verification) |
| `verify_report` | `verify_report.json` |
| `coverage` | `coverage.json` |
| `narration` | `script/{variant}/narration_per_slide.json` |
| `audio` | `audio/{variant}/slide_N.wav` |
| `timeline` | `timeline/{variant}/timeline.json` |
| `overlay_mp4` | `overlays/{variant}/slide_N_overlay.mp4` |
| `final_video` | `output/{variant}/final.mp4` |
| `subtitles` | `output/{variant}/final.srt` |
| `metrics` | `metrics.json` |

---

### `GET /jobs/{job_id}/artifacts/{artifact_type}`

Download or get the URL for a specific artifact.

**Path parameters**

| Parameter | Type | Description |
|---|---|---|
| `job_id` | UUID | Job identifier |
| `artifact_type` | string | One of the artifact types above |

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `variant` | string | `en` | Output variant ID |

**Response `200`** — file stream for binary artifacts (video, audio, PDF) or JSON for structured artifacts

**Examples**

```bash
# Download final video
curl "http://localhost:8000/jobs/{job_id}/artifacts/final_video" -o final.mp4

# Get verified script JSON
curl "http://localhost:8000/jobs/{job_id}/artifacts/script_verified"

# Get verifier coverage report
curl "http://localhost:8000/jobs/{job_id}/artifacts/coverage"

# Get evidence index
curl "http://localhost:8000/jobs/{job_id}/artifacts/evidence"

# Get l2 (second language) video
curl "http://localhost:8000/jobs/{job_id}/artifacts/final_video?variant=l2" -o final_l2.mp4
```

---

## Output Streaming

### `GET /jobs/{job_id}/output/{variant}/final.mp4`

Stream the final video for a given variant. **Supports HTTP `Range` requests** so the browser HTML5 `<video>` element (and the React `VideoPlayer` in the web UI) can seek to arbitrary timestamps without downloading the whole file.

**Path parameters**

| Parameter | Type | Description |
|---|---|---|
| `job_id` | UUID | Job identifier |
| `variant` | string | Output variant (`en`, `l2`, …) |

**Headers**

| Request header | Behaviour |
|---|---|
| `Range: bytes=START-END` | Server returns `206 Partial Content` with the requested byte range and `Accept-Ranges: bytes` |
| _(no Range)_ | Server returns `200 OK` with the full file and `Content-Length` |

**Response codes**

| Code | Meaning |
|---|---|
| `200` | Full file (no Range header) |
| `206` | Partial content (Range request) |
| `404` | Variant or video not yet produced |

**Example**

```bash
# Full download
curl "http://localhost:8000/jobs/{job_id}/output/en/final.mp4" -o final.mp4

# Range request (first MB)
curl -H "Range: bytes=0-1048575" \
  "http://localhost:8000/jobs/{job_id}/output/en/final.mp4" -o head.mp4
```

The web UI's `<VideoPlayer />` uses this endpoint as its `<video src>` so that scrubbing the seek bar works without buffering the full file.

---

### `GET /jobs/{job_id}/output/{path}`

Generic streaming endpoint for **any artifact** under `jobs/{job_id}/output/` in MinIO. Used by the web UI to download per-variant subtitles, metrics, and intermediate JSON artifacts on demand.

**Path parameters**

| Parameter | Type | Description |
|---|---|---|
| `job_id` | UUID | Job identifier |
| `path` | string | Path under `jobs/{job_id}/output/` (e.g. `en/final.srt`, `en/metrics.json`) |

**Examples**

```bash
# SRT subtitles
curl "http://localhost:8000/jobs/{job_id}/output/en/final.srt"

# Per-variant metrics
curl "http://localhost:8000/jobs/{job_id}/output/en/metrics.json"

# l2 (Hindi) variant final video
curl "http://localhost:8000/jobs/{job_id}/output/l2/final.mp4" -o final_hi.mp4
```

The Content-Type is inferred from the file extension. Binary artifacts are streamed; JSON is returned as `application/json`.

---

## Error Responses

All endpoints return standard error responses:

```json
{
  "detail": "Human-readable error message"
}
```

| HTTP Status | Meaning |
|---|---|
| `400` | Bad request (invalid file type, missing field) |
| `404` | Resource not found (job, project, or artifact) |
| `422` | Validation error (malformed request body) |
| `500` | Internal server error |
