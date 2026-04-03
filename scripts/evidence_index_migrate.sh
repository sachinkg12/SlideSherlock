#!/bin/bash
# Option A: Drop evidence index tables (if they exist), then run Alembic upgrade to 003.
# Use this when migration 003 fails with "relation slides already exists".
# Sets terminal title to "Evidence Index Migration".

set -e
echo -e "\033]0;Evidence Index Migration\007"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Evidence Index Migration (Option A) ==="
echo ""

# 1. Drop evidence index tables if they exist (reverse dependency order)
echo "1. Dropping evidence index tables if they exist..."
docker compose exec -T postgres psql -U slidesherlock -d slidesherlock <<'SQL'
DROP TABLE IF EXISTS entity_links CASCADE;
DROP TABLE IF EXISTS claim_links CASCADE;
DROP TABLE IF EXISTS source_refs CASCADE;
DROP TABLE IF EXISTS evidence_items CASCADE;
DROP TABLE IF EXISTS sources CASCADE;
DROP TABLE IF EXISTS slides CASCADE;
SQL
echo "   Done."
echo ""

# 2. Run Alembic upgrade to head
echo "2. Running alembic upgrade head..."
venv/bin/python -m alembic upgrade head
echo ""

echo "=== Done ==="
