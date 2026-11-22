#!/usr/bin/env bash
# =============================================================================
# LearnGuard — Instant Application Rollback Script on DigitalOcean Droplet VM
#
# Restores the previous known-good container image digests from
# `/opt/learnguard/deploy/digitalocean/last_good_release.env`, restarts the
# `api` and `frontend` services, and verifies container healthchecks.
#
# Usage:
#   ./rollback-do.sh [--dry-run] [--compose-dir /opt/learnguard/deploy/digitalocean]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_DIR="${LG_COMPOSE_DIR:-${PLATFORM_ROOT}/deploy/digitalocean}"
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
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.prod.yml"
ENV_FILE="${COMPOSE_DIR}/.env"
LAST_GOOD_FILE="${COMPOSE_DIR}/last_good_release.env"

log() {
  echo "[rollback-do] $(date -u +"%Y-%m-%dT%H:%M:%SZ") - $*"
}

update_env_var() {
  local key="$1"
  local val="$2"
  local file="$3"
  local tmp_file
  tmp_file="$(mktemp)"
  awk -v k="${key}" -v v="${val}" '
    BEGIN { found = 0 }
    index($0, k "=") == 1 { print k "=" v; found = 1; next }
    { print }
    END { if (!found) print k "=" v }
  ' "${file}" > "${tmp_file}"
  chmod --reference="${file}" "${tmp_file}" 2>/dev/null || chmod 0600 "${tmp_file}"
  mv "${tmp_file}" "${file}"
}

if [[ "${DRY_RUN}" == "true" ]]; then
  log "[DRY-RUN] Would load previous digests from ${LAST_GOOD_FILE}, update ${ENV_FILE}, and run docker compose up -d api frontend"
  exit 0
fi

if [[ ! -f "${LAST_GOOD_FILE}" ]]; then
  log "ERROR: Rollback state file not found at ${LAST_GOOD_FILE}. Cannot perform automatic rollback."
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  log "ERROR: Production .env file not found at ${ENV_FILE}."
  exit 1
fi

# shellcheck disable=SC1090
source "${LAST_GOOD_FILE}"

if [[ -z "${LG_API_IMAGE:-}" || -z "${LG_FE_IMAGE:-}" ]]; then
  log "ERROR: ${LAST_GOOD_FILE} is missing LG_API_IMAGE or LG_FE_IMAGE."
  exit 1
fi

log "Rolling back to last known-good release:"
log "  API : ${LG_API_IMAGE}"
log "  FE  : ${LG_FE_IMAGE}"
log "  ML  : ${LG_ML_IMAGE:-unchanged}"

update_env_var "LG_API_IMAGE" "${LG_API_IMAGE}" "${ENV_FILE}"
update_env_var "LG_FE_IMAGE" "${LG_FE_IMAGE}" "${ENV_FILE}"
if [[ -n "${LG_ML_IMAGE:-}" ]]; then
  update_env_var "LG_ML_IMAGE" "${LG_ML_IMAGE}" "${ENV_FILE}"
fi

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d api frontend

log "Waiting for rolled-back containers to report healthy..."
HEALTHY=false
for _ in $(seq 1 25); do
  API_HEALTH="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' lg-api 2>/dev/null || echo "unknown")"
  FE_HEALTH="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' lg-frontend 2>/dev/null || echo "unknown")"
  if [[ "${API_HEALTH}" == "healthy" && "${FE_HEALTH}" == "healthy" ]]; then
    HEALTHY=true
    break
  fi
  sleep 2
done

if [[ "${HEALTHY}" != "true" ]]; then
  log "ERROR: Rolled-back containers failed to reach healthy status!"
  exit 1
fi

log "Rollback completed and verified healthy."
