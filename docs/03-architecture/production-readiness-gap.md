# LearnGuard — Production Readiness Gap Register (v4)

> **Phiên bản:** 4.0 (2026-11-23)
> **Phạm vi đánh giá:** Đánh giá toàn diện độ sẵn sàng vận hành thực tế theo **CMU MLIP (Lec 1–6)** trên **cả hai đích triển khai Dual-Cloud (Option A: Azure PaaS & Option B: DigitalOcean VM)** và **kiểm toán mã nguồn thực tế** của cả 3 repo ứng dụng (`BE-MLOPS@a2bae92`, `Data-ML-MLOPS@72c96cd`, `FE-MLOPS@0f70e14`).
> **Phân loại hành động:** **A** = Platform/MLOps làm được ngay · **B** = Cần Admin tenant (Option A) / Provision VM (Option B) · **C** = Cần App Change trên `BE-MLOPS` / `FE-MLOPS` / `Data-ML-MLOPS` hoặc Product Study.

---

## 0. Đánh giá Tổng quan (Executive Verdict — v4)

| Trục Đánh giá | Điểm / Trạng thái (v4) | Giải thích Trung thực (Evidence-Based) |
| :--- | :--- | :--- |
| **1. Nền tảng Hạ tầng & MLOps (Dual-Cloud Option A + B)** | **8.8 / 10 (Infra/MLOps Ready)** | **Option B (DigitalOcean):** 2-network isolation (`lg_frontend_net` / `lg_backend_net`), DB least-privilege (`lg_api`, `lg_ml_writer`), Nginx rate limit & 5 headers, Trivy `exit-code: 1` + GHCR `@sha256` đã verify (`e9f9c81`), `backup-db.sh` + auto-rollback `< 60s`, Drift Triage + Behavioral Gate + Retrain Pipeline (`pytest` pass). Chỉ còn `OPS-06` (provision VM thật) & `OPS-07` (GameDay drill).<br>**Option A (Azure PaaS):** Terraform 39 resources (`snet-pg`, `snet-pe`, `snet-cae`, Jump VM) và CD workflows sẵn sàng (`cd-dev-*.yml`); còn ràng buộc `FSO-SandboxOps` (cần ticket Admin nếu chạy OIDC hosted) và mount `lgdata` vào `ca-lg-dev-api` cho `/evaluations` & `/activity`. |
| **2. Bảo mật & Vòng lặp Con người ở Tầng Ứng dụng** | **5.5 / 10 (App Hardening Required)** | Kiến trúc và contract rất sạch, nhưng kiểm toán code trực tiếp cho thấy còn **10 khoảng trống thật** ở `BE-MLOPS`, `FE-MLOPS`, `Data-ML-MLOPS` (đặc biệt: `api/auth.py` & `observability.py` vẫn `NotImplementedError`, `StudentDetailPage.tsx` thiếu nút Accept/Reject, `BriefDecisionRequestBody` thiếu `feedback`, thiếu `GET /predictions/.../brief`, `AdvisorDashboardPage.tsx` hardcode 5/7 modules & 3/4 presentations). |
| **Phán quyết Chung** | **"Infra Prod-Shaped ✅ · App Hardening Required ⚠️"** | **KHÔNG** mở Public Internet không giới hạn IP trên cả Option A lẫn Option B cho tới khi đóng xong Critical Path (`G-01` Auth/RBAC + `G-25..G-29` Closed-Loop Oversight & Observability). |

---

## 1. Khoảng trống Thực tế trong Mã nguồn Ứng dụng (Verified Baseline Code Gaps — 2026-11-23)

Bảng dưới đây ghi nhận **chính xác 10 khoảng trống đã đối chiếu trực tiếp trong code nguồn** (không suy diễn):

| Gap ID | Vị trí Chính xác trong Code | Hiện trạng Đã Kiểm chứng | Mức độ | Tác động & Hướng Khắc phục (`Task ID`) |
| :--- | :--- | :--- | :---: | :--- |
| **G-01** | `BE-MLOPS/src/learnguard_backend/api/auth.py` (`L6-L17`) & `api/app.py` (`L1144, L1195, L1268, L1466, L1817`) | `AuthenticationService` (`authenticate`, `create_access_token`, `require_role`) và `AuthenticationController` đều `raise NotImplementedError`. Tất cả routes (`/predictions*`, `/briefs*`, `/evaluations*`, `/audit-logs`) chưa enforce JWT/RBAC; các thao tác ghi dùng `user_repo.get_or_create_system_user()` (`system@learnguard.local`) và `_audit_event` ghi `user_id=None`. | 🔴 **Critical** (C) | Chặn mở public prod. Implement `POST /auth/login`, `GET /auth/me`, dependencies `require_advisor`/`require_admin` và nối `FE-MLOPS` JWT (`BE-08`, `BE-09`, `BE-10`, `FE-09`). |
| **G-25** | `BE-MLOPS/src/learnguard_backend/observability.py` (`L26-L45`) & `api/app.py` | `StructuredLogger.log_event`, `MetricsCollector.record_request`, `MetricsCollector.record_llm_call`, `write_run_summary` đều `raise NotImplementedError`. Chưa có endpoint `/metrics` (Prometheus) nên `deploy/digitalocean/prometheus.yml` hiện chỉ scrape `node-exporter` & `cadvisor`. | 🟠 **High** (C) | Mù telemetry API latency p50/p95 và LLM cost/failover real-time. Triển khai structured JSON logger (lọc PII) + `/metrics` Prometheus exposition (`BE-11`, `FE-10`). |
| **G-26** | `BE-MLOPS/src/learnguard_backend/api/app.py` (`L206-L208, L1203`) | `BriefDecisionRequestBody` chỉ có `decision: str`, **thiếu trường `feedback: str \| None = None`**, và `decide_brief` hardcode `feedback=None` khi lưu `DecisionRecord` — dù `api/schemas.py` (`DecisionRequest`) và bảng `decisions` (`DB_CONTRACT.md` §6.5) có sẵn cột `feedback`. | 🔴 **Critical** (C) | Cố vấn không ghi nhận được lý do khi Accept/Reject brief (đứt vòng học tập phản hồi `FR-07`). Bổ sung `feedback: str \| None = None` vào `BriefDecisionRequestBody` và truyền vào `DecisionRecord`. |
| **G-27** | `BE-MLOPS/src/learnguard_backend/api/app.py` (route `/predictions/...` & `/briefs/...`) | Chỉ có `POST /briefs/generate` và `GET /briefs/{brief_id}`; **thiếu endpoint `GET /predictions/{code_module}/{code_presentation}/{student_key}/brief`** để lấy brief đang active theo composite key. | 🟠 **High** (C) | Khi cố vấn reload `StudentDetailPage` hoặc mở từ hàng đợi, UI không tự tải được brief đã tạo/đã duyệt trước đó. Bổ sung `GET /predictions/{m}/{p}/{s}/brief` gọi `brief_repo.get_active(...)`. |
| **G-28** | `FE-MLOPS/src/pages/StudentDetailPage.tsx` (`L974-L997`) | Dù `client.ts` và `brief-service.ts` đã có `saveBriefDecision(briefId, 'accepted' \| 'rejected')`, giao diện `StudentDetailPage.tsx` chỉ render 3 nút (*Trao đổi với Trợ lý AI*, *Chỉnh sửa*, *Tạo lại brief*) và **thiếu nút Chấp nhận (`Accept`) / Từ chối (`Reject`) + ô nhập `feedback`**. | 🔴 **Critical** (C) | Đứt vòng lặp **100% Human Oversight (`FR-07`)** trên giao diện thật! Cần nối ngay nút Accept/Reject + confirmation + feedback vào `BriefService` (`FE-13` completion). |
| **G-29** | `FE-MLOPS/src/pages/AdvisorDashboardPage.tsx` (`L51-L65`) | `MODULE_OPTIONS` hardcode **5/7 modules** (`AAA`–`EEE`, thiếu `FFF`, `GGG`) và `PRESENTATION_OPTIONS` hardcode **3/4 presentations** (`2013J`, `2014B`, `2013B`, thiếu `2014J`). | 🟡 **Medium** (C) | Cố vấn không lọc được dữ liệu các học phần `FFF`, `GGG` và holdout/cohort `2014J` qua UI filter. Bổ sung đủ 7 modules / 4 presentations hoặc lấy động từ backend. |
| **G-30** | `BE-MLOPS/src/learnguard_backend/services/briefs.py` (`L26-L43, L203-L212`) | Luồng tạo one-shot brief (`AdvisorBriefService.generate`) chỉ dùng `BRIEF_SYSTEM_PROMPT` tĩnh, **không nạp** `BE-MLOPS/src/learnguard_backend/services/advisor_guidelines.md` (trong khi `chat_context.py` có nạp `_GUIDELINES_PATH`). | 🟡 **Medium** (C) | Gợi ý can thiệp của brief one-shot chưa đồng nhất với Sổ hướng dẫn cố vấn và quy trình escalation (`FR-06`). Cần tiêm các mục liên quan của `advisor_guidelines.md` vào context brief. |
| **G-31** | `Data-ML-MLOPS/src/learnguard/evaluation/ml_gate.py` (`L42, L360-L400`) | `FAIRNESS_COLUMN = "gender"` — `_check_fairness_slices` mới đánh giá công bằng trên **1 chiều duy nhất** (`gender`), bỏ qua `code_module`, `age_band`, `disability`, `imd_band`. | 🟠 **High** (C) | Có thể bỏ sót chênh lệch FNR giữa các nhóm học phần/tuổi/khuyết tật/kinh tế-xã hội (`NFR-ML4`). Mở rộng ra 5 chiều kèm guard cỡ mẫu (`ML-11`). |
| **G-32** | `Data-ML-MLOPS/src/learnguard/evaluation/llm_judge.py` (`L23-L29`) | `llm_judge.py` (`gemini-3.1-flash-lite`) chấm 4 tiêu chí (`grounded`, `useful`, `no_fabrication`, `clarity`) nhưng chưa được hiệu chỉnh (calibrate) so với nhãn chấm độc lập của con người. | 🟡 **Medium** (C) | Nguy cơ lệch chuẩn đánh giá tự động `Gate 3`. Thực nghiệm đối chiếu dual human rubric annotations trên 30 brief (`AI-06`). |
| **G-33** | Product / User Value Validation (`01-business-analysis/product-value-protocol.md`) | Chưa có số liệu thực nghiệm chứng minh giá trị sản phẩm cho cố vấn (thời gian rà soát & chất lượng can thiệp **có vs không có** LearnGuard AI). | 🟠 **High** (C) | Theo CMU MLIP Lec 1–2 (*Product Boundary*), thiếu bằng chứng `Accuracy ≠ Usefulness`. Thực hiện benchmark 10 case studies (`AI-07`). |

---

## 2. Ma trận Trạng thái Hạ tầng & Vận hành Dual-Cloud (`G-02` → `G-24`)

Dưới đây là toàn bộ các gap hạ tầng từ giai đoạn v2–v3, được đối chiếu trạng thái trên **cả hai đích Cloud Option A (Azure PaaS) và Option B (DigitalOcean VM)**:

| Gap ID | Hạng mục Hạ tầng / Bảo mật | Trạng thái trên Option A (Azure PaaS) | Trạng thái trên Option B (DigitalOcean VM) | Hành động Còn lại |
| :--- | :--- | :--- | :--- | :--- |
| **G-02** | Rate limiting / Security headers / WAF | 🟡 `ca-lg-dev-api` public ingress + IP restriction + CORS; hoãn App Gateway WAF (`~$180–320/mo`) | ✅ **Đã đóng:** `nginx.fe.conf` đặt `limit_req_zone` (`20r/s`, `burst=40`) + đủ 5 security headers trên mọi `location` block | Option A: giữ IP restriction/CORS ở dev; bật AppGW nếu lên enterprise prod |
| **G-03** | CI/CD identity tách biệt | 🟡 Self-hosted runner (`az login`) hoạt động; OIDC+UAMI trên hosted runner cần ticket Admin ([`admin-requests.md`](../../runbooks/admin-requests.md)) | ✅ **Đã đóng:** GitHub-hosted runner + GHCR token + dedicated SSH deploy key trong GitHub Env `production` | Option A: gửi ticket Admin nếu muốn chuyển hẳn sang OIDC hosted |
| **G-04** | Database High Availability (HA) | 🔴 Dev dùng PG Burstable `B1ms` (không hỗ trợ zone-redundant HA) | ⚠️ **Accepted Trade-off:** Single-VM container `postgres:16-alpine` (không có multi-node HA) | Option A prod: nâng General Purpose/HA; Option B: bù bằng `backup-db.sh` + DO Backups + Terraform RTO `< 15m` |
| **G-05** | Backup / DR & Test Restore | 🟡 PG Flexible có automated backup; chưa chạy drill restore kiểm chứng | 🟡 Script `backup-db.sh` (kèm `.sha256`) & `restore-db.sh` đã pass `--dry-run`; chờ diễn tập live (`OPS-07`) | Thực thi live GameDay backup/restore trên VM (`OPS-07`) |
| **G-06** | Terraform Remote State | 🟡 `infra/bootstrap/` đã viết, nhưng policy `FSO-SZ` chặn Storage public access ngoài VNet → `env/dev` dùng local state | 🟡 `infra/digitalocean/` hiện dùng local state (hoặc nâng lên Spaces S3 backend khi có nhiều operator) | Giữ state ngoài Git (`.gitignore`), chuyển Spaces/VNet remote backend trước khi nhiều người cùng `apply` |
| **G-07 / G-08** | NSG / Firewall & Egress Control | ✅ NSG cho `snet-cae`, `snet-pg`, `snet-pe`, `snet-jump` đã có (kèm ARM fix policy) | ✅ DigitalOcean Cloud Firewall + host `ufw` + `lg_backend_net` (`internal: true`) | Bổ sung egress allowlist chặt hơn nếu yêu cầu compliance cao |
| **G-09** | Compute HA / Scaling | 🟡 `min_replicas = 0` ở dev (tiết kiệm chi phí, cold start ~20s); prod cần `>= 1` | 🟡 Single-VM `restart: unless-stopped` + resource limits (`mem_limit`, `cpus`) | Option A prod: đặt `min_replicas >= 1`; Option B: dùng `s-4vcpu-8gb` theo `prod.yaml` |
| **G-10** | Observability vận hành & AI | ✅ Log Analytics + App Insights (Option A) | ✅ Prometheus + Node Exporter + cAdvisor + `eval-report.v1` + `drift-report.v1` | Hoàn thiện `BE-11` (`/metrics`) để Prometheus thu thập latency & LLM cost |
| **G-11** | Migration strategy tách biệt | 🟡 Chạy `alembic upgrade head` từ Jump VM / CD | ✅ **Đã đóng:** Container `db-migrate` chạy trước `api` + idempotent `init-db.sh` + `ALTER DEFAULT PRIVILEGES` | Duy trì quy tắc expand/contract migration |
| **G-12** | Supply chain security | 🟡 Build qua `build-push.ps1` + `@sha256`; chưa gắn Trivy trực tiếp trong script PS1 | ✅ **Đã đóng:** `ci-build-and-scan.yml` chạy **Trivy `exit-code: 1`** (0 CRITICAL/HIGH), non-root `UID 10001`, GHCR `@sha256` đã verify (`e9f9c81`) | Có thể tái dùng image đã quét Trivy từ CI cho cả Option A |
| **G-13..G-18** | Storage soft-delete, Cost tags, Checkov, Secret rotation, KV RBAC, ACR Premium PE | 🟡 Các mục tối ưu riêng cho Azure PaaS (`AZURE_CONSTRAINTS.md`, `admin-requests.md`) | *N/A trên Option B* (dùng DO Block Storage, `.env` chmod 600, GHCR) | Thực hiện theo lộ trình khi triển khai Option A ở quy mô prod |
| **G-19** | Audit trail (`audit_logs`) | ✅ **Đã đóng ở tầng App** (`GET /audit-logs` & ghi log các route trong `BE-MLOPS@a2bae92`) | ✅ **Đã đóng ở tầng App** | Bổ sung `user_id` thật khi đóng `G-01` (`BE-10`) |
| **G-20..G-24** | PII retention policy, TLS certbot/domain, Live DO Provision | 🟡 Đã ẩn danh `student_key` 16-hex & không log prompt LLM; cần chốt lịch retention chính thức (`M10`) | 🟡 `docker-compose.prod.yml` comment sẵn cổng `443` chờ domain/TLS; chờ provision VM thật (`OPS-06`) | Chốt domain + TLS HTTPS trước khi mở truy cập rộng rãi |

---

## 3. Lộ trình Đóng Gap theo Mức độ Ưu tiên (Critical-Path Action Plan)

1. **Ưu tiên 1 — Chặn Mở Public Prod nếu chưa Đóng (Security & Oversight):**
   - `G-01` (`BE-08`, `BE-09`, `BE-10`, `FE-09`): Hoàn thiện `auth.py` JWT + RBAC (`advisor`/`admin`), gỡ bỏ `system@learnguard.local` placeholder.
   - `G-26` + `G-27` + `G-28`: Thêm `feedback` vào `BriefDecisionRequestBody`, thêm `GET /predictions/{m}/{p}/{s}/brief`, và gắn nút **Chấp nhận / Từ chối + feedback** trên `FE-MLOPS/src/pages/StudentDetailPage.tsx`.
2. **Ưu tiên 2 — Năng lực Quan sát, Dữ liệu Đầy đủ & Công bằng (Operability & Fairness):**
   - `G-25` (`BE-11`): Implement `observability.py` + endpoint `/metrics` cho Prometheus.
   - `G-29` & `G-30`: Mở khóa đủ 7 modules / 4 presentations trong `AdvisorDashboardPage.tsx` và nạp `advisor_guidelines.md` vào `AdvisorBriefService.generate`.
   - `G-31` (`ML-11`): Mở rộng `ml_gate.py` từ `gender`-only sang 5 chiều fairness slices.
3. **Ưu tiên 3 — Thực nghiệm Cloud & Giá trị Sản phẩm (Defense & Production Proof):**
   - `OPS-06` & `OPS-07` (Option B — hoặc Option A tương ứng tùy cloud có credit): Provision VM thật, bật TLS 443, chạy `smoke-test.sh` & diễn tập 3 bài GameDay (app rollback, model `--mode rollback`, DB restore).
   - `G-32` (`AI-06`) & `G-33` (`AI-07`): Hiệu chỉnh `llm_judge.py` với dual human rubric và thực hiện Product Value study (with vs without AI).
