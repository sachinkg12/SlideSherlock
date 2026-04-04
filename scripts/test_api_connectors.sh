#!/bin/bash
# Test SlideSherlock API with sample_connectors.pptx (shapes + connectors for G_native edges).
# Ensures ppt/slide_*.json has connectors and graphs/native/slide_*.json has non-empty edges.

set -e

API_URL="http://localhost:8000"
SAMPLE_PPTX="sample_connectors.pptx"

echo "=== Testing SlideSherlock API (connectors sample) ==="
echo ""

# Ensure sample_connectors.pptx exists; create if missing
if [ ! -f "$SAMPLE_PPTX" ]; then
  echo "0. Generating $SAMPLE_PPTX (shapes + connectors)..."
  PYTHONPATH=. \
    python3 scripts/create_sample_connectors_ppt.py --output "$SAMPLE_PPTX" 2>/dev/null || \
    PYTHONPATH=. venv/bin/python scripts/create_sample_connectors_ppt.py --output "$SAMPLE_PPTX" 2>/dev/null || true
  if [ ! -f "$SAMPLE_PPTX" ]; then
    echo "   $SAMPLE_PPTX not found. Create it with:"
    echo "   PYTHONPATH=. python scripts/create_sample_connectors_ppt.py --output $SAMPLE_PPTX"
    exit 1
  fi
  echo "   Created $SAMPLE_PPTX"
else
  echo "0. Using existing $SAMPLE_PPTX"
fi
echo ""

# Test health endpoint
echo "1. Testing health endpoint..."
curl -s "$API_URL/health" | jq .
echo ""

# Create a project
echo "2. Creating a project..."
PROJECT_RESPONSE=$(curl -s -X POST "$API_URL/projects" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Connectors Test Project",
    "description": "Test with sample_connectors.pptx (shapes + connectors)"
  }')
echo "$PROJECT_RESPONSE" | jq .
PROJECT_ID=$(echo "$PROJECT_RESPONSE" | jq -r '.project_id')
echo "Project ID: $PROJECT_ID"
echo ""

# Get the project
echo "3. Getting project..."
curl -s "$API_URL/projects/$PROJECT_ID" | jq .
echo ""

# Create a job
echo "4. Creating a job..."
JOB_RESPONSE=$(curl -s -X POST "$API_URL/jobs" \
  -H "Content-Type: application/json" \
  -d "{
    \"project_id\": \"$PROJECT_ID\"
  }")
echo "$JOB_RESPONSE" | jq .
JOB_ID=$(echo "$JOB_RESPONSE" | jq -r '.job_id // empty')
if [ -z "$JOB_ID" ] || [ "$JOB_ID" = "null" ]; then
  echo "ERROR: Failed to create job"
  exit 1
fi
echo "Job ID: $JOB_ID"
echo ""

# Upload sample_connectors.pptx
echo "5. Uploading $SAMPLE_PPTX..."
UPLOAD_RESPONSE=$(curl -s -X POST "$API_URL/jobs/$JOB_ID/upload_pptx" \
  -F "file=@$SAMPLE_PPTX")
echo "$UPLOAD_RESPONSE" | jq .
echo ""

echo "6. Getting job status after upload..."
curl -s "$API_URL/jobs/$JOB_ID" | jq .
echo ""

echo "7. Waiting for worker to process (render + ppt + evidence + native graph)..."
echo "   (May take 30–60 seconds; ensure 'make worker' is running in another terminal)"
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 5
  JOB_STATUS=$(curl -s "$API_URL/jobs/$JOB_ID" | jq -r '.status')
  echo "   ... $(( i * 5 ))s - status: $JOB_STATUS"
  if [ "$JOB_STATUS" = "DONE" ]; then
    echo "   ✅ Job completed"
    break
  fi
  if [ "$JOB_STATUS" = "FAILED" ]; then
    echo "   ❌ Job failed"
    curl -s "$API_URL/jobs/$JOB_ID" | jq '.error_message // .'
    exit 1
  fi
done
echo ""

echo "8. Final job status..."
curl -s "$API_URL/jobs/$JOB_ID" | jq .
echo ""

echo "=== Test completed ==="
echo ""
echo "To verify connectors, script, and verifier:"
echo "  - MinIO: jobs/$JOB_ID/ppt/slide_001.json           → connectors array (e.g. 3 entries)"
echo "  - MinIO: jobs/$JOB_ID/graphs/native/slide_001.json → edges array (e.g. 3 entries)"
echo "  - MinIO: jobs/$JOB_ID/script/script.json          → verified script (verified: true)"
echo "  - MinIO: jobs/$JOB_ID/script/verify_report.json   → verdict per claim (PASS/REWRITE/REMOVE)"
echo "  - MinIO: jobs/$JOB_ID/script/coverage.json        → pct_claims_with_evidence, pass/rewrite/remove"
echo "  - See VERIFY_ARTIFACTS.md → 'How to verify manually with test_api_connectors.sh'"
echo ""
