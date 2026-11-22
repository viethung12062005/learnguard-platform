#!/usr/bin/env bash
# =============================================================================
# LearnGuard — Idempotent DigitalOcean Droplet VM Bootstrap Script
#
# Target OS: Ubuntu 22.04 LTS / 24.04 LTS
# Usage:
#   sudo bash bootstrap-vm.sh [--dry-run] [--operator-user lgops]
#
# Responsibilities:
#   1. Creates non-root operations user (`lgops`) with Docker & sudo permissions
#   2. Installs Docker Engine + Docker Compose v2 plugin, UFW, Fail2ban, jq, rsync
#   3. Configures UFW host firewall (Allow 22, 80, 443; Deny 5432, 8000, 11434, 9090)
#   4. Creates standardized `/opt/learnguard` directory hierarchy with UID 10001 ownership
#   5. Installs systemd timer `learnguard-ml-batch.timer` (weekly drift & retraining)
#      and daily PostgreSQL backup cron job (`/etc/cron.d/learnguard-db-backup`).
# =============================================================================
set -euo pipefail

DRY_RUN=false
OPERATOR_USER="lgops"
LG_ROOT="/opt/learnguard"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --operator-user)
      OPERATOR_USER="$2"
      shift 2
      ;;
    --root-dir)
      LG_ROOT="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

log() {
  echo "[bootstrap-vm] $(date -u +"%Y-%m-%dT%H:%M:%SZ") - $*"
}

run_cmd() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    log "[DRY-RUN] $*"
  else
    "$@"
  fi
}

log "Starting LearnGuard DigitalOcean Droplet bootstrap (operator=${OPERATOR_USER}, root=${LG_ROOT}, dry_run=${DRY_RUN})"

if [[ "${DRY_RUN}" == "false" && "${EUID}" -ne 0 ]]; then
  echo "ERROR: bootstrap-vm.sh must be executed as root (or with sudo)." >&2
  exit 1
fi

# -----------------------------------------------------------------------------
# 1. Create non-root operator user
# -----------------------------------------------------------------------------
log "1/6 Ensuring operator user '${OPERATOR_USER}' exists..."
if ! id -u "${OPERATOR_USER}" >/dev/null 2>&1; then
  run_cmd useradd --create-home --shell /bin/bash --groups sudo "${OPERATOR_USER}"
fi

if [[ "${DRY_RUN}" == "false" ]]; then
  echo "${OPERATOR_USER} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-${OPERATOR_USER}"
  chmod 0440 "/etc/sudoers.d/90-${OPERATOR_USER}"
  if [[ -f /root/.ssh/authorized_keys ]]; then
    mkdir -p "/home/${OPERATOR_USER}/.ssh"
    cp -n /root/.ssh/authorized_keys "/home/${OPERATOR_USER}/.ssh/authorized_keys" || true
    chown -R "${OPERATOR_USER}:${OPERATOR_USER}" "/home/${OPERATOR_USER}/.ssh"
    chmod 0700 "/home/${OPERATOR_USER}/.ssh"
    chmod 0600 "/home/${OPERATOR_USER}/.ssh/authorized_keys" || true
  fi
fi

# -----------------------------------------------------------------------------
# 2. Install OS packages and Docker Engine + Compose v2
# -----------------------------------------------------------------------------
log "2/6 Installing base packages and Docker Engine..."
if [[ "${DRY_RUN}" == "false" ]]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg lsb-release ufw fail2ban jq rsync git

  if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    # shellcheck disable=SC1091
    UBUNTU_CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME} stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi

  usermod -aG docker "${OPERATOR_USER}"
  systemctl enable --now docker
else
  log "[DRY-RUN] Would install ca-certificates, curl, ufw, fail2ban, jq, rsync, docker-ce, docker-compose-plugin"
fi

# -----------------------------------------------------------------------------
# 3. Configure UFW Host Firewall & Fail2ban
# -----------------------------------------------------------------------------
log "3/6 Configuring UFW host firewall and Fail2ban..."
if [[ "${DRY_RUN}" == "false" ]]; then
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow 22/tcp comment 'SSH Operator and GitHub Actions CI'
  ufw allow 80/tcp comment 'HTTP Nginx Reverse Proxy'
  ufw allow 443/tcp comment 'HTTPS Nginx Reverse Proxy'
  ufw deny 5432/tcp comment 'Block external PostgreSQL access'
  ufw deny 8000/tcp comment 'Block direct FastAPI access'
  ufw --force enable
  systemctl enable --now fail2ban
else
  log "[DRY-RUN] Would configure UFW (allow 22,80,443; deny 5432,8000) and enable fail2ban"
fi

# -----------------------------------------------------------------------------
# 4. Mount Block Storage (if attached) & Create /opt/learnguard directory layout
# -----------------------------------------------------------------------------
log "4/6 Checking DigitalOcean Block Storage volume and creating directory hierarchy under ${LG_ROOT}..."
DATA_MOUNT="${LG_ROOT}/data"
run_cmd mkdir -p "${DATA_MOUNT}"

DO_VOL="$(ls /dev/disk/by-id/scsi-0DO_Volume_* 2>/dev/null | head -n 1 || true)"
if [[ -n "${DO_VOL}" && -e "${DO_VOL}" ]]; then
  if [[ "${DRY_RUN}" == "true" ]]; then
    log "[DRY-RUN] Would format (if unformatted), add fstab entry, and mount ${DO_VOL} -> ${DATA_MOUNT}"
  else
    if ! blkid "${DO_VOL}" >/dev/null 2>&1; then
      mkfs.ext4 -F "${DO_VOL}"
    fi
    if ! grep -qs " ${DATA_MOUNT} " /etc/fstab; then
      echo "${DO_VOL} ${DATA_MOUNT} ext4 defaults,nofail,discard,noatime 0 2" >> /etc/fstab
    fi
    if ! mountpoint -q "${DATA_MOUNT}"; then
      mount "${DATA_MOUNT}"
    fi
  fi
fi

DIRS=(
  "${LG_ROOT}/deploy/digitalocean"
  "${LG_ROOT}/deploy/docker"
  "${LG_ROOT}/deploy/db"
  "${LG_ROOT}/deploy/ml"
  "${LG_ROOT}/deploy/releases"
  "${LG_ROOT}/scripts/cd"
  "${LG_ROOT}/scripts/do"
  "${LG_ROOT}/data/oulad"
  "${LG_ROOT}/data/backups"
  "${LG_ROOT}/data/artifacts/ingestion_m1"
  "${LG_ROOT}/data/artifacts/feature_snapshot_m2"
  "${LG_ROOT}/data/artifacts/preprocessing-runs"
  "${LG_ROOT}/data/artifacts/model-runs"
  "${LG_ROOT}/data/artifacts/model-releases"
  "${LG_ROOT}/data/artifacts/prediction-batches"
  "${LG_ROOT}/data/artifacts/evaluations"
  "${LG_ROOT}/data/artifacts/drift-reports"
)

for dir in "${DIRS[@]}"; do
  run_cmd mkdir -p "${dir}"
done

if [[ "${DRY_RUN}" == "false" ]]; then
  chown -R "${OPERATOR_USER}:${OPERATOR_USER}" "${LG_ROOT}"
  # Container non-root user `learnguard` runs as UID 10001
  chown -R 10001:10001 "${LG_ROOT}/data/oulad" "${LG_ROOT}/data/artifacts"
fi

# -----------------------------------------------------------------------------
# 5. Configure Systemd Service & Timer for Weekly Drift & Retraining Pipeline
# -----------------------------------------------------------------------------
log "5/6 Configuring systemd service and timer (learnguard-ml-batch)..."
if [[ "${DRY_RUN}" == "false" ]]; then
  cat > /etc/systemd/system/learnguard-ml-batch.service <<EOF
[Unit]
Description=LearnGuard Weekly Drift Detection & Continual Retraining Pipeline
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=${OPERATOR_USER}
WorkingDirectory=${LG_ROOT}/deploy/digitalocean
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml --profile batch run --rm ml-worker --mode auto
StandardOutput=journal
StandardError=journal
EOF

  cat > /etc/systemd/system/learnguard-ml-batch.timer <<EOF
[Unit]
Description=Run LearnGuard Drift & Retraining Pipeline every Monday at 06:30 UTC

[Timer]
OnCalendar=Mon *-*-* 06:30:00
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  systemctl enable --now learnguard-ml-batch.timer
else
  log "[DRY-RUN] Would write /etc/systemd/system/learnguard-ml-batch.{service,timer}"
fi

# -----------------------------------------------------------------------------
# 6. Configure Daily Automated PostgreSQL Backup Cron Job
# -----------------------------------------------------------------------------
log "6/6 Installing daily database backup cron job..."
if [[ "${DRY_RUN}" == "false" ]]; then
  cat > /etc/cron.d/learnguard-db-backup <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
15 2 * * * ${OPERATOR_USER} ${LG_ROOT}/scripts/cd/backup-db.sh >> /var/log/learnguard-backup.log 2>&1
EOF
  chmod 0644 /etc/cron.d/learnguard-db-backup
else
  log "[DRY-RUN] Would write /etc/cron.d/learnguard-db-backup"
fi

log "Bootstrap completed successfully."
