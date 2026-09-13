#!/usr/bin/env bash
# ==============================================================================
# Project Luvcraft: Automated PostgreSQL Database Backup Script
# Creates timestamped, gzip-compressed database dumps and manages retention.
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/project-luvcraft/backups}"
CONTAINER_NAME="${CONTAINER_NAME:-project-luvcraft-postgres-1}"
DB_NAME="${DB_NAME:-luvcraft}"
DB_USER="${DB_USER:-postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting database backup for '${DB_NAME}' from '${CONTAINER_NAME}'..."

# Verify container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "ERROR: PostgreSQL container '${CONTAINER_NAME}' is not running." >&2
    exit 1
fi

# Execute pg_dump inside container and stream to gzip
docker exec -t "${CONTAINER_NAME}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" --clean --if-exists | gzip > "${BACKUP_FILE}"

# Verify file existence and non-zero size
if [[ -s "${BACKUP_FILE}" ]]; then
    BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup completed successfully: ${BACKUP_FILE} (${BACKUP_SIZE})"
else
    echo "ERROR: Backup file ${BACKUP_FILE} was created but is empty." >&2
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# Retention policy: remove backups older than RETENTION_DAYS
echo "Applying retention policy: pruning backups older than ${RETENTION_DAYS} days in ${BACKUP_DIR}..."
find "${BACKUP_DIR}" -name "${DB_NAME}_*.sql.gz" -type f -mtime +"${RETENTION_DAYS}" -exec rm -f {} +
echo "Backup operations finished successfully."
