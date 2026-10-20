#!/usr/bin/env bash
# PostgreSQL Automated Backup & Verification Script (Section 49)
set -euo pipefail
BACKUP_DIR="${BACKUP_DIR:-/var/backups/pyforge}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${BACKUP_DIR}"
OUT_FILE="${BACKUP_DIR}/pyforge_${TIMESTAMP}.sql.gz"
pg_dump "${DATABASE_URL}" --format=custom --no-owner --no-privileges | gzip -9 > "${OUT_FILE}"
sha256sum "${OUT_FILE}" > "${OUT_FILE}.sha256"
find "${BACKUP_DIR}" -name "pyforge_*.sql.gz*" -mtime +30 -delete
echo "Backup verified and stored at ${OUT_FILE}"
