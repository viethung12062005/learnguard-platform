# ADR-0008 — Chuyển dịch Hạ tầng Đích sang DigitalOcean Droplet VM (Docker Compose Production Stack)

- **Trạng thái:** Accepted
- **Ngày:** 2026-11-23
- **Supersedes:** ADR-0001 (Azure Container Apps), ADR-0002 (Azure Static Web Apps), ADR-0003 (Azure PostgreSQL Flexible Server) cho môi trường triển khai mục tiêu mới.

## 1. Bối cảnh

Trong giai đoạn trước (Phase 0–1 ngày 2026-11-04), dự án được thiết kế trên Azure sandbox (`FSO-SB-GHCHCS-OJT-DEV`) với nhiều giới hạn quyền RBAC/AAD (`notActions: Microsoft.Authorization/*/Write`). Hiện tại, chủ dự án quyết định chuyển mục tiêu triển khai chính sang **VM (Droplet) của DigitalOcean** với yêu cầu:
- Kiến trúc, quy chuẩn vận hành và bảo mật phải **like-production nhất có thể**.
- Hỗ trợ chạy trọn vẹn 3 thành phần ứng dụng (`FE-MLOPS`, `BE-MLOPS`, `Data-ML-MLOPS`) cùng cơ sở dữ liệu PostgreSQL, cơ chế chia sẻ artifact đánh giá (`eval-report.v1`) và pipeline tự động phát hiện drift + tái huấn luyện mô hình.
- Chi phí kiểm soát được trên một hoặc cụm VM DigitalOcean nhưng vẫn đảm bảo cô lập mạng, phân quyền dữ liệu tối thiểu (least-privilege), reverse proxy bảo mật, giám sát (observability), sao lưu tự động và rollback tức thì.

## 2. Quyết định

1. **Hạ tầng Đích (DigitalOcean Infrastructure):**
   - Sử dụng **DigitalOcean Droplet** (Ubuntu 24.04 LTS, khuyến nghị tối thiểu `s-2vcpu-4gb` hoặc `s-4vcpu-8gb` cho workload M1–M5 OULAD ~464MB CSV + FastAPI + PostgreSQL 16).
   - Đặt Droplet trong **DigitalOcean VPC** riêng và bảo vệ bằng **DigitalOcean Cloud Firewall** kết hợp `ufw` + `fail2ban` trên host:
     - Chỉ mở cổng `80/tcp` và `443/tcp` ra Internet (do Nginx xử lý).
     - Cổng `22/tcp` (SSH) chỉ cho phép key-based authentication (`PasswordAuthentication no`, `PermitRootLogin no`) và giới hạn theo IP vận hành / GitHub Actions runner.
     - Tuyệt đối không mở cổng `5432` (PostgreSQL), `8000` (FastAPI), `11434` (Ollama), hay `9090` (Prometheus) ra ngoài host.

2. **Kiến trúc Container hóa & Cô lập Mạng (Docker Compose Production Stack):**
   - Tổ chức ứng dụng bằng `docker-compose.prod.yml` với 2 mạng nội bộ tách biệt:
     - `lg_frontend_net`: chỉ kết nối `frontend` (Nginx) và `api` (FastAPI).
     - `lg_backend_net` (`internal: true`): kết nối `api`, `postgres`, `ml-worker`, `ollama` (optional fallback), và `prometheus`.
   - **Reverse Proxy & Frontend (`Dockerfile.fe` + `nginx.fe.conf`):**
     - Build tĩnh React/Vite SPA ở stage 1, đóng gói vào `nginx:1.27-alpine` ở stage 2.
     - Nginx phục vụ static bundle với SPA fallback (`try_files $uri $uri/ /index.html`), gắn security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`), giới hạn tốc độ (`limit_req_zone`) và reverse-proxy `/api/` sang `http://api:8000/`.
   - **Database & Least-Privilege Roles (`postgres` + `roles.sql`):**
     - Chạy `postgres:16-alpine` với persistent volume, healthcheck `pg_isready`, khởi tạo schema qua `init-db.sh` và tách biệt 2 tài khoản: `lg_ml_writer` (chỉ ghi `ml_predictions`) và `lg_api` (chỉ đọc `ml_predictions`, ghi các bảng backend).
   - **Shared Artifact & Data Volume (`/opt/learnguard/data`):**
     - `ml-worker` mount Read-Write để đọc `oulad/*.csv` và xuất `artifacts/evaluations/`, `artifacts/model-releases/`, `artifacts/prediction-batches/`, `artifacts/drift-reports/`.
     - `api` mount Read-Only vào `artifacts/evaluations` (`EVALUATIONS_DIR`) và `oulad` (`OULAD_DATA_DIR`) để phục vụ trực tiếp các trang Dashboard Đánh giá tự động và Hành vi 4 tuần trên UI mà không vi phạm ranh giới code giữa hai repo.

## 3. Hệ quả

- **Ưu điểm:**
  - Loại bỏ hoàn toàn sự phụ thuộc vào Admin tenant Azure; chủ dự án nắm toàn quyền root/VPC/Firewall trên DigitalOcean.
  - Kiến trúc mạng 2 lớp (`DMZ` vs `Internal Data Plane`) và phân quyền DB 2 role giữ nguyên tính chất bảo mật production-grade.
  - Chia sẻ volume trên cùng Droplet giúp đồng bộ tức thì kết quả `eval-report.v1` từ pipeline ML lên giao diện quản trị của Backend/Frontend.
- **Đánh đổi & Kiểm soát Rủi ro:**
  - Single-VM có rủi ro SPOF phần cứng → Giảm thiểu bằng DigitalOcean Automated Backups, script `backup-db.sh` (`pg_dump` nén mỗi ngày và trước mỗi lần deploy), lưu trữ immutable container images trên GHCR và IaC (`infra/digitalocean/`) để dựng lại toàn bộ VM trong `< 10 phút` (RTO < 15m).
