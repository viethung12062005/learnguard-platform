#!/usr/bin/env bash
# =============================================================================
# LearnGuard — Production Secrets & Operator Pre-Flight Helper (DigitalOcean)
#
# Usage:
#   ./init-prod-secrets.sh [options]
#
# Options:
#   --env-file <path>           Target .env path (default: /opt/learnguard/deploy/digitalocean/.env)
#   --template <path>           Template .env.prod.example path (default: deploy/digitalocean/.env.prod.example)
#   --generate-ssh-key <path>   Optional: generate passwordless ed25519 CI/CD deploy key
#   --generate-htpasswd <path>  Optional: generate Nginx pre-auth .htpasswd file
#   --htpasswd-user <username>  Username for .htpasswd entry (default: learnguard)
#   --dry-run                   Preview actions without creating or modifying files
#   -h, --help                  Show this help message
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

ENV_FILE="/opt/learnguard/deploy/digitalocean/.env"
TEMPLATE_FILE="${PLATFORM_ROOT}/deploy/digitalocean/.env.prod.example"
SSH_KEY_PATH=""
HTPASSWD_PATH=""
HTPASSWD_USER="${HTPASSWD_USER:-learnguard}"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --env-file requires a path" >&2
        exit 1
      fi
      ENV_FILE="$2"
      shift 2
      ;;
    --template)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --template requires a path" >&2
        exit 1
      fi
      TEMPLATE_FILE="$2"
      shift 2
      ;;
    --generate-ssh-key)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --generate-ssh-key requires a path" >&2
        exit 1
      fi
      SSH_KEY_PATH="$2"
      shift 2
      ;;
    --generate-htpasswd)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --generate-htpasswd requires a path" >&2
        exit 1
      fi
      HTPASSWD_PATH="$2"
      shift 2
      ;;
    --htpasswd-user)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --htpasswd-user requires a username" >&2
        exit 1
      fi
      HTPASSWD_USER="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      sed -n '2,18p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

log() {
  echo "[init-prod-secrets] $(date -u +"%Y-%m-%dT%H:%M:%SZ") - $*"
}

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  log "ERROR: Template file not found at ${TEMPLATE_FILE}"
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  log "ERROR: openssl is required to generate cryptographic secrets."
  exit 1
fi

# Read raw value for a key from an env file without sourcing or printing it
get_env_value() {
  local key="$1"
  local file="$2"
  awk -v k="${key}" '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
    index($0, k "=") == 1 {
      print substr($0, length(k) + 2)
      exit
    }
  ' "${file}"
}

# Atomically set key=value using environment variable so secret never appears in argv/ps
set_env_secret_from_env() {
  local key="$1"
  local file="$2"
  local tmp_file
  tmp_file="$(mktemp)"
  awk -v k="${key}" '
    BEGIN { found = 0; val = ENVIRON["LG_SECRET_VALUE"] }
    index($0, k "=") == 1 { print k "=" val; found = 1; next }
    { print }
    END { if (!found) print k "=" val }
  ' "${file}" > "${tmp_file}"
  chmod 0600 "${tmp_file}"
  mv "${tmp_file}" "${file}"
}

SECRET_KEYS=(
  "POSTGRES_ADMIN_PASSWORD"
  "LG_API_PASSWORD"
  "LG_ML_WRITER_PASSWORD"
  "JWT_SECRET"
)

# Restrict default permissions for all created files/dirs
umask 077

# -----------------------------------------------------------------------------
# 1. Initialize .env from template and populate cryptographic secrets
# -----------------------------------------------------------------------------
log "1/4 Initializing production environment file (${ENV_FILE})..."
if [[ "${DRY_RUN}" == "true" ]]; then
  if [[ -f "${ENV_FILE}" ]]; then
    log "[DRY-RUN] ${ENV_FILE} already exists; would enforce chmod 600 and populate only remaining REPLACE_WITH_* secret keys."
  else
    log "[DRY-RUN] Would copy ${TEMPLATE_FILE} -> ${ENV_FILE} with umask 077 and chmod 600."
  fi
  for key in "${SECRET_KEYS[@]}"; do
    log "[DRY-RUN] Would ensure ${key} has a cryptographically random value (openssl rand -hex 24; value never printed)."
  done
else
  mkdir -p "$(dirname "${ENV_FILE}")"
  if [[ ! -f "${ENV_FILE}" ]]; then
    cp "${TEMPLATE_FILE}" "${ENV_FILE}"
    chmod 0600 "${ENV_FILE}"
    log "Created ${ENV_FILE} from ${TEMPLATE_FILE} (mode 600)."
  else
    chmod 0600 "${ENV_FILE}"
    log "Using existing ${ENV_FILE} (enforced mode 600); existing non-placeholder secrets will be preserved."
  fi

  for key in "${SECRET_KEYS[@]}"; do
    current_val="$(get_env_value "${key}" "${ENV_FILE}")"
    if [[ -z "${current_val}" || "${current_val}" == REPLACE_WITH_* ]]; then
      if [[ "${key}" == "JWT_SECRET" ]]; then
        LG_SECRET_VALUE="$(openssl rand -hex 32)"
      else
        LG_SECRET_VALUE="$(openssl rand -hex 24)"
      fi
      export LG_SECRET_VALUE
      set_env_secret_from_env "${key}" "${ENV_FILE}"
      unset LG_SECRET_VALUE
      log "Generated strong random secret for ${key} (value redacted)."
    else
      log "${key} is already set (preserved)."
    fi
  done
fi

# -----------------------------------------------------------------------------
# 2. Validate remaining REPLACE_WITH_* placeholders
# -----------------------------------------------------------------------------
log "2/4 Validating placeholders in environment configuration..."
INSPECT_FILE="${ENV_FILE}"
if [[ "${DRY_RUN}" == "true" && ! -f "${ENV_FILE}" ]]; then
  INSPECT_FILE="${TEMPLATE_FILE}"
fi

UNRESOLVED_KEYS=()
LLM_KEY_NEEDS_MANUAL=false

while IFS= read -r line || [[ -n "${line}" ]]; do
  [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
  if [[ "${line}" == *=* ]]; then
    k="${line%%=*}"
    v="${line#*=}"
    if [[ "${v}" == *REPLACE_WITH_* ]]; then
      if [[ "${k}" == "LLM_API_KEY" ]]; then
        LLM_KEY_NEEDS_MANUAL=true
      elif [[ "${DRY_RUN}" == "true" ]] && [[ " ${SECRET_KEYS[*]} " == *" ${k} "* ]]; then
        continue
      else
        UNRESOLVED_KEYS+=("${k}")
      fi
    fi
  fi
done < "${INSPECT_FILE}"

if [[ "${#UNRESOLVED_KEYS[@]}" -gt 0 ]]; then
  log "ERROR: Unresolved REPLACE_WITH_* placeholder(s) remain for key(s): ${UNRESOLVED_KEYS[*]}"
  exit 1
fi

if [[ "${LLM_KEY_NEEDS_MANUAL}" == "true" ]]; then
  log "ACTION REQUIRED: Manually edit ${ENV_FILE} and replace LLM_API_KEY with your OpenRouter API key."
else
  log "All REPLACE_WITH_* placeholders are resolved (including LLM_API_KEY)."
fi

# -----------------------------------------------------------------------------
# 3. Optional: Generate CI/CD SSH Deploy Key & Nginx Pre-Auth .htpasswd
# -----------------------------------------------------------------------------
log "3/4 Processing optional operator credential helpers..."
if [[ -n "${SSH_KEY_PATH}" ]]; then
  if [[ "${DRY_RUN}" == "true" ]]; then
    log "[DRY-RUN] Would generate passwordless ed25519 SSH deploy key at ${SSH_KEY_PATH} (and ${SSH_KEY_PATH}.pub)."
  else
    if [[ -e "${SSH_KEY_PATH}" ]]; then
      log "SSH deploy key already exists at ${SSH_KEY_PATH} (preserved)."
    else
      if ! command -v ssh-keygen >/dev/null 2>&1; then
        log "ERROR: ssh-keygen is required for --generate-ssh-key."
        exit 1
      fi
      mkdir -p "$(dirname "${SSH_KEY_PATH}")"
      ssh-keygen -t ed25519 -N "" -C "learnguard-github-cd" -f "${SSH_KEY_PATH}" >/dev/null
      chmod 0600 "${SSH_KEY_PATH}"
      chmod 0644 "${SSH_KEY_PATH}.pub"
      log "Generated CI/CD ed25519 deploy key pair at ${SSH_KEY_PATH}{,.pub}."
      log "  -> Append ${SSH_KEY_PATH}.pub to /home/lgops/.ssh/authorized_keys on the Droplet."
      log "  -> Store the contents of ${SSH_KEY_PATH} in GitHub Environment 'production' secret DO_SSH_KEY."
    fi
  fi
else
  log "Skipping SSH deploy key generation (--generate-ssh-key not specified)."
fi

if [[ -n "${HTPASSWD_PATH}" ]]; then
  if [[ "${DRY_RUN}" == "true" ]]; then
    log "[DRY-RUN] Would generate Nginx pre-auth .htpasswd entry for user '${HTPASSWD_USER}' at ${HTPASSWD_PATH}."
  else
    HTPASSWD_INPUT="${HTPASSWD_PASSWORD:-}"
    if [[ -z "${HTPASSWD_INPUT}" ]]; then
      if [[ -t 0 ]]; then
        printf "Enter Nginx Basic Auth password for user '%s': " "${HTPASSWD_USER}" >&2
        read -rs HTPASSWD_INPUT
        printf "\n" >&2
      else
        log "ERROR: Set HTPASSWD_PASSWORD env var or run interactively when using --generate-htpasswd."
        exit 1
      fi
    fi
    if [[ -z "${HTPASSWD_INPUT}" ]]; then
      log "ERROR: Empty password is not permitted for .htpasswd."
      exit 1
    fi

    mkdir -p "$(dirname "${HTPASSWD_PATH}")"
    TMP_HT="$(mktemp)"
    if command -v htpasswd >/dev/null 2>&1; then
      printf '%s\n' "${HTPASSWD_INPUT}" | htpasswd -niB "${HTPASSWD_USER}" > "${TMP_HT}"
    else
      HASHED_PW="$(printf '%s\n' "${HTPASSWD_INPUT}" | openssl passwd -6 -stdin)"
      printf '%s:%s\n' "${HTPASSWD_USER}" "${HASHED_PW}" > "${TMP_HT}"
      unset HASHED_PW
    fi
    unset HTPASSWD_INPUT
    # World-readable 0644 (hashes only) so non-root nginx worker (UID 101) can read when bind-mounted :ro
    chmod 0644 "${TMP_HT}"
    mv "${TMP_HT}" "${HTPASSWD_PATH}"
    log "Generated Nginx Basic Auth file at ${HTPASSWD_PATH} for user '${HTPASSWD_USER}'."
  fi
else
  log "Skipping Nginx .htpasswd generation (--generate-htpasswd not specified)."
fi

# -----------------------------------------------------------------------------
# 4. Print GitHub Environment 'production' Secrets Checklist
# -----------------------------------------------------------------------------
log "4/4 Pre-flight complete. Configure the following GitHub Environment 'production' secrets:"
cat <<'EOF'

GitHub Repository -> Settings -> Environments -> production -> Environment secrets:
  [ ] DO_HOST          Public IPv4 of the DigitalOcean Droplet (from `terraform output droplet_public_ipv4`)
  [ ] DO_USER          SSH operator username on the Droplet (default: `lgops`)
  [ ] DO_PORT          SSH port on the Droplet (default: `22`)
  [ ] DO_SSH_KEY       Private ed25519 deploy key matching `/home/lgops/.ssh/authorized_keys`
  [ ] GHCR_READ_TOKEN  GitHub PAT (`read:packages`) used by Droplet to pull private GHCR images

Operator manual follow-ups in .env before first deploy:
  [ ] Set `LLM_API_KEY` (OpenRouter API key) in `.env`
  [ ] Set `CORS_ORIGINS` to your production domain (e.g. `https://learnguard.example.com`)
  [ ] Set `ENABLE_TLS=true` in `.env` once certificates are placed in `/opt/learnguard/certs/`

EOF
