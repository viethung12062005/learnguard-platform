#!/usr/bin/env bash
# =============================================================================
# LearnGuard — Production Deployment Script on DigitalOcean Droplet VM
#
# Reference: ADR-0009 (CI/CD Pipeline with GHCR Immutable Digests & Auto-Rollback)
#
# Execution Flow:
#   1. Validates environment and target container image digests (`@sha256:...` or explicit tags)
#   2. Saves currently running non-placeholder image references to `last_good_release.env`
#   3. Executes pre-deployment PostgreSQL snapshot via `backup-db.sh`
#   4. Pulls target images from GHCR (including `ml-worker` batch image)
#   5. Runs database migration (`db-migrate`: Alembic upgrade head) & idempotent role grants
#   6. Performs rolling update of `api` and `frontend` services
#   7. Waits for Docker container healthchecks (`healthy`)
#   8. Runs comprehensive post-deploy E2E verification (`smoke-test.sh`)
#   9. Automatically invokes `rollback-do.sh` if healthcheck or smoke test fails!
#
# Usage:
#   ./deploy-do.sh [--dry-run] [--skip-backup] [--api-image <img@sha256:...>] [--fe-image <img@sha256:...>] [--ml-image <img@sha256:...>]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_DIR="${LG_COMPOSE_DIR:-${PLATFORM_ROOT}/deploy/digitalocean}"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.prod.yml"
ENV_FILE="${COMPOSE_DIR}/.env"
LAST_GOOD_FILE="${COMPOSE_DIR}/last_good_release.env"

DRY_RUN=false
SKIP_BACKUP=false
ARG_API_IMAGE=""
ARG_FE_IMAGE=""
ARG_ML_IMAGE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --skip-backup)
      SKIP_BACKUP=true
      shift
      ;;
    --api-image)
      ARG_API_IMAGE="$2"
      shift 2
      ;;
    --fe-image)
      ARG_FE_IMAGE="$2"
      shift 2
      ;;
    --ml-image)
      ARG_ML_IMAGE="$2"
      shift 2
      ;;
    --compose-dir)
      COMPOSE_DIR="$2"
      COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.prod.yml"
      ENV_FILE="${COMPOSE_DIR}/.env"
      LAST_GOOD_FILE="${COMPOSE_DIR}/last_good_release.env"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

log() {
  echo "[deploy-do] $(date -u +"%Y-%m-%dT%H:%M:%SZ") - $*"
}

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  log "ERROR: Docker Compose file not found at ${COMPOSE_FILE}"
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  if [[ "${DRY_RUN}" == "true" && -f "${COMPOSE_DIR}/.env.prod.example" ]]; then
    log "[DRY-RUN] Using .env.prod.example because ${ENV_FILE} does not exist yet."
    ENV_FILE="${COMPOSE_DIR}/.env.prod.example"
  else
    log "ERROR: Production .env file not found at ${ENV_FILE}"
    exit 1
  fi
fi

# Load non-sensitive image variables from ENV_FILE safely
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

PREV_API_IMAGE="${LG_API_IMAGE:-}"
PREV_FE_IMAGE="${LG_FE_IMAGE:-}"
PREV_ML_IMAGE="${LG_ML_IMAGE:-}"

TARGET_API_IMAGE="${ARG_API_IMAGE:-${LG_API_IMAGE:-}}"
TARGET_FE_IMAGE="${ARG_FE_IMAGE:-${LG_FE_IMAGE:-}}"
TARGET_ML_IMAGE="${ARG_ML_IMAGE:-${LG_ML_IMAGE:-}}"

if [[ -z "${TARGET_API_IMAGE}" || -z "${TARGET_FE_IMAGE}" || -z "${TARGET_ML_IMAGE}" ]]; then
  log "ERROR: LG_API_IMAGE, LG_FE_IMAGE, and LG_ML_IMAGE must all be specified."
  exit 1
fi

log "Target release images:"
log "  API : ${TARGET_API_IMAGE}"
log "  FE  : ${TARGET_FE_IMAGE}"
log "  ML  : ${TARGET_ML_IMAGE}"

is_placeholder_digest() {
  local img="$1"
  [[ "${img}" == *"1111111111111111"* || "${img}" == *"2222222222222222"* || "${img}" == *"3333333333333333"* || "${img}" == *"0000000000000000"* ]]
}

# -----------------------------------------------------------------------------
# 1. Record current release into last_good_release.env before modifying stack
# -----------------------------------------------------------------------------
log "1/7 Saving previous known-good release pointers to ${LAST_GOOD_FILE}..."
if [[ "${DRY_RUN}" == "false" ]]; then
  if [[ -n "${PREV_API_IMAGE}" && -n "${PREV_FE_IMAGE}" ]] \
     && ! is_placeholder_digest "${PREV_API_IMAGE}" \
     && ! is_placeholder_digest "${PREV_FE_IMAGE}"; then
    cat > "${LAST_GOOD_FILE}" <<EOF
# Saved automatically by deploy-do.sh at $(date -u +"%Y-%m-%dT%H:%M:%SZ")
LG_API_IMAGE=${PREV_API_IMAGE}
LG_FE_IMAGE=${PREV_FE_IMAGE}
LG_ML_IMAGE=${PREV_ML_IMAGE}
EOF
    chmod 0600 "${LAST_GOOD_FILE}"
  else
    log "Skipping last_good_release.env update because current .env contains empty or placeholder digests."
  fi
else
  log "[DRY-RUN] Would save LG_API_IMAGE, LG_FE_IMAGE, LG_ML_IMAGE to ${LAST_GOOD_FILE} (unless placeholder)"
fi

# Safely update key=value pairs without sed delimiter/backreference hazards
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

if [[ "${DRY_RUN}" == "false" ]]; then
  update_env_var "LG_API_IMAGE" "${TARGET_API_IMAGE}" "${ENV_FILE}"
  update_env_var "LG_FE_IMAGE" "${TARGET_FE_IMAGE}" "${ENV_FILE}"
  update_env_var "LG_ML_IMAGE" "${TARGET_ML_IMAGE}" "${ENV_FILE}"
fi

export LG_API_IMAGE="${TARGET_API_IMAGE}"
export LG_FE_IMAGE="${TARGET_FE_IMAGE}"
export LG_ML_IMAGE="${TARGET_ML_IMAGE}"

# Helper function to trigger automatic rollback on failure
trigger_auto_rollback() {
  local reason="$1"
  log "CRITICAL: Deployment failed during '${reason}'. Triggering automatic rollback..."
  if [[ -x "${SCRIPT_DIR}/rollback-do.sh" ]]; then
    if [[ "${DRY_RUN}" == "true" ]]; then
      "${SCRIPT_DIR}/rollback-do.sh" --dry-run --compose-dir "${COMPOSE_DIR}" || true
    else
      "${SCRIPT_DIR}/rollback-do.sh" --compose-dir "${COMPOSE_DIR}" || true
    fi
  fi
  exit 1
}

# -----------------------------------------------------------------------------
# 2. Pre-deployment Database Backup
# -----------------------------------------------------------------------------
if [[ "${SKIP_BACKUP}" == "false" ]]; then
  log "2/7 Running pre-deployment PostgreSQL backup..."
  if [[ "${DRY_RUN}" == "true" ]]; then
    "${SCRIPT_DIR}/backup-db.sh" --dry-run --compose-dir "${COMPOSE_DIR}"
  else
    "${SCRIPT_DIR}/backup-db.sh" --compose-dir "${COMPOSE_DIR}" || log "WARNING: Pre-deploy backup skipped (postgres container not running yet)."
  fi
else
  log "2/7 Skipping pre-deployment database backup (--skip-backup)."
fi

# -----------------------------------------------------------------------------
# 3. Pull Immutable Container Images
# -----------------------------------------------------------------------------
log "3/7 Pulling container images from registry..."
if [[ "${DRY_RUN}" == "false" ]]; then
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" pull postgres api frontend
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --profile batch pull ml-worker || true
else
  log "[DRY-RUN] Would run: docker compose -f ${COMPOSE_FILE} pull postgres api frontend (and --profile batch pull ml-worker)"
fi

# -----------------------------------------------------------------------------
# 4. Ensure PostgreSQL is Healthy & Run Database Migrations + Roles Init
# -----------------------------------------------------------------------------
log "4/7 Starting PostgreSQL and executing Alembic migrations + least-privilege role verification..."
if [[ "${DRY_RUN}" == "false" ]]; then
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d postgres

  # Wait up to 60s for postgres healthcheck
  PG_HEALTHY=false
  for _ in $(seq 1 30); do
    STATUS="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}starting{{end}}' lg-postgres 2>/dev/null || echo "starting")"
    if [[ "${STATUS}" == "healthy" ]]; then
      PG_HEALTHY=true
      break
    fi
    sleep 2
  done

  if [[ "${PG_HEALTHY}" != "true" ]]; then
    trigger_auto_rollback "postgres_healthcheck_timeout"
  fi

  # Re-apply idempotent init-db.sh to guarantee ml_predictions & default privileges before Alembic
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T postgres bash /docker-entrypoint-initdb.d/10-init-db.sh \
    || trigger_auto_rollback "init_db_roles_failure"

  # Run Alembic migrations
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" run --rm db-migrate \
    || trigger_auto_rollback "alembic_db_migration_failure"
else
  log "[DRY-RUN] Would start postgres, verify init-db.sh roles, and run db-migrate (alembic upgrade head)"
fi

# -----------------------------------------------------------------------------
# 5. Rolling Update of API and Frontend Containers
# -----------------------------------------------------------------------------
log "5/7 Performing rolling update of api and frontend containers..."
if [[ "${DRY_RUN}" == "false" ]]; then
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --remove-orphans api frontend \
    || trigger_auto_rollback "compose_up_api_frontend"
else
  log "[DRY-RUN] Would run: docker compose -f ${COMPOSE_FILE} up -d --remove-orphans api frontend"
fi

# -----------------------------------------------------------------------------
# 6. Wait for Container Healthchecks
# -----------------------------------------------------------------------------
log "6/7 Waiting for api and frontend container healthchecks..."
if [[ "${DRY_RUN}" == "false" ]]; then
  SERVICES_HEALTHY=false
  for _ in $(seq 1 30); do
    API_HEALTH="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' lg-api 2>/dev/null || echo "unknown")"
    FE_HEALTH="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' lg-frontend 2>/dev/null || echo "unknown")"
    if [[ "${API_HEALTH}" == "healthy" && "${FE_HEALTH}" == "healthy" ]]; then
      SERVICES_HEALTHY=true
      break
    fi
    sleep 2
  done

  if [[ "${SERVICES_HEALTHY}" != "true" ]]; then
    log "ERROR: Container healthchecks did not converge (lg-api=${API_HEALTH:-unknown}, lg-frontend=${FE_HEALTH:-unknown})"
    trigger_auto_rollback "container_healthcheck_timeout"
  fi
else
  log "[DRY-RUN] Would poll docker inspect health status for lg-api and lg-frontend"
fi

# -----------------------------------------------------------------------------
# 7. Run Post-Deploy E2E Smoke Tests
# -----------------------------------------------------------------------------
log "7/7 Executing post-deployment E2E smoke test suite..."
if [[ "${DRY_RUN}" == "true" ]]; then
  "${SCRIPT_DIR}/smoke-test.sh" --dry-run
else
  HTTP_CHECK_PORT="${HTTP_PORT:-80}"
  if ! "${SCRIPT_DIR}/smoke-test.sh" --base-url "http://127.0.0.1:${HTTP_CHECK_PORT}"; then
    trigger_auto_rollback "post_deploy_smoke_test_failure"
  fi
fi

log "SUCCESS: Production deployment verified and healthy."
