# OPEN_QUESTIONS — Câu hỏi Mở & Ràng buộc Vận hành (Dual-Cloud)

> **Cập nhật:** 2026-11-23 | **Phạm vi:** Dual-Cloud Portable (**Option A: Azure PaaS** & **Option B: DigitalOcean VM**) + Baseline App Hardening.
> **Quy tắc:** Không tự ý đoán IP/giá/secret; tuyệt đối không ghi giá trị secret thật vào file này.

---

## 1. Đã Đóng / Giải quyết (Closed & Verified)

| ID | Câu hỏi | Kết quả |
|---|---|---|
| **Q-REGISTER** | Đăng ký `Microsoft.App` trên Azure | ✅ Đã chạy (2026-11-04), state `Registered` (Option A Azure). |
| **Q-NETWORK** | Public hay Private networking cho Data Plane | ✅ **Private Data Plane** ở cả hai cloud: VNet `snet-pg`/`snet-pe` trên Option A; VPC + `lg_backend_net` (`internal: true`) trên Option B. |
| **Q-FW** | PG firewall theo dải egress IP | ✅ Đóng trên cả hai cloud: PG dùng delegated subnet private trên Option A và `lg_backend_net` internal trên Option B (không mở port `5432` ra ngoài). |
| **Q-CICD-GHCR** | Push `learnguard-platform` và xác minh live GitHub Actions CI/CD + GHCR `@sha256` (`CICD-05`) | ✅ **Đã đóng (commit `e9f9c81`):** 4/4 workflows xanh, Trivy 0 CRITICAL/HIGH CVEs, GHCR digests đã ghim trong `deploy/releases/{dev,prod}.yaml`. |
| **Q-ARCH-DUAL** | Chuẩn hóa mô hình Dual-Cloud (Azure vs DigitalOcean) (`ARC-05`) | ✅ **Đã đóng (`D-018`, `D-022`):** Chốt chiến lược **Cloud-Portable Dual-Option (Deploy-Where-Available)** — duy trì cả Option A và Option B sẵn sàng, chỉ deploy lên **1 cloud có credit/account tại mỗi thời điểm** (không chạy/trả phí đồng thời). |

---

## 2. Ràng buộc Đã Xác minh Theo Cloud (Cloud-Specific Constraints)

| ID | Ràng buộc / Câu hỏi | Option A (Azure PaaS) | Option B (DigitalOcean VM) |
|---|---|---|---|
| **Q-CI-IDENTITY** | Identity cho CD tự động | Dùng **self-hosted runner (`az login`)** (`cd-dev-infra.yml`). Để dùng GitHub-hosted OIDC+UAMI cần ticket Admin (`runbooks/admin-requests.md`). | **Không bị chặn:** Dùng GitHub-hosted runner + dedicated `ed25519` deploy key (`DO_SSH_KEY`). |
| **Q-RBAC / Q-POLICY** | Quyền Tenant & Policy `FSO-SZ` | `FSO-SandboxOps` chặn `roleAssignments` & `aadiam`; `FSO-SZ` chặn public Storage/KV và đòi NSG mọi subnet (`AZURE_CONSTRAINTS.md`). | **Không áp dụng:** Chủ dự án toàn quyền VPC/Droplet/Firewall trên DigitalOcean. |
| **Q-ACR-PE** | Private Endpoint cho Registry | ACR giữ public + token/admin user (vì PE cần Premium SKU). | Dùng GHCR (`ghcr.io`) với token `read:packages` & `@sha256` immutable digest. |

---

## 3. Đang Mở — Cần Hành động / Quyết định (Open Action Items)

### 3.1. App Critical Path (Áp dụng cho Cả Option A & Option B)

| ID | Vấn đề Cần Chốt / Thực thi | Hiện trạng Đã Kiểm chứng | Owner |
|---|---|---|---|
| **Q-AUTH** 🔴 | Hoàn thiện M6 JWT Auth & RBAC (`BE-08`, `BE-09`, `BE-10`, `FE-09`) trước khi mở public prod | `BE-MLOPS/api/auth.py` vẫn `NotImplementedError`; các endpoint write dùng `system@learnguard.local`. Chặn mở public Internet trên cả 2 cloud nếu chưa đóng. | `SWE1` + `SWE2` |
| **Q-OVERSIGHT** 🔴 | Đóng kín vòng lặp Human Oversight `FR-07` (`G-26`, `G-27`, `G-28`) | Cần: (1) thêm `feedback` vào `BriefDecisionRequestBody`, (2) thêm `GET /predictions/{m}/{p}/{s}/brief`, (3) gắn nút Accept/Reject + ô feedback trong `StudentDetailPage.tsx`. | `SWE1` + `SWE2` |
| **Q-OBS** 🟠 | Bổ sung `observability.py` & endpoint `/metrics` (`BE-11`, `FE-10`) | `BE-MLOPS/observability.py` hiện vẫn `NotImplementedError`; cần xuất latency p50/p95 và LLM cost/failover cho Prometheus. | `SWE1` + `SWE2` |
| **Q-APP-PARITY** 🟡 | Các gap chất lượng dữ liệu/AI trong code baseline (`G-29`..`G-33`) | `AdvisorDashboardPage.tsx` mới hardcode 5/7 modules & 3/4 presentations; `briefs.py` chưa nạp `advisor_guidelines.md`; `ml_gate.py` mới kiểm tra fairness trên `gender`; `llm_judge.py` chưa calibrate (`AI-06`) & thiếu Product Value study (`AI-07`). | `SWE2` + `AIE` |

### 3.2. Triển khai & Vận hành Cloud (Chọn theo Cloud Đang Có Credit)

| ID | Vấn đề Cần Chốt / Thực thi | Gợi ý Hiện tại | Owner |
|---|---|---|---|
| **Q-CLOUD-ACTIVE** | Chọn cloud mục tiêu cho đợt demo/bảo vệ sắp tới (Option A hay Option B) | Tùy credit/tài khoản sẵn có tại thời điểm chạy demo. Option B (DO) có lợi thế chạy sẵn shared volume `/evaluations` + `/activity` + Prometheus + Ollama fallback. | Người dùng / `MLOPS` |
| **Q-PRICE** | Cấu hình SKU cuối cùng khi bật cloud tương ứng | **Option B (DO):** `s-4vcpu-8gb` + 50 GB Volume (~`$63/mo`, mặc định `prod.yaml`) hoặc tối thiểu `s-2vcpu-4gb` (~`$34/mo`, tắt `ollama` container).<br>**Option A (Azure):** dev SKU ~`$30–39/mo` (`infra/README.md`). | Người dùng |
| **Q-DO-PROVISION** | Provision Droplet VM thật, domain & TLS HTTPS (`443`) (`OPS-06`, `OPS-07`) | Chạy Terraform `infra/digitalocean/`, mở TLS 443 trên Nginx, ghi nhận Droplet IP/VPC vào runbook và chạy diễn tập GameDay (`rollback-do.sh`, `--mode rollback`, `restore-db.sh`). | Người dùng / `MLOPS` |
| **Q-DO-SECRETS** | Nạp GitHub Environment `production` secrets (`DO_HOST`, `DO_USER`, `DO_SSH_KEY`, `DO_PORT`, `GHCR_READ_TOKEN`) & runtime `.env` | Tạo SSH key `ed25519` riêng cho `lgops`; tuyệt đối không dùng SSH key cá nhân. | Người dùng / `MLOPS` |
| **Q-AZURE-PARITY** | Nếu triển khai Option A lên prod/demo đầy đủ: mount Azure Files `lgdata` vào `ca-lg-dev-api` | Cập nhật `infra/env/dev/apps.tf` để container API đọc được `EVALUATIONS_DIR` và `OULAD_DATA_DIR`, và xác nhận ticket Admin (`admin-requests.md`) nếu cần OIDC. | `MLOPS` |
