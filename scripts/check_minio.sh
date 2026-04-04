#!/bin/bash
# Script to check MinIO contents for a job

set -e

if [ -z "$1" ]; then
    echo "Usage: ./check_minio.sh <job_id>"
    echo ""
    echo "Example:"
    echo "  ./check_minio.sh abc-123-def-456"
    exit 1
fi

JOB_ID=$1
BUCKET="slidesherlock"

echo "=== Checking MinIO for job: $JOB_ID ==="
echo ""

# Check if mc (MinIO client) is available
if command -v mc > /dev/null 2>&1; then
    echo "Using MinIO client (mc)..."
    echo ""
    
    # Configure alias if not already done
    mc alias set local http://localhost:9000 minioadmin minioadmin 2>/dev/null || true
    
    # List all files for this job
    echo "Files in jobs/$JOB_ID/:"
    mc find local/$BUCKET --name "*$JOB_ID*" --print || echo "No files found"
    
elif command -v docker > /dev/null 2>&1; then
    echo "Using Docker to access MinIO..."
    echo ""
    
    # Use docker exec to access MinIO
    echo "Files in jobs/$JOB_ID/:"
    docker compose exec -T minio sh -c "mc find local/$BUCKET --name '*$JOB_ID*' --print" 2>/dev/null || \
    docker exec -it $(docker ps | grep minio | awk '{print $1}') sh -c "mc find local/$BUCKET --name '*$JOB_ID*' --print" 2>/dev/null || \
    echo "Could not access MinIO via Docker. Try accessing via web console at http://localhost:9001"
    
else
    echo "⚠️  MinIO client (mc) not found and Docker not available"
    echo ""
    echo "Please check MinIO console manually:"
    echo "  1. Open http://localhost:9001"
    echo "  2. Login: minioadmin / minioadmin"
    echo "  3. Navigate to bucket: $BUCKET"
    echo "  4. Look for folder: jobs/$JOB_ID/"
    echo ""
    echo "Expected structure:"
    echo "  jobs/$JOB_ID/"
    echo "    input/"
    echo "      deck.pptx"
    echo "    render/"
    echo "      deck.pdf"
    echo "      slides/"
    echo "        slide_001.png"
    echo "        slide_002.png"
    echo "        ..."
    echo "      manifest.json"
fi

echo ""
echo "=== Expected Artifacts ==="
echo "Input:"
echo "  - jobs/$JOB_ID/input/deck.pptx"
echo ""
echo "Render:"
echo "  - jobs/$JOB_ID/render/deck.pdf"
echo "  - jobs/$JOB_ID/render/slides/slide_001.png"
echo "  - jobs/$JOB_ID/render/slides/slide_002.png"
echo "  - ... (one PNG per slide)"
echo "  - jobs/$JOB_ID/render/manifest.json"
echo ""
