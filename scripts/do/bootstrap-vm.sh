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
#   3. Writes `/etc/docker/daemon.json` (`json-file` log rotation + `live-restore`) if missing
#   4. Provisions idempotent 4 GB `/swapfile` with `vm.swappiness=10`
#   5. Configures UFW host firewall (Allow 22, 80, 443; Deny 5432, 8000, 11434, 9090)
#   6. Creates `/opt/learnguard` hierarchy (`certs` at 750, data UID 10001 ownership)
#   7. Installs systemd timers `learnguard-ml-batch.timer` (weekly Mon 06:30 UTC)
#      and `learnguard-db-backup.timer` (daily 02:30 UTC, journalctl logging).
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
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --operator-user requires a value" >&2
        exit 1
      fi
      OPERATOR_USER="$2"
      shift 2
      ;;
    --root-dir)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --root-dir requires a value" >&2
        exit 1
      fi
      LG_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: sudo bash bootstrap-vm.sh [--dry-run] [--operator-user lgops] [--root-dir /opt/learnguard]"
      exit 0
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
log "1/8 Ensuring operator user '${OPERATOR_USER}' exists..."
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
log "2/8 Installing base packages and Docker Engine..."
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
    ARCH="$(dpkg --print-architecture)"
    echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME} stable" \
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
# 3. Configure Docker Engine Log Rotation & Live-Restore (/etc/docker/daemon.json)
# -----------------------------------------------------------------------------
log "3/8 Configuring Docker daemon log rotation (/etc/docker/daemon.json)..."
DOCKER_DAEMON_JSON="/etc/docker/daemon.json"
if [[ "${DRY_RUN}" == "true" ]]; then
  if [[ -f "${DOCKER_DAEMON_JSON}" ]]; then
    log "[DRY-RUN] ${DOCKER_DAEMON_JSON} already exists; would preserve existing configuration."
  else
    log "[DRY-RUN] Would write ${DOCKER_DAEMON_JSON} (json-file max-size=10m, max-file=5, live-restore=true) and reload Docker."
  fi
else
  if [[ ! -f "${DOCKER_DAEMON_JSON}" ]]; then
    mkdir -p /etc/docker
    cat > "${DOCKER_DAEMON_JSON}" <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "5"
  },
  "live-restore": true
}
EOF
    chmod 0644 "${DOCKER_DAEMON_JSON}"
    if systemctl is-active --quiet docker; then
      systemctl reload docker || systemctl restart docker
    fi
  else
    log "${DOCKER_DAEMON_JSON} already exists; preserving existing configuration."
  fi
fi

# -----------------------------------------------------------------------------
# 4. Provision Idempotent 4 GB Swapfile & Tuned Swappiness
# -----------------------------------------------------------------------------
log "4/8 Ensuring 4 GB /swapfile and vm.swappiness=10 are configured..."
SWAP_FILE="/swapfile"
SYSCTL_SWAP_CONF="/etc/sysctl.d/99-learnguard-swap.conf"
if [[ "${DRY_RUN}" == "true" ]]; then
  log "[DRY-RUN] Would ensure 4 GB ${SWAP_FILE} (fallocate -l 4G, chmod 600, mkswap, swapon), persist in /etc/fstab, and set vm.swappiness=10 in ${SYSCTL_SWAP_CONF}."
else
  if [[ ! -f "${SWAP_FILE}" ]]; then
    fallocate -l 4G "${SWAP_FILE}" || dd if=/dev/zero of="${SWAP_FILE}" bs=1M count=4096 status=none
    chmod 0600 "${SWAP_FILE}"
    mkswap "${SWAP_FILE}"
  else
    chmod 0600 "${SWAP_FILE}"
  fi

  if ! swapon --show=NAME --noheadings 2>/dev/null | grep -qx "${SWAP_FILE}"; then
    swapon "${SWAP_FILE}"
  fi

  if ! grep -qs "^${SWAP_FILE}[[:space:]]" /etc/fstab; then
    echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
  fi

  if [[ ! -f "${SYSCTL_SWAP_CONF}" ]] || ! grep -qs '^vm\.swappiness=10$' "${SYSCTL_SWAP_CONF}"; then
    printf 'vm.swappiness=10\n' > "${SYSCTL_SWAP_CONF}"
    chmod 0644 "${SYSCTL_SWAP_CONF}"
  fi
  sysctl -p "${SYSCTL_SWAP_CONF}" >/dev/null
fi

# -----------------------------------------------------------------------------
# 5. Configure UFW Host Firewall & Fail2ban
# -----------------------------------------------------------------------------
log "5/8 Configuring UFW host firewall and Fail2ban..."
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
# 6. Mount Block Storage (if attached) & Create /opt/learnguard directory layout
# -----------------------------------------------------------------------------
log "6/8 Checking DigitalOcean Block Storage volume and creating directory hierarchy under ${LG_ROOT}..."
DATA_MOUNT="${LG_ROOT}/data"
run_cmd mkdir -p "${DATA_MOUNT}"

DO_VOL="$(find /dev/disk/by-id -maxdepth 1 -name 'scsi-0DO_Volume_*' 2>/dev/null | head -n 1 || true)"
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
  "${LG_ROOT}/certs"
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
  chmod 0750 "${LG_ROOT}/certs"
  # Container non-root user `learnguard` runs as UID 10001
  chown -R 10001:10001 "${LG_ROOT}/data/oulad" "${LG_ROOT}/data/artifacts"
else
  log "[DRY-RUN] Would set ownership ${OPERATOR_USER}:${OPERATOR_USER} on ${LG_ROOT}, chmod 750 ${LG_ROOT}/certs, and UID 10001 on data dirs"
fi

# -----------------------------------------------------------------------------
# 7. Configure Systemd Service & Timer for Weekly Drift & Retraining Pipeline
# -----------------------------------------------------------------------------
log "7/8 Configuring systemd service and timer (learnguard-ml-batch)..."
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
# 8. Configure Daily Automated PostgreSQL Backup Systemd Timer (Journal Logging)
# -----------------------------------------------------------------------------
log "8/8 Replacing legacy cron job with systemd timer (learnguard-db-backup)..."
if [[ "${DRY_RUN}" == "false" ]]; then
  # Remove legacy cron job that attempted to write to root-owned /var/log/learnguard-backup.log
  rm -f /etc/cron.d/learnguard-db-backup

  cat > /etc/systemd/system/learnguard-db-backup.service <<EOF
[Unit]
Description=LearnGuard Daily Automated PostgreSQL Backup
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=${OPERATOR_USER}
WorkingDirectory=${LG_ROOT}
ExecStart=${LG_ROOT}/scripts/cd/backup-db.sh --compose-dir ${LG_ROOT}/deploy/digitalocean
StandardOutput=journal
StandardError=journal
SyslogIdentifier=learnguard-db-backup
EOF

  cat > /etc/systemd/system/learnguard-db-backup.timer <<EOF
[Unit]
Description=Run LearnGuard Daily PostgreSQL Backup at 02:30 UTC

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  systemctl enable --now learnguard-db-backup.timer
else
  log "[DRY-RUN] Would remove /etc/cron.d/learnguard-db-backup and write /etc/systemd/system/learnguard-db-backup.{service,timer} (daily 02:30 UTC, Persistent=true)"
fi

log "Bootstrap completed successfully."
