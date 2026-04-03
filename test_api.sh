#!/bin/bash
# Test script for SlideSherlock API

set -e

API_URL="http://localhost:8000"

echo "=== Testing SlideSherlock API ==="
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
    "name": "Test Project",
    "description": "A test project"
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

# Wait a bit for worker to process
echo "5. Waiting for worker to process job (5 seconds)..."
sleep 5

# Get the job status
echo "6. Getting job status..."
curl -s "$API_URL/jobs/$JOB_ID" | jq .
echo ""

# Upload PPTX (if a test file exists)
# Note: This script uses a single test file, test.pptx, by design.
# Render output: one deck.pdf + one PNG per slide + manifest.json (see VERIFY_ARTIFACTS.md).
echo "7. Testing PPTX upload..."
if [ -f "test.pptx" ]; then
    echo "   Found test.pptx, uploading..."
    UPLOAD_RESPONSE=$(curl -s -X POST "$API_URL/jobs/$JOB_ID/upload_pptx" \
        -F "file=@test.pptx")
    echo "$UPLOAD_RESPONSE" | jq .
    echo ""
    
    echo "8. Getting job status after upload..."
    curl -s "$API_URL/jobs/$JOB_ID" | jq .
    echo ""
    
    echo "9. Verifying job status changed to RUNNING..."
    JOB_STATUS=$(curl -s "$API_URL/jobs/$JOB_ID" | jq -r '.status')
    if [ "$JOB_STATUS" = "RUNNING" ]; then
        echo "   ✅ Job status is RUNNING (expected)"
    else
        echo "   ⚠️  Job status is $JOB_STATUS (expected RUNNING)"
    fi
    echo ""
else
    echo "   ⚠️  test.pptx not found - skipping upload test"
    echo ""
    echo "   To test PPTX upload:"
    echo "   1. Create or copy a .pptx file to the project root as 'test.pptx'"
    echo "   2. Or manually test with:"
    echo "      curl -X POST \"$API_URL/jobs/$JOB_ID/upload_pptx\" -F \"file=@yourfile.pptx\""
    echo ""
fi

echo "   To verify render artifacts (PDF + PNGs per slide): see VERIFY_ARTIFACTS.md or MinIO at jobs/<job_id>/render/"
echo ""
echo "=== Test completed ==="
