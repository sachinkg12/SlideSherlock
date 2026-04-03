#!/bin/bash
# Test script for SlideSherlock Render Stage
# Tests PPTX upload and render stage execution

set -e

API_URL="http://localhost:8000"

echo "=== Testing SlideSherlock Render Stage ==="
echo ""

# Check if test.pptx exists
if [ ! -f "test.pptx" ]; then
    echo "❌ ERROR: test.pptx not found in project root"
    echo ""
    echo "To create a test file:"
    echo "  1. Create a PowerPoint presentation with a few slides"
    echo "  2. Save it as test.pptx in the project root"
    echo "  3. Or copy an existing .pptx file:"
    echo "     cp /path/to/your/presentation.pptx test.pptx"
    exit 1
fi

echo "✅ Found test.pptx"
echo ""

# Test health endpoint
echo "1. Testing health endpoint..."
HEALTH=$(curl -s "$API_URL/health")
echo "$HEALTH" | jq .
if [ "$(echo "$HEALTH" | jq -r '.status')" != "ok" ]; then
    echo "❌ Health check failed. Is the API running?"
    exit 1
fi
echo ""

# Create a project
echo "2. Creating a project..."
PROJECT_RESPONSE=$(curl -s -X POST "$API_URL/projects" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Render Test Project",
    "description": "Testing render stage"
  }')
echo "$PROJECT_RESPONSE" | jq .
PROJECT_ID=$(echo "$PROJECT_RESPONSE" | jq -r '.project_id')
if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" = "null" ]; then
    echo "❌ Failed to create project"
    exit 1
fi
echo "Project ID: $PROJECT_ID"
echo ""

# Create a job
echo "3. Creating a job..."
JOB_RESPONSE=$(curl -s -X POST "$API_URL/jobs" \
  -H "Content-Type: application/json" \
  -d "{
    \"project_id\": \"$PROJECT_ID\"
  }")
echo "$JOB_RESPONSE" | jq .
JOB_ID=$(echo "$JOB_RESPONSE" | jq -r '.job_id // empty')
if [ -z "$JOB_ID" ] || [ "$JOB_ID" = "null" ]; then
    echo "❌ Failed to create job"
    exit 1
fi
echo "Job ID: $JOB_ID"
echo ""

# Check initial job status
echo "4. Checking initial job status..."
INITIAL_STATUS=$(curl -s "$API_URL/jobs/$JOB_ID" | jq -r '.status')
echo "Initial status: $INITIAL_STATUS"
if [ "$INITIAL_STATUS" != "QUEUED" ]; then
    echo "⚠️  Expected QUEUED, got $INITIAL_STATUS"
fi
echo ""

# Upload PPTX
echo "5. Uploading PPTX file..."
UPLOAD_RESPONSE=$(curl -s -X POST "$API_URL/jobs/$JOB_ID/upload_pptx" \
    -F "file=@test.pptx")
echo "$UPLOAD_RESPONSE" | jq .
UPLOAD_ARTIFACT_ID=$(echo "$UPLOAD_RESPONSE" | jq -r '.artifact_id // empty')
if [ -z "$UPLOAD_ARTIFACT_ID" ] || [ "$UPLOAD_ARTIFACT_ID" = "null" ]; then
    echo "❌ Upload failed or no artifact ID returned"
    exit 1
fi
echo "Upload artifact ID: $UPLOAD_ARTIFACT_ID"
echo ""

# Check job status after upload
echo "6. Checking job status after upload..."
UPLOAD_STATUS=$(curl -s "$API_URL/jobs/$JOB_ID" | jq -r '.status')
echo "Status after upload: $UPLOAD_STATUS"
if [ "$UPLOAD_STATUS" != "RUNNING" ]; then
    echo "⚠️  Expected RUNNING, got $UPLOAD_STATUS"
fi
echo ""

# Wait for render stage to complete
echo "7. Waiting for render stage to process (this may take 30-60 seconds)..."
echo "   (The worker should pick up the render_stage job from Redis)"
MAX_WAIT=120
WAIT_TIME=0
INTERVAL=5

while [ $WAIT_TIME -lt $MAX_WAIT ]; do
    sleep $INTERVAL
    WAIT_TIME=$((WAIT_TIME + INTERVAL))
    
    JOB_STATUS=$(curl -s "$API_URL/jobs/$JOB_ID" | jq -r '.status')
    echo "   [${WAIT_TIME}s] Job status: $JOB_STATUS"
    
    if [ "$JOB_STATUS" = "RUNNING" ] || [ "$JOB_STATUS" = "PROCESSING" ]; then
        echo "   ⏳ Still processing..."
    elif [ "$JOB_STATUS" = "FAILED" ]; then
        ERROR_MSG=$(curl -s "$API_URL/jobs/$JOB_ID" | jq -r '.error_message // "Unknown error"')
        echo "   ❌ Job failed: $ERROR_MSG"
        exit 1
    else
        echo "   ✅ Job completed with status: $JOB_STATUS"
        break
    fi
done

if [ $WAIT_TIME -ge $MAX_WAIT ]; then
    echo "   ⚠️  Timeout waiting for job to complete"
fi
echo ""

# Get final job status
echo "8. Final job status:"
FINAL_JOB=$(curl -s "$API_URL/jobs/$JOB_ID")
echo "$FINAL_JOB" | jq .
echo ""

# Summary
echo "=== Test Summary ==="
echo "✅ Project created: $PROJECT_ID"
echo "✅ Job created: $JOB_ID"
echo "✅ PPTX uploaded: $UPLOAD_ARTIFACT_ID"
echo "✅ Render stage: $JOB_STATUS"
echo ""
echo "Next steps:"
echo "1. Check MinIO console at http://localhost:9001 (minioadmin/minioadmin)"
echo "2. Look for artifacts in bucket 'slidesherlock' at:"
echo "   - jobs/$JOB_ID/input/deck.pptx"
echo "   - jobs/$JOB_ID/render/deck.pdf"
echo "   - jobs/$JOB_ID/render/slides/slide_001.png, slide_002.png, etc."
echo "   - jobs/$JOB_ID/render/manifest.json"
echo ""
echo "3. Check database artifacts:"
echo "   Connect to PostgreSQL and query:"
echo "   SELECT artifact_type, storage_path, size_bytes FROM artifacts WHERE job_id = '$JOB_ID';"
echo ""
