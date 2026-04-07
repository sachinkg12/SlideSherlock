---
id: e2e-tests
title: End-to-End Testing
sidebar_position: 2
---

# End-to-End Testing

End-to-end tests verify that the complete pipeline — from PPTX upload to final video — works correctly with all infrastructure services running.

---

## Prerequisites

Before running E2E tests, ensure:

```bash
# 1. Infrastructure is running
make up

# 2. Migrations applied
make migrate

# 3. API server running (terminal 1)
make api

# 4. Worker running (terminal 2)
make worker
```

---

## Using the Demo Script

The fastest E2E test uses the included sample presentation:

```bash
make demo
```

This runs `scripts/run_demo.py` which:
1. Creates a project and job
2. Uploads `sample_connectors.pptx`
3. Polls until the job is `DONE`
4. Downloads `output/demo/final.mp4`
5. Prints a summary of stages completed and artifact sizes

Expected output:
```
Running end-to-end demo...
Project created: demo-project-uuid
Job created: 550e8400-...
PPTX uploaded. Job queued.
[10:00:05] RUNNING
[10:00:08] PROCESSING - INGEST
[10:00:12] PROCESSING - EVIDENCE
[10:00:14] PROCESSING - GRAPH
[10:00:16] PROCESSING - RENDER
[10:00:25] PROCESSING - SCRIPT/en
[10:00:26] PROCESSING - VERIFY/en
[10:00:27] PROCESSING - AUDIO/en
[10:00:42] PROCESSING - TIMELINE/en
[10:00:43] PROCESSING - OVERLAY/en
[10:01:08] PROCESSING - COMPOSE/en
[10:01:15] DONE

✅ final.mp4 saved to output/demo/final.mp4 (18.4 MB, 00:02:34)
✅ Evidence: 47 items (22 TEXT_SPAN, 12 DIAGRAM_ENTITIES, 8 IMAGE_CAPTION, 5 SLIDE_CAPTION)
✅ Script: 28 segments (28 PASS, 0 REWRITE, 0 REMOVE)
✅ Timeline: 22 actions (14 HIGHLIGHT, 5 TRACE, 3 ZOOM)
```

---

## Shell-Based API Tests

Two shell scripts test specific API scenarios:

### `test_api.sh` — Basic API test

```bash
./test_api.sh
```

Tests:
- `GET /health`
- `POST /projects`
- `POST /jobs`
- `POST /jobs/{id}/upload_pptx` with `test.pptx`
- `GET /jobs/{id}` polling until `DONE`
- `GET /jobs/{id}/artifacts/final_video` — asserts 200 and non-empty file

### `test_api_connectors.sh` — Connector-heavy test

```bash
./test_api_connectors.sh
```

Tests the pipeline specifically with `sample_connectors.pptx`, which contains:
- Multiple diagrams with shape connectors
- Group shapes (clusters)
- Embedded images classified as DIAGRAM

Verifies that:
- Native graph has at least 5 nodes and 3 edges
- Unified graph has at least 3 TRACE actions in the timeline
- All DIAGRAM claims cite DIAGRAM_* evidence (no hallucination)

### `test_render.sh` — Render stage test

```bash
./test_render.sh
```

Verifies the LibreOffice + Poppler rendering stage specifically:
- `render/deck.pdf` exists and is non-empty
- `render/slides/slide_001.png` exists and is > 50KB
- PNG dimensions match expected slide aspect ratio

---

## Checking MinIO Artifacts

After a job completes, verify all expected artifacts are present:

```bash
JOB_ID="550e8400-..."

# Required artifacts for a complete run
ARTIFACTS=(
  "jobs/$JOB_ID/input.pptx"
  "jobs/$JOB_ID/evidence/index.json"
  "jobs/$JOB_ID/graphs/unified/slide_001.json"
  "jobs/$JOB_ID/script/en/script.json"
  "jobs/$JOB_ID/verify_report.json"
  "jobs/$JOB_ID/output/en/final.mp4"
)

for path in "${ARTIFACTS[@]}"; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:9000/slidesherlock/$path")
  if [ "$STATUS" = "200" ]; then
    echo "✅ $path"
  else
    echo "❌ $path (HTTP $STATUS)"
  fi
done
```

---

## Verifying No Hallucination

Check the verifier report to confirm all segments are grounded:

```bash
curl -s "http://localhost:8000/jobs/$JOB_ID/artifacts/verify_report" | python3 -c "
import sys, json
report = json.load(sys.stdin)
total = report['total_segments']
passn = report['pass']
rewrite = report['rewrite']
remove = report['remove']
print(f'Total segments: {total}')
print(f'  PASS:    {passn} ({passn/total*100:.1f}%)')
print(f'  REWRITE: {rewrite}')
print(f'  REMOVE:  {remove}')
if remove > 0:
    print('WARNING: Some segments were removed — check verify_report for reason codes')
"
```

---

## Minimum Acceptance Criteria

A passing E2E run should satisfy:

| Check | Expected |
|---|---|
| Job status | `DONE` |
| `final.mp4` exists | ✓ |
| `final.mp4` size | > 1 MB |
| Evidence items | > 0 |
| Script segments | > 0 |
| Verifier PASS rate | > 90% |
| No `IMAGE_UNGROUNDED` verdicts | ✓ (critical) |
| Timeline actions | > 0 |

---

## Diagnosing Failures

### Job stuck in PROCESSING

```bash
# Check worker logs
# The worker terminal will show the last stage attempted

# Check PostgreSQL for error
docker compose exec postgres psql -U slidesherlock -d slidesherlock \
  -c "SELECT status, error_message FROM jobs WHERE job_id='$JOB_ID';"
```

### LibreOffice render failure

```bash
# Verify LibreOffice is accessible
make doctor

# Test conversion manually
/Applications/LibreOffice.app/Contents/MacOS/soffice \
  --headless --convert-to pdf test.pptx --outdir /tmp/
ls /tmp/test.pdf
```

### Missing audio files

```bash
# Check if TTS is configured
echo $USE_SYSTEM_TTS    # Should be 'true' for offline TTS
echo $OPENAI_API_KEY    # Or set this for OpenAI TTS

# Check audio artifacts in MinIO
mc ls local/slidesherlock/jobs/$JOB_ID/audio/en/
```
