# Runbook Triển khai Production trên DigitalOcean Droplet VM

> **Phiên bản:** 3.0 (2026-11-23)
> **Tham chiếu:** [ADR-0008](../../docs/adr/0008-cloud-migration-digitalocean-vm.md), [ADR-0009](../../docs/adr/0009-cicd-pipeline-digitalocean-ghcr.md), [Kiến trúc Đích DigitalOcean v3](../../docs/architecture/digitalocean-target-architecture.md).

---

## 1. Tổng quan Kiến trúc Triển khai

Toàn bộ hệ thống **LearnGuard** vận hành trên **DigitalOcean Droplet VM (Ubuntu 24.04 LTS)** đặt trong mạng riêng **DigitalOcean VPC (`10.116.0.0/20`)** với hai vùng mạng container tách biệt:
- **`lg_frontend_net` (DMZ):** Chỉ gồm `frontend` (Nginx 1.27 phục vụ React SPA + reverse proxy `/api/`) và `api` (FastAPI).
- **`lg_backend_net` (`internal: true` — Private Data Plane):** Gồm `api`, `postgres` (PostgreSQL 16), `ml-worker` (`Data-ML-MLOPS` + `retrain_pipeline.py`), `ollama` (local LLM fallback), và cụm `prometheus`/`node-exporter`/`cadvisor`. **PostgreSQL tuyệt đối không mở cổng `5432` ra ngoài host.**

---

## 2. Bước 1 — Khởi tạo Hạ tầng DigitalOcean (Terraform hoặc Bootstrap Script)

### Phương án A: Khởi tạo tự động qua Terraform (Khuyến nghị)

```bash
cd learnguard-platform/infra/digitalocean
cp terraform.tfvars.example terraform.tfvars
# Chỉnh sửa terraform.tfvars: điền ssh_key_fingerprints, operator_ssh_public_key, allowed_ssh_cidrs

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

### Phương án B: Khởi tạo trên Droplet Ubuntu 24.04 đã tạo sẵn

Nếu bạn tạo Droplet thủ công trên giao diện DigitalOcean Control Panel, hãy chạy script `bootstrap-vm.sh` (thiết kế **idempotent**, chạy lặp lại an toàn):

```bash
scp learnguard-platform/scripts/do/bootstrap-vm.sh root@<DROPLET_IP>:/tmp/
ssh root@<DROPLET_IP> "bash /tmp/bootstrap-vm.sh --operator-user lgops"
```

Script này tự động:
1. Tạo user vận hành `lgops` (thuộc nhóm `docker` và `sudo`).
2. Cài đặt Docker Engine, Docker Compose v2, `ufw`, `fail2ban`, `jq`, `rsync`.
3. Khóa firewall `ufw`: chỉ mở `22/tcp`, `80/tcp`, `443/tcp`; chặn `5432/tcp` và `8000/tcp`.
4. Tạo cây thư mục chuẩn `/opt/learnguard/{deploy,scripts,data}` và gán quyền `10001:10001` cho `/opt/learnguard/data/{oulad,artifacts}` (khớp với non-root user `learnguard` trong container).
5. Cài đặt `learnguard-ml-batch.timer` (chạy kiểm tra drift & retraining vào `06:30 UTC` sáng thứ Hai hàng tuần) và cron sao lưu PostgreSQL hàng ngày lúc `02:15 UTC`.

---

## 3. Bước 2 — Cấu hình File `.env` trên DigitalOcean VM và GitHub Secrets

### 3.1. Tạo file `/opt/learnguard/deploy/digitalocean/.env` trên Droplet

SSH vào Droplet bằng tài khoản `lgops`:

```bash
ssh lgops@<DROPLET_IP>
cp /opt/learnguard/deploy/digitalocean/.env.prod.example /opt/learnguard/deploy/digitalocean/.env
chmod 600 /opt/learnguard/deploy/digitalocean/.env
```

Sinh mật khẩu ngẫu nhiên mạnh cho 3 tài khoản PostgreSQL (`lgadmin`, `lg_api`, `lg_ml_writer`) và `JWT_SECRET`:

```bash
openssl rand -hex 24   # Dùng cho POSTGRES_ADMIN_PASSWORD
openssl rand -hex 24   # Dùng cho LG_API_PASSWORD
openssl rand -hex 24   # Dùng cho LG_ML_WRITER_PASSWORD
openssl rand -hex 32   # Dùng cho JWT_SECRET
```

Điền các giá trị trên cùng `LLM_API_KEY` (OpenRouter API key) vào `/opt/learnguard/deploy/digitalocean/.env`.

### 3.2. Cấu hình GitHub Environment Secrets (`production`)

Trên GitHub repository `learnguard-platform`, vào **Settings → Environments → `production`** và khai báo các Secrets sau:

| Tên Secret | Ý nghĩa | Ví dụ |
| :--- | :--- | :--- |
| `DO_HOST` | Địa chỉ IPv4 công khai của DigitalOcean Droplet | `159.223.xxx.xxx` |
| `DO_USER` | Tài khoản SSH vận hành trên Droplet | `lgops` |
| `DO_PORT` | Cổng SSH của Droplet | `22` |
| `DO_SSH_KEY` | Private key (`ed25519`) tương ứng với public key trong `/home/lgops/.ssh/authorized_keys` | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `GHCR_READ_TOKEN` | Personal Access Token (quyền `read:packages`) để Droplet pull image từ `ghcr.io` | `ghp_...` |

---

## 4. Bước 3 — Đồng bộ Dữ liệu OULAD & Chạy Pipeline Khởi tạo Ban đầu

1. Tải 7 file CSV chuẩn của bộ dữ liệu **OULAD** (`assessments.csv`, `courses.csv`, `studentAssessment.csv`, `studentInfo.csv`, `studentRegistration.csv`, `studentVle.csv`, `vle.csv`) vào `/opt/learnguard/data/oulad/` trên Droplet:
   ```bash
   rsync -avz ./oulad/*.csv lgops@<DROPLET_IP>:/opt/learnguard/data/oulad/
   ssh lgops@<DROPLET_IP> "sudo chown -R 10001:10001 /opt/learnguard/data/oulad /opt/learnguard/data/artifacts"
   ```

2. Kích hoạt chạy pipeline ML lần đầu (khởi tạo Champion Release `active_release.json`, xuất scorecard `eval-report.v1` và nạp 32.593 dự đoán vào bảng `ml_predictions`):
   ```bash
   ssh lgops@<DROPLET_IP> "cd /opt/learnguard/deploy/digitalocean && \
     docker compose -f docker-compose.prod.yml --profile batch run --rm ml-worker --mode force-retrain"
   ```

---

## 5. Bước 4 — Triển khai qua CI/CD hoặc CLI (`deploy-do.sh`)

### 5.1. Triển khai tự động qua GitHub Actions
1. Chạy workflow **`CI — Build, Scan & Push Images to GHCR`** (`ci-build-and-scan.yml`) để build 3 image (`learnguard-api`, `learnguard-ml`, `learnguard-fe`), quét bảo mật Trivy và lấy mã băm `@sha256:...`.
2. Cập nhật digest `@sha256:...` mới vào `deploy/releases/prod.yaml` thông qua Pull Request.
3. Kích hoạt workflow **`CD — Deploy Production to DigitalOcean VM`** (`cd-digitalocean-prod.yml`).

### 5.2. Triển khai trực tiếp trên Droplet
```bash
cd /opt/learnguard
./scripts/cd/deploy-do.sh --compose-dir /opt/learnguard/deploy/digitalocean
```

Trình tự tự động của `deploy-do.sh`:
1. Lưu bộ image đang chạy hiện tại vào `/opt/learnguard/deploy/digitalocean/last_good_release.env`.
2. Chạy `backup-db.sh` tạo bản sao lưu PostgreSQL nén `.sql.gz` kèm mã kiểm tra `.sha256`.
3. Pull image mới, kiểm tra sức khỏe `lg-postgres`, chạy `init-db.sh` (đảm bảo quyền least-privilege cho `lg_api` và `lg_ml_writer`) và chạy `db-migrate` (`alembic upgrade head`).
4. Cập nhật `lg-api` và `lg-frontend`, chờ Docker healthcheck đạt trạng thái `healthy`.
5. Thực thi `smoke-test.sh` kiểm tra 9 hạng mục E2E. Nếu bất kỳ bước nào thất bại, `deploy-do.sh` **tự động gọi `rollback-do.sh`** khôi phục phiên bản cũ trong vòng `< 60 giây`.

---

## 6. Bước 5 — Kiểm tra Xác nhận Sau Triển khai (Post-Deploy Verification)

Chạy bộ kiểm thử khói bất kỳ lúc nào:
```bash
/opt/learnguard/scripts/cd/smoke-test.sh --base-url http://127.0.0.1:80
```

Kiểm tra trạng thái các container và phân tách mạng:
```bash
docker compose -f /opt/learnguard/deploy/digitalocean/docker-compose.prod.yml ps
```
