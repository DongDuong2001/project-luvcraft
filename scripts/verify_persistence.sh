#!/usr/bin/env bash
# ==============================================================================
# Project Luvcraft: PostgreSQL Volume Persistence Verification Script
# Verifies that data stored in postgres_data volume survives container restarts.
# ==============================================================================
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-project-luvcraft-postgres-1}"
DB_NAME="${DB_NAME:-luvcraft}"
DB_USER="${DB_USER:-postgres}"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting data persistence verification..."

# 1. Check container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "ERROR: PostgreSQL container '${CONTAINER_NAME}' is not running." >&2
    exit 1
fi

TEST_MARKER="test_sentinel_$(date +%s)"

echo "[1/4] Writing sentinel test record: '${TEST_MARKER}'..."
docker exec -t "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" -c "
CREATE TABLE IF NOT EXISTS _persistence_verification (
    id SERIAL PRIMARY KEY,
    marker VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO _persistence_verification (marker) VALUES ('${TEST_MARKER}');
"

echo "[2/4] Restarting PostgreSQL container to test volume persistence..."
docker restart "${CONTAINER_NAME}" > /dev/null

echo "Waiting for PostgreSQL service to become ready..."
for i in {1..15}; do
    if docker exec -t "${CONTAINER_NAME}" pg_isready -U "${DB_USER}" -d "${DB_NAME}" > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo "[3/4] Checking sentinel test record after container restart..."
FOUND_COUNT=$(docker exec -t "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" -t -c "
SELECT count(*) FROM _persistence_verification WHERE marker = '${TEST_MARKER}';
" | tr -d '[:space:]')

if [[ "${FOUND_COUNT}" -ge 1 ]]; then
    echo "[4/4] SUCCESS: Sentinel record survived restart. PostgreSQL volume is persistent!"
    # Clean up test table
    docker exec -t "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" -c "DROP TABLE _persistence_verification;" > /dev/null
    echo "Persistence verification complete. All checks passed."
    exit 0
else
    echo "CRITICAL: Sentinel record was lost after restart. Volume may not be mounted properly!" >&2
    exit 1
fi
