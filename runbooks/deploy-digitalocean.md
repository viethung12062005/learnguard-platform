# Runbook Triển khai Production trên DigitalOcean Droplet VM

> **Phiên bản:** 3.1 (Production Launch Hardened — 2026-11-23)
> **Tham chiếu:** [ADR-0008](../docs/adr/0008-cloud-migration-digitalocean-vm.md), [ADR-0009](../docs/adr/0009-cicd-pipeline-digitalocean-ghcr.md), [Kiến trúc Đích DigitalOcean v3](../docs/architecture/digitalocean-target-architecture.md).

---

## 1. Tổng quan Kiến trúc & Hardening Production

Toàn bộ hệ thống **LearnGuard** vận hành trên **DigitalOcean Droplet VM (Ubuntu 24.04 LTS)** đặt trong mạng riêng **DigitalOcean VPC (`10.116.0.0/20`)** với hai vùng mạng container tách biệt:
- **`lg_frontend_net` (DMZ):** Chỉ gồm `frontend` (Nginx 1.27 phục vụ React SPA + reverse proxy `/api/`) và `api` (FastAPI).
- **`lg_backend_net` (`internal: true` — Private Data Plane):** Gồm `api`, `postgres` (PostgreSQL 16), `ml-worker` (`Data-ML-MLOPS` + `retrain_pipeline.py`), `ollama` (local LLM fallback), và cụm `prometheus`/`node-exporter`/`cadvisor`. **PostgreSQL tuyệt đối không mở cổng `5432` ra ngoài host.**

Các lớp bảo vệ production đã được tích hợp:
- **Memory & Log Protection:** Swap 4 GB (`/swapfile`, `vm.swappiness=10`) và Docker `json-file` log rotation (`max-size: 10m`, `max-file: 5`, `live-restore: true`).
- **Systemd Timers (thay thế cron):** `learnguard-ml-batch.timer` (chạy ML drift & retraining hàng tuần) và `learnguard-db-backup.timer` (sao lưu PostgreSQL hàng ngày lúc `02:30 UTC`, ghi log sạch vào `journalctl`).
- **Fail-Fast Deployment Guard:** `deploy-do.sh` từ chối triển khai nếu phát hiện digest placeholder (`0000...`, `1111...`, `2222...`, `3333...`) hoặc biến `REPLACE_WITH_*` chưa điền trong `.env`.

---

## 2. Bước 1 — Khởi tạo Hạ tầng DigitalOcean (Terraform hoặc Bootstrap Script)

### Phương án A: Khởi tạo tự động qua Terraform (Khuyến nghị)

```bash
cd learnguard-platform/infra/digitalocean
cp terraform.tfvars.example terraform.tfvars
# Chỉnh sửa terraform.tfvars: điền ssh_key_fingerprints, operator_ssh_public_key,
# allowed_ssh_cidrs (và allowed_web_cidrs nếu bật Pre-Auth Exposure Guard)

export DIGITALOCEAN_TOKEN="dop_v1_your_personal_access_token"
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

Sau khi `terraform apply` hoàn tất, lấy địa chỉ IPv4 công khai của Droplet:
```bash
terraform output droplet_public_ipv4
```

### Phương án B: Khởi tạo & Hardening VM bằng `bootstrap-vm.sh`

Nếu bạn tạo Droplet thủ công trên DigitalOcean Control Panel (hoặc cần bổ sung đầy đủ hardening lên VM đã chạy cloud-init), chạy `bootstrap-vm.sh` (thiết kế **idempotent**, hỗ trợ `--dry-run`):

```bash
scp learnguard-platform/scripts/do/bootstrap-vm.sh root@<DROPLET_IP>:/tmp/
ssh root@<DROPLET_IP> "bash /tmp/bootstrap-vm.sh --operator-user lgops"
```

Script tự động thực hiện 8 bước:
1. Tạo user vận hành `lgops` (thuộc nhóm `docker` và `sudo`).
2. Cài đặt Docker Engine, Docker Compose v2, `ufw`, `fail2ban`, `jq`, `rsync`, `git`.
3. Ghi `/etc/docker/daemon.json` (`json-file`, `max-size: "10m"`, `max-file: "5"`, `live-restore: true`) nếu chưa tồn tại.
4. Tạo `/swapfile` dung lượng **4 GB** (`chmod 600`, `mkswap`, `swapon`), lưu bền vững trong `/etc/fstab`, và cấu hình `/etc/sysctl.d/99-learnguard-swap.conf` (`vm.swappiness=10`).
5. Khóa firewall `ufw`: chỉ mở `22/tcp`, `80/tcp`, `443/tcp`; chặn `5432/tcp` và `8000/tcp`.
6. Tạo cây thư mục `/opt/learnguard/{certs,deploy,scripts,data}` (`certs` với `chmod 750` thuộc `lgops:lgops`; `data/{oulad,artifacts}` thuộc `10001:10001`).
7. Cài đặt `learnguard-ml-batch.timer` (chạy kiểm tra drift & retraining vào `06:30 UTC` sáng thứ Hai hàng tuần).
8. Gỡ bỏ cron cũ `/etc/cron.d/learnguard-db-backup` (nếu có) và cài đặt `learnguard-db-backup.service` + `learnguard-db-backup.timer` (chạy hàng ngày lúc `02:30 UTC`, `Persistent=true`, xem log qua `journalctl -u learnguard-db-backup`).

---

## 3. Bước 2 — Khởi tạo Secrets & CI Deploy Key (`init-prod-secrets.sh`)

### 3.1. Sinh `.env` và SSH Deploy Key trên Droplet bằng `init-prod-secrets.sh`

SSH vào Droplet bằng tài khoản `lgops` và chạy script pre-flight (tự động đặt `umask 077`, `chmod 600`, không bao giờ in giá trị secret ra terminal):

```bash
ssh lgops@<DROPLET_IP>
cd /opt/learnguard

# Kiểm tra trước ở chế độ dry-run
./scripts/do/init-prod-secrets.sh --dry-run

# Khởi tạo .env + sinh mật khẩu ngẫu nhiên (POSTGRES_ADMIN_PASSWORD, LG_API_PASSWORD, LG_ML_WRITER_PASSWORD, JWT_SECRET)
# và sinh cặp khóa SSH ed25519 riêng cho GitHub Actions CD
./scripts/do/init-prod-secrets.sh \
  --env-file /opt/learnguard/deploy/digitalocean/.env \
  --template /opt/learnguard/deploy/digitalocean/.env.prod.example \
  --generate-ssh-key ~/.ssh/id_learnguard_ci
```

Sau khi chạy xong:
1. Mở `/opt/learnguard/deploy/digitalocean/.env` và điền thủ công:
   - `LLM_API_KEY` (OpenRouter API key)
   - `CORS_ORIGINS` (ví dụ `https://learnguard.example.com`)
   - `ENABLE_TLS=true` (sau khi cài chứng chỉ TLS ở Bước 4)
2. Thêm public key CI vào `authorized_keys` của `lgops`:
   ```bash
   cat ~/.ssh/id_learnguard_ci.pub >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ```
3. Sao chép nội dung private key `~/.ssh/id_learnguard_ci` vào GitHub Environment Secret `DO_SSH_KEY`, sau đó xóa bản private key tạm nếu không lưu trên VM (`rm -f ~/.ssh/id_learnguard_ci`).

### 3.2. Cấu hình GitHub Environment Secrets (`production`)

Trên GitHub repository `learnguard-platform`, vào **Settings → Environments → `production`** và khai báo các Secrets khớp với `.github/workflows/cd-digitalocean-prod.yml`:

| Tên Secret | Ý nghĩa | Ghi chú khớp Workflow |
| :--- | :--- | :--- |
| `DO_HOST` | Địa chỉ IPv4 công khai của DigitalOcean Droplet | Từ `terraform output droplet_public_ipv4` |
| `DO_USER` | Tài khoản SSH vận hành trên Droplet | Mặc định `lgops` |
| `DO_PORT` | Cổng SSH của Droplet | Mặc định `22` |
| `DO_SSH_KEY` | Private key (`ed25519`) từ `--generate-ssh-key` | Khớp `/home/lgops/.ssh/authorized_keys` |
| `GHCR_READ_TOKEN` | GitHub PAT (quyền `read:packages`) | Dùng cho `docker login ghcr.io` trên VM |

> **Lưu ý về `GHCR_USER`:** Workflow `cd-digitalocean-prod.yml` sử dụng biến **`GHCR_USER: ${{ vars.GHCR_USER || github.repository_owner }}`** khi chạy `docker login ghcr.io` cùng `GHCR_READ_TOKEN`. Nếu PAT `GHCR_READ_TOKEN` thuộc về tài khoản khác với `github.repository_owner`, hãy khai báo thêm **Repository/Environment Variable `GHCR_USER`** khớp với chủ sở hữu PAT đó.

---

## 4. Bước 3 — Thiết lập TLS / HTTPS (`docker-compose.tls.yml` + `nginx.fe.tls.conf`)

Chứng chỉ TLS được lưu tại `/opt/learnguard/certs/` (đã được `bootstrap-vm.sh` tạo với quyền `750`, thuộc `lgops:lgops`). Khi `ENABLE_TLS=true` trong `.env` (hoặc truyền `--tls`) và tồn tại `deploy/digitalocean/docker-compose.tls.yml`, `deploy-do.sh` sẽ tự động ghép `-f docker-compose.tls.yml` (mount `nginx.fe.tls.conf` và thư mục `/opt/learnguard/certs`) vào mọi lệnh `docker compose`.

### Phương án 1 (Khuyến nghị — Zero Renewal): Cloudflare Origin Certificate (`Full (strict)`)

Phù hợp nhất cho production chạy sau Cloudflare DNS proxy vì chứng chỉ có thời hạn tới **15 năm**, không cần cron gia hạn trên VM:
1. Trên Cloudflare Dashboard → **SSL/TLS → Origin Server → Create Certificate** (chọn RSA 2048 hoặc ECDSA, hostname `*.example.com`, `example.com`).
2. Lưu Origin Certificate và Private Key vào `/opt/learnguard/certs/` trên Droplet:
   ```bash
   sudo install -d -o lgops -g lgops -m 750 /opt/learnguard/certs
   # Dán Origin Certificate vào fullchain.pem và Private Key vào privkey.pem
   chmod 644 /opt/learnguard/certs/fullchain.pem
   chmod 600 /opt/learnguard/certs/privkey.pem
   ```
3. Trên Cloudflare Dashboard → **SSL/TLS → Overview**, chọn chế độ mã hóa **`Full (strict)`**.
4. Bật TLS trong `.env`:
   ```bash
   ENABLE_TLS=true
   CORS_ORIGINS=https://learnguard.example.com
   ```

### Phương án 2: Let's Encrypt Certbot (`webroot /var/www/certbot`)

Phù hợp nếu trỏ DNS trực tiếp (DNS-only / không qua Cloudflare proxy):
1. Đảm bảo domain đã trỏ bản ghi `A` về `<DROPLET_IP>` và `nginx.fe.tls.conf` phục vụ ACME challenge tại `/.well-known/acme-challenge/` từ `/var/www/certbot`.
2. Cấp chứng chỉ lần đầu bằng `certbot`:
   ```bash
   sudo apt-get install -y certbot
   sudo mkdir -p /var/www/certbot
   sudo certbot certonly --webroot \
     -w /var/www/certbot \
     -d learnguard.example.com \
     --email ops@learnguard.example.com \
     --agree-tos --no-eff-email
   ```
3. Đồng bộ chứng chỉ sang `/opt/learnguard/certs/` và cấu hình post-renewal hook reload Nginx:
   ```bash
   sudo cp /etc/letsencrypt/live/learnguard.example.com/fullchain.pem /opt/learnguard/certs/fullchain.pem
   sudo cp /etc/letsencrypt/live/learnguard.example.com/privkey.pem /opt/learnguard/certs/privkey.pem
   sudo chown lgops:lgops /opt/learnguard/certs/fullchain.pem /opt/learnguard/certs/privkey.pem
   sudo chmod 644 /opt/learnguard/certs/fullchain.pem
   sudo chmod 600 /opt/learnguard/certs/privkey.pem
   ```
   Tạo hook gia hạn tự động tại `/etc/letsencrypt/renewal-hooks/deploy/reload-learnguard-nginx.sh`:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   cp /etc/letsencrypt/live/learnguard.example.com/fullchain.pem /opt/learnguard/certs/fullchain.pem
   cp /etc/letsencrypt/live/learnguard.example.com/privkey.pem /opt/learnguard/certs/privkey.pem
   chown lgops:lgops /opt/learnguard/certs/fullchain.pem /opt/learnguard/certs/privkey.pem
   chmod 644 /opt/learnguard/certs/fullchain.pem
   chmod 600 /opt/learnguard/certs/privkey.pem
   docker exec lg-frontend nginx -s reload
   ```

---

## 5. Bước 4 — Pre-Auth Exposure Guard (`Q-AUTH`)

> **CẢNH BÁO BẢO MẬT (`Q-AUTH`):** Cho đến khi các ticket **`BE-08` / `BE-09` (JWT Auth & RBAC)** được hoàn thiện và triển khai lên production, **KHÔNG ĐƯỢC mở public Internet không kiểm soát** cho giao diện Dashboard hoặc các API endpoint của LearnGuard.

Trước khi `BE-08`/`BE-09` hoàn tất, bắt buộc áp dụng **ít nhất một** (khuyến nghị cả hai) lớp chắn sau:

### Biện pháp 1: Giới hạn `allowed_web_cidrs` trong `terraform.tfvars` / DigitalOcean Cloud Firewall
Thay vì mở `80/tcp` và `443/tcp` cho `0.0.0.0/0`, chỉ cho phép dải IP văn phòng, VPN trường học hoặc IP người đánh giá trong `infra/digitalocean/terraform.tfvars`:
```hcl
allowed_web_cidrs = [
  "203.0.113.10/32",   # Operator / Reviewer Workstation IP
  "198.51.100.0/24"    # University / VPN Egress CIDR
]
```

### Biện pháp 2: Bật Nginx Basic Auth (`.htpasswd`) ở lớp Reverse Proxy
Sử dụng `init-prod-secrets.sh` để tạo tệp `.htpasswd` an toàn (`openssl passwd -6` / `htpasswd -niB`), ví dụ tại `/opt/learnguard/deploy/docker/.htpasswd` (hoặc `/opt/learnguard/certs/.htpasswd`):
```bash
HTPASSWD_USER=learnguard ./scripts/do/init-prod-secrets.sh \
  --generate-htpasswd /opt/learnguard/deploy/docker/.htpasswd
```
Sau đó tạo `/opt/learnguard/deploy/docker/preauth.inc` theo hướng dẫn trong `deploy/docker/nginx.fe.tls.conf`:
```nginx
satisfy any;
allow 127.0.0.1;
allow ::1;
deny all;
auth_basic "LearnGuard Pre-Auth";
auth_basic_user_file /etc/nginx/conf.d/.htpasswd;
```
Mount `preauth.inc` và `.htpasswd` vào `/etc/nginx/conf.d/` trong `frontend` và bỏ chú thích `include /etc/nginx/conf.d/preauth.inc;` trong `nginx.fe.tls.conf` (cổng `80` `/healthz` và `/.well-known/acme-challenge/` đã tắt `auth_basic off;` sẵn để giữ nguyên healthcheck & Certbot) cho đến khi `BE-08`/`BE-09` đi vào hoạt động.

---

## 6. Bước 5 — Chiến lược GitHub Actions CD và DigitalOcean Cloud Firewall

DigitalOcean Cloud Firewall mặc định chỉ mở cổng `22/tcp` cho `var.allowed_ssh_cidrs`, trong khi GitHub-hosted runner (`ubuntu-latest`) sử dụng dải IP động thay đổi theo từng lần chạy. Chọn một trong các chiến lược sau cho production:

1. **Phương án A (Khuyến nghị cho bảo mật chặt): Tailscale SSH / Private Mesh VPN**
   - Cài Tailscale trên Droplet (`tailscale up --ssh`) và thêm bước `tailscale/github-action` vào CD workflow.
   - Giữ `allowed_ssh_cidrs` trong Terraform chỉ chứa IP tĩnh của operator; cổng `22/tcp` public không bao giờ phải mở cho dải IP GitHub Actions.
2. **Phương án B: Quy tắc Firewall Tạm thời qua `doctl` (Ephemeral Allowlist)**
   - Trong job `deploy-to-digitalocean`, dùng `doctl compute firewall add-rules` mở tạm `$(curl -s https://api.ipify.org)/32` vào cổng `22/tcp` trước bước `ssh-keyscan`, và gỡ bỏ ngay trong bước cleanup `if: always()`.
   - Yêu cầu thêm secret `DIGITALOCEAN_ACCESS_TOKEN` (quyền tối thiểu quản lý Firewall).
3. **Phương án C: Self-Hosted Runner / Bastion IP Tĩnh**
   - Chạy CD trên một self-hosted runner hoặc bastion host có IPv4 tĩnh và khai báo duy nhất `/32` đó vào `allowed_ssh_cidrs`.

---

## 7. Bước 6 — Checklist Quản trị Production trên GitHub Repository

Trước khi kích hoạt triển khai production chính thức, rà soát đủ các cấu hình bảo vệ trên GitHub:

### 7.1. `main` Branch Protection Rules (`Settings → Branches`)
- [ ] Bật **Require a pull request before merging** (tối thiểu **1 approving review**, bật **Dismiss stale pull request approvals when new commits are pushed**).
- [ ] Bật **Require status checks to pass before merging** và chọn bắt buộc:
  - `L1 Guardrails: Shell, Ruff, Compose & Manifests`
  - `L2-L5 Gates: Contracts, Behavioral (MFT/INV/DIR) & Drift Retraining`
- [ ] Bật **Do not allow bypassing the above settings** (áp dụng cho cả admin).
- [ ] Chặn **Allow force pushes** và **Allow deletions**.

### 7.2. GitHub Environment `production` (`Settings → Environments → production`)
- [ ] Bật **Required reviewers** (tối thiểu 1 maintainer duyệt tay trước khi job `deploy-to-digitalocean` được phép SSH lên VM).
- [ ] Giới hạn **Deployment branches and tags**: chỉ cho phép nhánh **`main`** (`Selected branches: main`).
- [ ] Lưu đủ 5 secrets ở cấp **Environment `production`** (không lưu ở repository-level không kiểm soát): `DO_HOST`, `DO_USER`, `DO_PORT`, `DO_SSH_KEY`, `GHCR_READ_TOKEN`.

---

## 8. Bước 7 — Đồng bộ Dữ liệu OULAD, Chạy ML Khởi tạo & Triển khai

### 8.1. Nạp dữ liệu OULAD & khởi tạo Champion Model Release
1. Tải 7 file CSV chuẩn của bộ dữ liệu **OULAD** (`assessments.csv`, `courses.csv`, `studentAssessment.csv`, `studentInfo.csv`, `studentRegistration.csv`, `studentVle.csv`, `vle.csv`) vào `/opt/learnguard/data/oulad/`:
   ```bash
   rsync -avz ./oulad/*.csv lgops@<DROPLET_IP>:/opt/learnguard/data/oulad/
   ssh lgops@<DROPLET_IP> "sudo chown -R 10001:10001 /opt/learnguard/data/oulad /opt/learnguard/data/artifacts"
   ```
2. Kích hoạt chạy pipeline ML lần đầu (khởi tạo `active_release.json`, scorecard `eval-report.v1` và 32.593 dự đoán vào `ml_predictions`):
   ```bash
   ssh lgops@<DROPLET_IP> "cd /opt/learnguard/deploy/digitalocean && \
     docker compose -f docker-compose.prod.yml --profile batch run --rm ml-worker --mode force-retrain"
   ```

### 8.2. Triển khai qua GitHub Actions CD hoặc CLI (`deploy-do.sh`)

- **Qua GitHub Actions:**
  1. Chạy `ci-build-and-scan.yml` để build & quét Trivy 3 image (`learnguard-api`, `learnguard-ml`, `learnguard-fe`).
  2. Cập nhật digest `@sha256:...` mới vào `deploy/releases/prod.yaml` qua Pull Request vào `main`.
  3. Chạy workflow **`CD — Deploy Production to DigitalOcean VM`** (`cd-digitalocean-prod.yml`) và phê duyệt tại Environment `production`.
- **Trực tiếp trên Droplet (khi có bảo trì khẩn cấp):**
  ```bash
  cd /opt/learnguard
  # Tự động nạp docker-compose.tls.yml nếu ENABLE_TLS=true trong .env (hoặc thêm --tls)
  ./scripts/cd/deploy-do.sh --compose-dir /opt/learnguard/deploy/digitalocean
  ```

Trình tự tự động của `deploy-do.sh`:
1. **Fail-fast guard:** Chặn ngay nếu digest là placeholder (`0000...`, `1111...`, `2222...`, `3333...`) hoặc `.env` còn biến `REPLACE_WITH_*`.
2. Lưu release đang chạy vào `/opt/learnguard/deploy/digitalocean/last_good_release.env`.
3. Chạy `backup-db.sh` tạo bản sao lưu `.sql.gz` + `.sha256`.
4. Pull image mới, kiểm tra `lg-postgres` healthy, chạy `init-db.sh` và `db-migrate` (`alembic upgrade head`).
5. Cập nhật `lg-api` và `lg-frontend` (kèm TLS overlay nếu bật), chờ container đạt `healthy`.
6. Chạy `smoke-test.sh`; nếu thất bại, **tự động gọi `rollback-do.sh`** khôi phục release trước đó.

---

## 9. Bước 8 — Kiểm tra Xác nhận Sau Triển khai (Copy-Paste Verification)

Chạy các lệnh sau trực tiếp trên Droplet (`ssh lgops@<DROPLET_IP>`) để xác nhận toàn bộ hệ thống sẵn sàng:

```bash
# 1. Kiểm tra swap (4G) và cấu hình Docker log rotation + live-restore
swapon --show
docker info --format 'Logging={{.LoggingDriver}} LiveRestore={{.LiveRestoreEnabled}}'

# 2. Kiểm tra các systemd timers (ML batch thứ Hai 06:30 UTC & DB backup hàng ngày 02:30 UTC)
systemctl list-timers --all | grep learnguard
journalctl -u learnguard-db-backup -n 30 --no-pager
journalctl -u learnguard-ml-batch -n 30 --no-pager

# 3. Kiểm tra trạng thái tất cả container (thêm -f docker-compose.tls.yml nếu bật TLS)
docker compose -f /opt/learnguard/deploy/digitalocean/docker-compose.prod.yml ps

# 4. Chạy bộ kiểm thử khói E2E (9 hạng mục)
/opt/learnguard/scripts/cd/smoke-test.sh --base-url http://127.0.0.1:80

# 5. (Nếu đã bật TLS) Kiểm tra HTTPS từ bên ngoài với tên miền production
curl -fsSI https://<YOUR_DOMAIN>/healthz
```
