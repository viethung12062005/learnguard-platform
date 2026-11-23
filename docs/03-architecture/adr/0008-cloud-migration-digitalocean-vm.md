# ADR-0008 — Kiến trúc Cloud Đích Option B: DigitalOcean Droplet VM (Docker Compose Production Stack)

- **Trạng thái:** **Accepted — Dual-Cloud Option B (Parallel to Active Option A: Azure PaaS ADR-0001..0007)**
- **Ngày:** 2026-11-23
- **Song song với (Parallel Target To):** [ADR-0001](0001-compute-container-apps.md) (Azure Container Apps), [ADR-0002](0002-frontend-static-web-apps.md) (Azure Static Web Apps), [ADR-0003](0003-data-postgresql-flexible.md) (Azure PostgreSQL Flexible Server), [ADR-0004](0004-secrets-dataplane-auth.md)–[ADR-0007](0007-ml-storage-batch-observability.md) — **Cả Option A (Azure PaaS) và Option B (DigitalOcean VM) đều được duy trì là hai đích triển khai hạng nhất (first-class, deploy-where-available).**
- **Liên quan:** [Dual-Cloud Strategy](../../03-architecture/dual-cloud-strategy.md) · [ADR-0009](0009-cicd-pipeline-digitalocean-ghcr.md) · [ADR-0010](0010-drift-detection-and-continual-retraining-pipeline.md)

---

## 1. Bối cảnh

Trong Phase 0–1 (2026-11-04), LearnGuard đã thiết kế và hoàn thiện hạ tầng IaC Terraform cho **Option A — Azure PaaS** trên subscription sandbox (`FSO-SB-GHCHCS-OJT-DEV`), nơi có các ràng buộc quyền RBAC/AAD (`notActions: Microsoft.Authorization/*/Write`) và Azure Policy `FSO-SZ` yêu cầu Jump VM + self-hosted CD runner.

Để bảo đảm dự án luôn chủ động triển khai được trong mọi tình huống credit/tài khoản cloud (chiến lược **Cloud-Portable Dual-Option / Deploy-Where-Available** theo [dual-cloud-strategy.md](../dual-cloud-strategy.md)), nhóm cần bổ sung **Option B — VM (Droplet) trên DigitalOcean** làm đích triển khai song song với Azure PaaS với các yêu cầu:
- Kiến trúc, quy chuẩn vận hành và bảo mật phải đạt mức **like-production** tương đương hoặc cao hơn Option A ở tầng cô lập mạng và kiểm định tự động.
- Dùng chung 100% mã nguồn ứng dụng (`BE-MLOPS`, `Data-ML-MLOPS`, `FE-MLOPS`), 3 Dockerfiles (`deploy/docker/Dockerfile.{api,ml,fe}`), phân quyền DB 2 role (`lg_api`, `lg_ml_writer`), và động cơ MLOps Drift/Retraining (`deploy/ml/`).
- Hỗ trợ chạy trọn vẹn 3 thành phần ứng dụng cùng PostgreSQL 16, chia sẻ trực tiếp volume artifact đánh giá (`eval-report.v1`), `ollama` fallback local, và cụm giám sát Prometheus trên một Droplet có kiểm soát chi phí.
- Tại thời điểm triển khai thực tế, đội vận hành chỉ cần deploy lên **cloud đang có credit/tài khoản khả dụng** (Azure Option A **hoặc** DigitalOcean Option B) mà không phải chạy hay trả phí cho cả hai cloud đồng thời.

---

## 2. Quyết định

1. **Duy trì Dual-Cloud Song song (Option A Azure PaaS + Option B DigitalOcean VM):**
   - Giữ nguyên toàn bộ hạ tầng Option A ([`azure-target-architecture.md`](../azure-target-architecture.md), `infra/env/dev/`, `infra/modules/*`, `runbooks/deploy-dev.md`, `cd-dev-*.yml`) ở trạng thái sẵn sàng hoạt động.
   - Xây dựng bổ sung **Option B (DigitalOcean Droplet VM)** tại `infra/digitalocean/` và `deploy/digitalocean/` theo các tiêu chuẩn dưới đây.

2. **Hạ tầng Đích Option B (DigitalOcean Infrastructure):**
   - Sử dụng **DigitalOcean Droplet** (Ubuntu 24.04 LTS, mặc định `s-4vcpu-8gb` hoặc tối thiểu `s-2vcpu-4gb`, region `sgp1`) gắn **Block Storage Volume 50 GiB** tại `/opt/learnguard/data`.
   - Đặt Droplet trong **DigitalOcean VPC (`10.116.0.0/20`)** riêng và bảo vệ bằng **DigitalOcean Cloud Firewall** kết hợp `ufw` + `fail2ban` trên host:
     - Chỉ mở cổng `80/tcp` và `443/tcp` ra Internet (do Nginx xử lý).
     - Cổng `22/tcp` (SSH) chỉ cho phép key-based authentication (`PasswordAuthentication no`, `PermitRootLogin no`) và giới hạn theo `allowed_ssh_cidrs` (IP vận hành / GitHub Actions runner).
     - Tuyệt đối không mở cổng `5432` (PostgreSQL), `8000` (FastAPI), `11434` (Ollama), hay `9090` (Prometheus) ra ngoài host.

3. **Kiến trúc Container hóa & Cô lập Mạng (Docker Compose Production Stack):**
   - Tổ chức ứng dụng bằng `deploy/digitalocean/docker-compose.prod.yml` với 2 mạng nội bộ tách biệt:
     - `lg_frontend_net`: chỉ kết nối `frontend` (Nginx) và `api` (FastAPI) (+ `ollama` khi bật profile `llm-fallback`).
     - `lg_backend_net` (`internal: true`): kết nối `api`, `postgres`, `ml-worker`, `ollama` (optional fallback), và cụm `prometheus`/`node-exporter`/`cadvisor`.
   - **Reverse Proxy & Frontend (`Dockerfile.fe` + `nginx.fe.conf`):**
     - Build tĩnh React/Vite SPA ở stage 1 (`node:22-alpine`), đóng gói vào `nginx:alpine` ở stage 2.
     - Nginx phục vụ static bundle với SPA fallback (`try_files $uri $uri/ /index.html`), gắn đủ 5 security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy`) trong mọi `location` block, giới hạn tốc độ (`limit_req_zone ... rate=20r/s`) và reverse-proxy `/api/` sang `http://api:8000/`.
   - **Database & Least-Privilege Roles (`postgres` + `init-db.sh` + `roles.sql`):**
     - Chạy `postgres:16-alpine` với persistent volume, healthcheck `pg_isready`, khởi tạo bảng `ml_predictions` + `ALTER DEFAULT PRIVILEGES` qua `init-db.sh` (không xung đột với container `db-migrate` chạy `alembic upgrade head`), tách biệt 2 tài khoản: `lg_ml_writer` (chỉ sở hữu & ghi `ml_predictions`) và `lg_api` (chỉ `SELECT` trên `ml_predictions`, CRUD các bảng backend).
   - **Shared Artifact & Data Volume (`/opt/learnguard/data`):**
     - `ml-worker` mount Read-Write để đọc `oulad/*.csv` và xuất `artifacts/evaluations/`, `artifacts/model-releases/`, `artifacts/prediction-batches/`, `artifacts/drift-reports/`.
     - `api` mount Read-Only vào `artifacts/evaluations` (`EVALUATIONS_DIR`) và `oulad` (`OULAD_DATA_DIR`) để phục vụ trực tiếp các trang Dashboard Đánh giá tự động (`/evaluations`) và Hành vi 4 tuần (`/predictions/.../activity`) mà không vi phạm ranh giới code giữa các repo.

---

## 3. Hệ quả

- **Ưu điểm:**
  - Giúp LearnGuard có tính di động đa đám mây thật sự: hết credit Azure có thể triển khai sang DigitalOcean ngay bằng Terraform + GitHub Actions, và ngược lại khi có Azure subscription/credits vẫn giữ nguyên toàn bộ năng lực PaaS của Option A.
  - Trên Option B, chủ dự án nắm toàn quyền root/VPC/Firewall trên DigitalOcean, CD chạy 100% bằng GitHub-hosted runner qua GHCR `@sha256`, và chia sẻ đĩa trực tiếp giữa `ml-worker` và `api`.
  - Kiến trúc mạng 2 lớp (`DMZ` vs `Internal Data Plane`) và phân quyền DB 2 role giữ nguyên tính chất bảo mật production-grade như Option A.
- **Đánh đổi & Kiểm soát Rủi ro:**
  - Single-VM trên Option B có rủi ro SPOF phần cứng → Giảm thiểu bằng DigitalOcean Automated Backups, script `backup-db.sh` (`pg_dump` nén mỗi ngày và trước mỗi lần deploy), lưu trữ immutable container images trên GHCR và IaC (`infra/digitalocean/`) để dựng lại toàn bộ VM trong `< 15 phút`.
  - Cần giữ parity cấu hình giữa hai option (ví dụ khi bổ sung `EVALUATIONS_DIR`/`OULAD_DATA_DIR` hoặc biến auth mới, phải cập nhật tương ứng ở cả `docker-compose.prod.yml` lẫn `infra/env/dev/apps.tf`).
