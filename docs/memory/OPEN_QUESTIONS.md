# OPEN_QUESTIONS — Câu hỏi mở & Ràng buộc Vận hành

> File "kiến thức" → không commit vào `learnguard-platform`. Cập nhật **2026-11-23**.

## Đã đóng / Superseded

| ID | Câu hỏi | Kết quả |
|---|---|---|
| Q-REGISTER | Đăng ký `Microsoft.App` | ✅ Đã chạy (2026-11-04), state **Registered** (Azure phase) |
| Q-NETWORK | Public hay private networking (Azure) | ✅ **Private networking** — sau đó chuyển sang DigitalOcean VPC + `lg_backend_net` internal (ADR-0008) |
| Q-FW | PG firewall theo dải egress IP (Azure) | ✅ Đóng — PostgreSQL chạy nội bộ trong `lg_backend_net`, không mở port `5432` ra ngoài host |
| Q-CI-IDENTITY | CD chạy self-hosted runner hay Azure OIDC+UAMI? | ✅ **Superseded (ADR-0008 & ADR-0009)** — Chuyển sang GitHub Actions hosted runner + GHCR + dedicated SSH deploy key trên GitHub Environment `production` |
| Q-RBAC | Admin gán Contributor(RG) cho UAMI CI trên Azure? | ✅ **Superseded (ADR-0008 & ADR-0009)** — Không còn phụ thuộc Azure RBAC/Admin ticket |
| Q-POLICY | Azure Policy / deny assignment ở management group `FSO`? | ✅ **Superseded (ADR-0008)** — Triển khai trên DigitalOcean Droplet VM do chủ dự án toàn quyền quản trị |
| Q-ACR-PE | ACR private endpoint SKU Premium? | ✅ **Superseded (ADR-0008 & ADR-0009)** — Dùng GitHub Container Registry (`ghcr.io`) với immutable `@sha256` digests |

## Còn mở (cần quyết định / xác minh vận hành DigitalOcean)

| ID | Câu hỏi | Gợi ý hiện tại | Ai |
|---|---|---|---|
| Q-AUTH | API xác thực người dùng (M6): FE đã có login/role guard (`admin`, `advisor`), BE cần xác nhận trạng thái bảo vệ endpoint `/predictions`, `/evaluations`, `/audit-logs` trước khi mở public prod | Kiểm tra enforcement JWT/RBAC ở `BE-MLOPS`; giữ Nginx IP allowlist/TLS nếu môi trường còn thử nghiệm | Người dùng / backend team |
| Q-PRICE | Cấu hình SKU Droplet DigitalOcean cuối cùng cho production (`s-2vcpu-4gb` ~$24/tháng vs `s-4vcpu-8gb` ~$48/tháng) | Khuyến nghị tối thiểu `s-2vcpu-4gb` (hoặc `s-4vcpu-8gb` nếu bật Ollama local fallback + Prometheus + batch OULAD đồng thời) | Người dùng |
| Q-DO-PROVISION | Thông tin hạ tầng DigitalOcean thực tế (Droplet Public IP, VPC ID, Cloud Firewall, domain name & TLS Let's Encrypt/Cloudflare) | Provision qua `infra/digitalocean/` Terraform và ghi nhận IP/domain vào runbook vận hành | Người dùng |
| Q-DO-SECRETS | Thiết lập GitHub Environment `production` secrets (`DO_HOST`, `DO_USER`, `DO_SSH_KEY`, `DO_PORT`) và runtime `.env` secrets (`POSTGRES_PASSWORD`, `LLM_API_KEY`, `JWT_SECRET`) trên Droplet | Tạo cặp SSH key ed25519 riêng cho CI/CD deploy user (`learnguard-deploy`), không dùng key cá nhân | Người dùng / MLOps |

## Quy tắc

- Không tự ý "đoán" giá/IP/secret → đánh dấu "cần xác minh" và thêm vào đây.
- Tuyệt đối không ghi giá trị secret thật vào file này hoặc bất kỳ file nào trong repo.
- Mỗi khi đóng 1 mục → chuyển xuống bảng "Đã đóng / Superseded".
