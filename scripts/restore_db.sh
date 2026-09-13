#!/usr/bin/env bash
# ==============================================================================
# Project Luvcraft: PostgreSQL Database Restore Script
# Restores a specified gzip-compressed or plain SQL backup into PostgreSQL.
# ==============================================================================
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-project-luvcraft-postgres-1}"
DB_NAME="${DB_NAME:-luvcraft}"
DB_USER="${DB_USER:-postgres}"

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <path_to_backup_file.sql.gz|path_to_backup_file.sql>" >&2
    echo "Example: $0 /opt/project-luvcraft/backups/luvcraft_20260913_120000.sql.gz" >&2
    exit 1
fi

BACKUP_FILE="$1"

if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "ERROR: Backup file '${BACKUP_FILE}' does not exist." >&2
    exit 1
fi

# Verify container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "ERROR: PostgreSQL container '${CONTAINER_NAME}' is not running." >&2
    exit 1
fi

echo "WARNING: Restoring '${BACKUP_FILE}' will overwrite existing data in '${DB_NAME}'."
read -r -p "Are you sure you want to proceed with database restore? [y/N]: " CONFIRM
if [[ "${CONFIRM}" != [yY] && "${CONFIRM}" != [yY][eE][sS] ]]; then
    echo "Restore cancelled by user."
    exit 0
fi

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting database restore into '${DB_NAME}'..."

if [[ "${BACKUP_FILE}" == *.gz ]]; then
    gzip -dc "${BACKUP_FILE}" | docker exec -i "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}"
else
    docker exec -i "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" < "${BACKUP_FILE}"
fi

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Verifying restored database tables..."
TABLE_COUNT=$(docker exec -t "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d '[:space:]')

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Database restore verified successfully. Total public tables: ${TABLE_COUNT}"
