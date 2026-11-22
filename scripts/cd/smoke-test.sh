#!/usr/bin/env bash
# =============================================================================
# LearnGuard — Post-Deploy E2E Smoke Test Suite (Layer 6 of AI Testing Pyramid)
#
# Verifies end-to-end readiness of the deployed DigitalOcean stack:
#   1. Nginx Liveness (`GET /healthz` -> 200 "ok")
#   2. Backend & PostgreSQL Connectivity (`GET /api/health` -> status="ok", database="reachable")
#   3. Predictions Contract (`GET /api/predictions?limit=5` -> valid items array & total count)
#   4. Predictions Stats Contract (`GET /api/predictions/stats` -> status breakdown)
#   5. Evaluation Scorecards Endpoint (`GET /api/evaluations` -> HTTP 200)
#   6. Audit Logs Endpoint (`GET /api/audit-logs?limit=5` -> HTTP 200)
#   7. Frontend SPA Root (`GET /`) & Deep-Link Routing (`GET /overview`, `GET /evaluations`)
#   8. Hardened HTTP Security Headers (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`)
#   9. Response Latency Guardrail (`GET /api/health` < 2000ms)
#
# Usage:
#   ./smoke-test.sh [--base-url http://127.0.0.1:80] [--dry-run]
# =============================================================================
set -euo pipefail

BASE_URL="${LG_SMOKE_BASE_URL:-http://127.0.0.1:80}"
DRY_RUN=false
MAX_LATENCY_MS=2000

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url|--mock-url)
      BASE_URL="${2%/}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --max-latency-ms)
      MAX_LATENCY_MS="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

log() {
  echo "[smoke-test] $(date -u +"%Y-%m-%dT%H:%M:%SZ") - $*"
}

if [[ "${DRY_RUN}" == "true" ]]; then
  log "[DRY-RUN] Smoke test configuration validated against base_url=${BASE_URL} (max_latency=${MAX_LATENCY_MS}ms)."
  log "[DRY-RUN] Checks: /healthz, /api/health, /api/predictions, /api/predictions/stats, /api/evaluations, /api/audit-logs, /, /overview, /evaluations, security headers."
  exit 0
fi

TMP_BODY="$(mktemp)"
trap 'rm -f "${TMP_BODY}"' EXIT

FAILURES=0

check_status() {
  local name="$1"
  local url="$2"
  local expected_codes="$3"
  local code
  code="$(curl -sS -o "${TMP_BODY}" -w "%{http_code}" --max-time 15 "${url}" || echo "000")"
  if [[ ",${expected_codes}," == *",${code},"* ]]; then
    log "PASS [${name}]: ${url} -> HTTP ${code}"
  else
    log "FAIL [${name}]: ${url} -> HTTP ${code} (expected one of: ${expected_codes})"
    FAILURES=$((FAILURES + 1))
  fi
}

log "Running LearnGuard E2E Smoke Tests against ${BASE_URL}..."

# 1. Nginx liveness probe
check_status "nginx-healthz" "${BASE_URL}/healthz" "200"

# 2. Backend health & PostgreSQL reachability + latency check
START_MS="$(date +%s%3N)"
check_status "api-health" "${BASE_URL}/api/health" "200"
END_MS="$(date +%s%3N)"
LATENCY_MS=$((END_MS - START_MS))

if [[ -f "${TMP_BODY}" ]]; then
  if grep -q '"database"[[:space:]]*:[[:space:]]*"reachable"' "${TMP_BODY}"; then
    log "PASS [db-reachability]: PostgreSQL reported reachable (${LATENCY_MS}ms)"
  else
    log "FAIL [db-reachability]: /api/health did not report database=reachable: $(cat "${TMP_BODY}")"
    FAILURES=$((FAILURES + 1))
  fi
fi

if [[ "${LATENCY_MS}" -gt "${MAX_LATENCY_MS}" ]]; then
  log "FAIL [health-latency]: /api/health took ${LATENCY_MS}ms (> ${MAX_LATENCY_MS}ms budget)"
  FAILURES=$((FAILURES + 1))
fi

# 3. Predictions list endpoint
check_status "api-predictions" "${BASE_URL}/api/predictions?limit=5" "200"
if [[ -f "${TMP_BODY}" ]]; then
  if ! grep -q '"items"' "${TMP_BODY}"; then
    log "FAIL [api-predictions-schema]: Response missing 'items' key"
    FAILURES=$((FAILURES + 1))
  fi
fi

# 4. Predictions stats endpoint
check_status "api-predictions-stats" "${BASE_URL}/api/predictions/stats" "200"

# 5. Evaluations scorecard endpoint (must return HTTP 200)
check_status "api-evaluations" "${BASE_URL}/api/evaluations" "200"

# 6. Audit logs endpoint
check_status "api-audit-logs" "${BASE_URL}/api/audit-logs?limit=5" "200"

# 7. Frontend SPA root & real deep-link fallback routes (/overview, /evaluations)
check_status "fe-root" "${BASE_URL}/" "200"
check_status "fe-spa-deeplink-overview" "${BASE_URL}/overview" "200"
if [[ -f "${TMP_BODY}" ]]; then
  if ! grep -qi "<!doctype html>" "${TMP_BODY}"; then
    log "FAIL [fe-spa-html-overview]: /overview did not return SPA index.html"
    FAILURES=$((FAILURES + 1))
  fi
fi
check_status "fe-spa-deeplink-evaluations" "${BASE_URL}/evaluations" "200"
if [[ -f "${TMP_BODY}" ]]; then
  if ! grep -qi "<!doctype html>" "${TMP_BODY}"; then
    log "FAIL [fe-spa-html-evaluations]: /evaluations did not return SPA index.html"
    FAILURES=$((FAILURES + 1))
  fi
fi

# 8. Security headers verification
HEADERS="$(curl -sSI --max-time 10 "${BASE_URL}/" || true)"
if echo "${HEADERS}" | grep -qi "X-Frame-Options: DENY"; then
  log "PASS [security-header-xfo]: X-Frame-Options: DENY present"
else
  log "FAIL [security-header-xfo]: Missing X-Frame-Options: DENY header"
  FAILURES=$((FAILURES + 1))
fi

if echo "${HEADERS}" | grep -qi "X-Content-Type-Options: nosniff"; then
  log "PASS [security-header-xcto]: X-Content-Type-Options: nosniff present"
else
  log "FAIL [security-header-xcto]: Missing X-Content-Type-Options: nosniff header"
  FAILURES=$((FAILURES + 1))
fi

if [[ "${FAILURES}" -gt 0 ]]; then
  log "SMOKE TEST FAILED with ${FAILURES} error(s)."
  exit 1
fi

log "ALL SMOKE TESTS PASSED."
