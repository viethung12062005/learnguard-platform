#!/usr/bin/env bash
# =============================================================================
# LearnGuard — Automated PostgreSQL Backup Script with Checksum & Retention
#
# Produces an atomic gzipped plain SQL dump of the `learnguard` database from
# the running `lg-postgres` container, writes a SHA-256 integrity file, and
# prunes backups older than the retention count (default: keep latest 14 dumps).
#
# Usage:
#   ./backup-db.sh [--dry-run] [--backup-dir /opt/learnguard/data/backups] [--keep 14]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_DIR="${LG_COMPOSE_DIR:-${PLATFORM_ROOT}/deploy/digitalocean}"
BACKUP_DIR="${LG_BACKUP_DIR:-/opt/learnguard/data/backups}"
RETENTION_COUNT=14
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --compose-dir)
      COMPOSE_DIR="$2"
      shift 2
      ;;
    --backup-dir)
      BACKUP_DIR="$2"
      shift 2
      ;;
    --keep)
      RETENTION_COUNT="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

ENV_FILE="${COMPOSE_DIR}/.env"
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
DUMP_FILE="${BACKUP_DIR}/learnguard_pg_${TIMESTAMP}.sql.gz"
TMP_DUMP_FILE="${DUMP_FILE}.tmp"
SHA_FILE="${DUMP_FILE}.sha256"

log() {
  echo "[backup-db] $(date -u +"%Y-%m-%dT%H:%M:%SZ") - $*"
}

if [[ "${DRY_RUN}" == "true" ]]; then
  log "[DRY-RUN] Would create PostgreSQL dump at ${DUMP_FILE}, generate ${SHA_FILE}, and retain last ${RETENTION_COUNT} backups."
  exit 0
fi

trap 'rm -f "${TMP_DUMP_FILE}"' EXIT

mkdir -p "${BACKUP_DIR}"
chmod 0700 "${BACKUP_DIR}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

DB_USER="${POSTGRES_ADMIN_USER:-lgadmin}"
DB_NAME="${POSTGRES_DB:-learnguard}"

if ! docker ps --format '{{.Names}}' | grep -q '^lg-postgres$'; then
  log "ERROR: Container lg-postgres is not running."
  exit 1
fi

log "Creating compressed PostgreSQL backup -> ${DUMP_FILE}..."
docker exec lg-postgres pg_dump -U "${DB_USER}" -d "${DB_NAME}" --clean --if-exists --no-owner --no-privileges \
  | gzip -9 > "${TMP_DUMP_FILE}"
mv "${TMP_DUMP_FILE}" "${DUMP_FILE}"

chmod 0600 "${DUMP_FILE}"
sha256sum "${DUMP_FILE}" > "${SHA_FILE}"
chmod 0600 "${SHA_FILE}"

log "Backup complete ($(du -h "${DUMP_FILE}" | cut -f1)). Checksum saved to ${SHA_FILE}."

# Prune older backups beyond RETENTION_COUNT
mapfile -t OLD_DUMPS < <(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'learnguard_pg_*.sql.gz' -printf '%T@\t%p\n' 2>/dev/null | sort -rn | cut -f2- | tail -n +"$((RETENTION_COUNT + 1))" || true)
if [[ "${#OLD_DUMPS[@]}" -gt 0 ]]; then
  log "Pruning ${#OLD_DUMPS[@]} old backup(s) exceeding retention policy (keep=${RETENTION_COUNT})..."
  for old in "${OLD_DUMPS[@]}"; do
    rm -f "${old}" "${old}.sha256"
  done
fi

log "Backup job finished successfully."
