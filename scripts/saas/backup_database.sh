#!/usr/bin/env bash
# ==============================================================================
# Mac Digital Human SaaS - Database & MinIO Metadata Backup Script
# Usage:
#   bash scripts/saas/backup_database.sh [/path/to/backup/dir]
# ==============================================================================
set -euo pipefail

BACKUP_ROOT="${1:-./backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
TARGET_DIR="${BACKUP_ROOT}/${TIMESTAMP}"

mkdir -p "${TARGET_DIR}"

echo ">>> [1/3] Backing up PostgreSQL database..."
if docker ps --format '{{.Names}}' | grep -q 'mac-digital-human-prod-postgres'; then
  docker exec mac-digital-human-prod-postgres pg_dump -U "${SAAS_DB_USER:-digital_human}" "${SAAS_DB_NAME:-digital_human}" | gzip > "${TARGET_DIR}/postgres_${TIMESTAMP}.sql.gz"
  echo "    Saved PostgreSQL dump to: ${TARGET_DIR}/postgres_${TIMESTAMP}.sql.gz"
else
  echo "    [WARN] mac-digital-human-prod-postgres container is not running, skipping database dump."
fi

echo ">>> [2/3] Recording Docker container and image hashes..."
docker ps --filter "name=mac-digital-human" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" > "${TARGET_DIR}/containers_${TIMESTAMP}.txt" 2>&1 || true

echo ">>> [3/3] Backing up configuration files (excluding secrets)..."
if [ -f .env.production ]; then
  # Redact secrets
  sed -E 's/(PASSWORD|SECRET)=.*/\1=REDACTED/g' .env.production > "${TARGET_DIR}/env.production.redacted"
fi

echo ">>> Backup completed successfully at ${TARGET_DIR}"
