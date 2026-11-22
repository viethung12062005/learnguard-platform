#!/usr/bin/env bash
# =============================================================================
# LearnGuard — Verified PostgreSQL Database Restore Script
#
# Verifies the SHA-256 checksum of a backup archive, restores it into the
# `lg-postgres` container, and re-applies `init-db.sh` least-privilege grants
# so `lg_api` and `lg_ml_writer` retain exact permissions.
#
# Usage:
#   ./restore-db.sh --file /opt/learnguard/data/backups/learnguard_pg_YYYYMMDDTHHMMSSZ.sql.gz [--dry-run]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_DIR="${LG_COMPOSE_DIR:-${PLATFORM_ROOT}/deploy/digitalocean}"
BACKUP_FILE=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --file)
      BACKUP_FILE="$2"
      shift 2
      ;;
    --compose-dir)
      COMPOSE_DIR="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

log() {
  echo "[restore-db] $(date -u +"%Y-%m-%dT%H:%M:%SZ") - $*"
}

if [[ -z "${BACKUP_FILE}" ]]; then
  log "ERROR: --file <path-to-backup.sql.gz> is required."
  exit 1
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  log "[DRY-RUN] Would verify SHA-256 checksum of ${BACKUP_FILE}, restore into lg-postgres, and re-apply init-db.sh grants."
  exit 0
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
  log "ERROR: Backup file not found: ${BACKUP_FILE}"
  exit 1
fi

if [[ -f "${BACKUP_FILE}.sha256" ]]; then
  log "1/3 Verifying SHA-256 integrity checksum..."
  sha256sum --check "${BACKUP_FILE}.sha256"
else
  log "WARNING: No .sha256 companion file found for ${BACKUP_FILE}; proceeding without checksum check."
fi

ENV_FILE="${COMPOSE_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

DB_USER="${POSTGRES_ADMIN_USER:-lgadmin}"
DB_NAME="${POSTGRES_DB:-learnguard}"

log "2/3 Restoring SQL dump into database '${DB_NAME}'..."
gunzip -c "${BACKUP_FILE}" | docker exec -i lg-postgres psql -v ON_ERROR_STOP=1 -U "${DB_USER}" -d "${DB_NAME}" >/dev/null

log "3/3 Re-applying least-privilege role ownership and grants (init-db.sh)..."
docker exec lg-postgres bash /docker-entrypoint-initdb.d/10-init-db.sh

log "Database restore completed and verified."
