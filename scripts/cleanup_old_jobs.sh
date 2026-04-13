#!/bin/bash
# Auto-cleanup script for demo VM.
# Deletes all jobs older than 30 minutes from MinIO and PostgreSQL.
# Run via cron: */5 * * * * /path/to/cleanup_old_jobs.sh
#
# Requires: docker, running slidesherlock containers

set -e

COMPOSE_DIR="${1:-/root/SlideSherlock}"
MAX_AGE_MINUTES=30

cd "$COMPOSE_DIR"

# Get jobs older than MAX_AGE_MINUTES from the database
OLD_JOBS=$(docker compose exec -T postgres psql -U slidesherlock -t -c \
  "SELECT job_id FROM jobs WHERE created_at < NOW() - INTERVAL '${MAX_AGE_MINUTES} minutes';" 2>/dev/null | tr -d ' ')

if [ -z "$OLD_JOBS" ]; then
    exit 0
fi

for JOB_ID in $OLD_JOBS; do
    [ -z "$JOB_ID" ] && continue
    echo "Cleaning job: $JOB_ID"

    # Delete from MinIO
    docker compose exec -T minio mc rm --recursive --force /data/slidesherlock/jobs/$JOB_ID/ 2>/dev/null || true

    # Delete from database
    docker compose exec -T postgres psql -U slidesherlock -c \
      "DELETE FROM artifacts WHERE job_id='$JOB_ID';
       DELETE FROM evidence_items WHERE job_id='$JOB_ID';
       DELETE FROM source_refs WHERE evidence_id IN (SELECT evidence_id FROM evidence_items WHERE job_id='$JOB_ID');
       DELETE FROM claim_links WHERE evidence_id IN (SELECT evidence_id FROM evidence_items WHERE job_id='$JOB_ID');
       DELETE FROM entity_links WHERE evidence_id IN (SELECT evidence_id FROM evidence_items WHERE job_id='$JOB_ID');
       DELETE FROM sources WHERE job_id='$JOB_ID';
       DELETE FROM slides WHERE job_id='$JOB_ID';
       DELETE FROM jobs WHERE job_id='$JOB_ID';" 2>/dev/null || true
done

echo "Cleanup done: $(echo "$OLD_JOBS" | wc -w) jobs removed"
