# LearnGuard — Unified Threat Model (STRIDE + OWASP LLM Top 10)

> **Phiên bản:** 3.0 (2026-11-23)
> **Phạm vi:** Bao phủ **cả hai đích triển khai Dual-Cloud** (**Option A: Azure PaaS** & **Option B: DigitalOcean VM**) và toàn bộ chuỗi AI/LLM (`Data-ML-MLOPS`, `BE-MLOPS`, `FE-MLOPS`, `learnguard-platform`). Bám sát `FR-08`, `FR-09`, `NFR-SEC1`, [`production-readiness-gap.md`](production-readiness-gap.md) và [`dual-cloud-strategy.md`](dual-cloud-strategy.md).
> **Ký hiệu trạng thái:** ✅ = Đã kiểm soát trong code/hạ tầng · 🟡 = Kiểm soát một phần / phụ thuộc cấu hình môi trường · 🔴 = Gap mở trọng yếu (chặn mở public prod).

---

## 1. Năm Ranh giới Tin cậy (Trust Boundaries — Dual-Cloud)

| Boundary | Option A (Azure PaaS) | Option B (DigitalOcean VM) | Dữ liệu Đi qua Ranh giới |
| :--- | :--- | :--- | :--- |
| **TB-1: Public Internet ↔ Ingress** | Browser → Azure Static Web App (`swa-lg-dev`) → Container App API (`ca-lg-dev-api` external ingress + CORS + IP restriction) | Browser → DO Cloud Firewall (`80/443`) + `ufw` → Nginx container (`lg_frontend_net` DMZ) → proxy `/api/` sang `api:8000` | Yêu cầu HTTPS/HTTP, credentials đăng nhập, token JWT, JSON predictions/briefs/chat. |
| **TB-2: App Tier ↔ Data Plane** | `ca-lg-dev-api` (VNet `snet-cae`) → PG Flexible (`snet-pg`, TLS, `lg_api`) & Key Vault PE (`snet-pe`) | `lg-api` → `lg-postgres` trên `lg_backend_net` (`internal: true`, role `lg_api`) & volume `/opt/learnguard/data` (`ro`) | SQL queries (`SELECT ml_predictions`, CRUD backend tables), evaluation scorecards, OULAD CSVs. |
| **TB-3: ML Batch ↔ DB & Artifacts** | `caj-lg-dev-ml` (`snet-cae`) → Azure Files `lgdata` (`/mnt/data`) & PG Flexible (role `lg_ml_writer`) | `lg-ml-worker` (`lg_backend_net` `internal: true`) → Block Storage `/opt/learnguard/data` (`rw`) & `lg-postgres` (role `lg_ml_writer`) | 7 OULAD CSVs, snapshots, model releases, `ml_predictions` upserts. |
| **TB-4: CI/CD ↔ Cloud Runtime** | GitHub Actions CI + Self-Hosted Runner (`az login`) / ACR (`acrdev*`) | GitHub Actions (`ubuntu-latest`) + GHCR `@sha256` + SSH deploy key (`GitHub Env: production`) | Mã nguồn 4 repos, container images, deploy bundles, secrets. |
| **TB-5: Backend API ↔ LLM Providers** | `ca-lg-dev-api` outbound → OpenRouter HTTPS API (LiteLLM) | `lg-api` (`lg_frontend_net` outbound) → OpenRouter HTTPS API hoặc `lg-ollama` (`lg_backend_net` internal) | Minimal PII-free context (`student_key` 16-hex, features, signals), chat turns, JSON briefs. |

---

## 2. Phân tích STRIDE trên 5 Luồng Chính (Option A & Option B)

### Luồng 1 — Advisor / Admin Browser ↔ Frontend ↔ Backend API (`TB-1`)

| STRIDE | Mối đe dọa | Control trên Option A (Azure) | Control trên Option B (DigitalOcean) | Trạng thái & Việc cần làm |
| :--- | :--- | :--- | :--- | :--- |
| **Spoofing** | Kẻ tấn công gọi thẳng API giả danh Advisor/Admin | IP restriction + CORS hạn chế origin SWA (tạm thời) | DO Cloud Firewall + Nginx reverse proxy cùng origin (tạm thời) | 🔴 **`G-01` (Critical):** `BE-MLOPS/api/auth.py` đang `NotImplementedError`! Bắt buộc hoàn thiện `BE-08`, `BE-09`, `FE-09` trước khi mở public prod. |
| **Tampering** | Chỉnh sửa request/header giữa browser và API | TLS 1.2+ bắt buộc trên SWA & Container App ingress | HTTPS/TLS trên Nginx (`443`, cần bật certbot khi gắn domain); `no-new-privileges` | 🟡 Cấu hình TLS Let's Encrypt / Cloudflare cho cổng `443` trên Droplet khi deploy domain thật. |
| **Repudiation** | Truy cập prediction / duyệt brief không lưu vết | `audit_logs` append-only (`BE-MLOPS@a2bae92`) | `audit_logs` append-only (`BE-MLOPS@a2bae92`) | 🟡 Đã ghi `audit_logs` trên các route, nhưng `user_id` vẫn là `None` hoặc `system@learnguard.local` cho tới khi đóng `BE-10`. |
| **Info Disclosure** | Lộ dữ liệu dự đoán hoặc clickjacking/XSS | `CORS_ORIGINS` không dùng `*`; dữ liệu chỉ có `student_key` 16-hex | Nginx gắn đủ 5 security headers (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, `CSP`) ở mọi `location` block | 🔴 Thiếu auth endpoint vẫn là rủi ro lộ dữ liệu mức hệ thống (`G-01`). |
| **DoS** | Flood request làm sập API hoặc đốt quota LLM | Container App scale rule (`max_replicas=2`) | Nginx `limit_req_zone ... rate=20r/s` (`burst=40 nodelay`), `client_max_body_size 10m` | ✅ Nginx rate limit đã đóng `G-02` trên Option B; Option A giữ `max_replicas` + timeouts. |
| **EoP** | Advisor thao tác chức năng Admin (`/evaluations/run`, `/audit-logs`) | Chỉ có guard phía FE (`FE-02`) | Chỉ có guard phía FE (`FE-02`) | 🔴 Chưa enforce RBAC `require_admin` / `require_advisor` phía backend (`BE-09`). |

### Luồng 2 — Backend API ↔ PostgreSQL (`TB-2`)

| STRIDE | Mối đe dọa | Control Dùng chung (Option A & Option B) | Trạng thái & Việc cần làm |
| :--- | :--- | :--- | :--- |
| **Spoofing / Tampering** | SQL Injection qua filter/search params | SQLAlchemy 2 parameterized queries + Pydantic validation (`_RUN_ID_RE`, query bounds) | ✅ An toàn ở tầng ORM/Validation. |
| **Info Disclosure** | PG lộ cổng ra Internet hoặc bị đọc quá quyền | **Option A:** Delegated subnet `snet-pg`, `public_network_access_enabled=false`, TLS `sslmode=require`.<br>**Option B:** `lg_backend_net` (`internal: true`), cổng `5432` không bind ra host, bị chặn bởi Cloud Firewall + `ufw`. | ✅ Đã khép kín Data Plane trên cả 2 cloud. |
| **EoP** | Backend vô tình hoặc bị khai thác sửa/xóa `ml_predictions` | Role `lg_api` chỉ có `GRANT SELECT ON public.ml_predictions`; toàn quyền backend chỉ giới hạn trên `users`, `briefs`, `decisions`, `llm_calls`, `audit_logs`, `chat_*`. | ✅ Đã enforce ở tầng PostgreSQL (`roles.sql`, `init-db.sh`). Cần thêm test kiểm chứng ở `BE-13`. |
| **DoS** | Cạn connection pool hoặc lộ DSN trong traceback `500` | `mem_limit: 1024m` / `1536m`; `/health` bắt exception trả `unreachable` | 🟡 Bổ sung test `BE-13` chứng minh lỗi DB trả `HTTP 503` sạch, không rò secret. |

### Luồng 3 — ML Batch Worker ↔ PostgreSQL & Artifact Storage (`TB-3`)

| STRIDE | Mối đe dọa | Control Dùng chung (Option A & Option B) | Trạng thái & Việc cần làm |
| :--- | :--- | :--- | :--- |
| **Tampering** | Dữ liệu OULAD hỏng hoặc bị tiêm sự kiện tương lai (`date > 27`) | `M1` quarantine + `M2` SHA-256 ledger + `M3 LeakageAuditor` (16 future-event probes) + `DriftMonitor` Semantic Scale Guard (`10x`) → Safe Mode (`DATA_QUALITY_OR_SEMANTIC_FAILURE`) | ✅ Đã kiểm chứng tự động qua `tests/test_drift_and_retraining.py`. |
| **Tampering (Model)** | Nạp nhầm model artifact bị sửa hoặc mô hình suy thoái | `verify-preprocessor`, `verify-model`, `verify-release` (SHA-256) + Champion-vs-Challenger Gate (`fail-closed`) + `BehavioralGate` + atomic `active_release.json` | ✅ Đã kiểm chứng cả positive & negative test (`tests/test_behavioral_gate.py`). |
| **EoP** | ML worker đọc bảng `users`/`briefs`/`audit_logs` hoặc drop bảng backend | Role `lg_ml_writer` chỉ sở hữu `public.ml_predictions`, không có quyền trên các bảng backend (`roles.sql`, `init-db.sh`). `api` mount `artifacts/` & `oulad/` ở chế độ `:ro` trên Option B. | ✅ Enforce ở tầng OS mount & PostgreSQL grants. |
| **Repudiation** | Không truy vết được batch run / model nào sinh ra dự đoán | Mọi dòng `ml_predictions` lưu `run_id`, `model_version`, `snapshot_version`, `cutoff_day`, `scored_at`; release lưu `release.provenance.json`. | ✅ Đã có đầy đủ provenance. |

### Luồng 4 — CI/CD & Container Supply Chain (`TB-4`)

| STRIDE | Mối đe dọa | Control trên Option A (Azure) | Control trên Option B (DigitalOcean) | Trạng thái & Việc cần làm |
| :--- | :--- | :--- | :--- | :--- |
| **Spoofing** | Lạm dụng credential deploy hoặc chiếm SSH | Self-hosted runner (`az login` user `HungTV88@fpt.com`), khóa ngoài PR fork; hoặc OIDC+UAMI khi có Admin | GitHub Environment `production` (hỗ trợ required reviewers), dedicated `ed25519` deploy key (`DO_SSH_KEY`), `PasswordAuthentication no`, `PermitRootLogin no`, SSH giới hạn `allowed_ssh_cidrs` | ✅ Tách biệt credential; cần cấu hình IP CIDR hẹp cho `allowed_ssh_cidrs` khi provision DO (`OPS-06`). |
| **Tampering** | Image chứa CVE nghiêm trọng hoặc bị thay thế tag `:latest` | Build từ SHA app cố định; deploy container bằng `@sha256` digest; `check_plan.py` chặn resource trái phép | `ci-build-and-scan.yml` chạy **Trivy (`exit-code: 1`, `CRITICAL,HIGH`)**, non-root `UID 10001`, ghim `@sha256` trong `prod.yaml` & `last_good_release.env` | ✅ Đã verify live GHCR digests sạch CVE (`e9f9c81`). |
| **Info Disclosure** | Lộ secret `.env`, `DATABASE_URL`, `LLM_API_KEY` trong log/git | Secrets trong Key Vault (`public_network_access_enabled=false`); `seed.sh` xóa `/tmp/lg.env` | `.env` quyền `chmod 600` (bị `.gitignore` chặn); `GHCR_PAT` truyền qua `--password-stdin` trong `cd-digitalocean-prod.yml`; tắt `set -x` ở shell | ✅ An toàn trên cả 2 luồng; luôn kiểm tra `git diff` không chứa secret. |

---

## 3. OWASP LLM Top 10 (2025) — Mô hình Đe dọa cho Brief Generator & Advisor Copilot (`TB-5`)

Do LearnGuard tích hợp **LLM** (`OpenRouter` qua `LiteLLM` + `Ollama qwen2.5:3b` fallback) để sinh Advisor Brief và trả lời Advisor Copilot Chat, kiến trúc áp dụng trực tiếp chuẩn phòng vệ **OWASP LLM Top 10**:

| Mã OWASP LLM | Mối đe dọa trong LearnGuard | Cơ chế Phòng vệ Hiện hữu (Verified in Code) | Rủi ro Còn lại / Việc cần làm |
| :--- | :--- | :--- | :--- |
| **LLM01: Prompt Injection** | Cố vấn nhập prompt độc hại vào `POST /briefs/chat/sessions/{id}/messages` nhằm bẻ hướng trợ lý (ví dụ: ép soạn email khuyên sinh viên nghỉ học hoặc bỏ qua ràng buộc trạng thái). | - `CHAT_SYSTEM_PROMPT` & `INTENT_DIRECTIVES` (`services/chat.py`) khóa cứng quy tắc đạo đức, kiểm tra `status` (`manual_review`, `insufficient_data`) và cấm tiết lộ thuật toán AI.<br>- Ép đầu ra JSON có cấu trúc (`STRUCTURED_OUTPUT_PROMPT`, `_parse_json_object`).<br>- LLM **không có bất kỳ tool-calling / code-execution** nào đụng vào DB hay hệ thống ngoài. | 🟡 Tiếp tục bổ sung adversarial prompt test cases trong `BE-MLOPS/tests/test_chat.py` & kiểm chứng trong `FE-12`. |
| **LLM02: Sensitive Information Disclosure (PII)** | Gửi `id_student`, tên, email thật của sinh viên ra nhà cung cấp LLM bên ngoài (`OpenRouter`), hoặc ghi prompt/response chứa thông tin nhạy cảm vào DB/log. | - `build_context` (`briefs.py`) và `build_chat_context` (`chat_context.py`) chỉ truyền `student_key` (SHA-256 16-hex) + các chỉ số hành vi tổng hợp.<br>- Bảng `llm_calls` (`DB_CONTRACT.md` §6.6) **tuyệt đối không lưu prompt/response text**, chỉ lưu `model`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `latency_ms`, `status`. | ✅ Đảm bảo 100% Data Minimization; tiếp tục audit log payload khi triển khai `observability.py` (`BE-11`). |
| **LLM05: Improper Output Handling & Hallucination** | LLM bịa số liệu không có trong hồ sơ, suy diễn nhân quả/tâm lý, hoặc trả markdown hỏng JSON làm crash Frontend. | - `AdvisorBriefService.validate_citations` lọc bỏ mọi `reason` trích dẫn feature không nằm trong `allowed_evidence` và ghi chú minh bạch vào `limitations`.<br>- `llm_judge.py` (`Gate 3`) kiểm định `no_fabrication` & `grounded` trên schema `eval-report.v1`.<br>- Parser phòng thủ ở cả backend (`_parse_draft`) và frontend (`client.ts`). | 🟡 `G-30`: Bổ sung `advisor_guidelines.md` vào luồng one-shot `briefs.py`. `G-32`: Hiệu chỉnh `llm_judge.py` với human annotations (`AI-06`). |
| **LLM06: Excessive Agency** | Hệ thống AI tự động gửi email cho sinh viên hoặc tự ý ghi đè điểm dự đoán `ml_predictions`. | - Zero student-facing endpoints (không có kênh gửi mail/SMS ra ngoài).<br>- Role `lg_api` bị PostgreSQL chặn ghi `ml_predictions`.<br>- Chính sách 100% Human-in-the-loop (`accept`/`edit`/`reject`). | 🔴 **`G-26` & `G-28`:** Cần nối lại nút Accept/Reject + `feedback` trên `StudentDetailPage.tsx` và `BriefDecisionRequestBody` để vòng kiểm soát con người hoàn chỉnh E2E. |
| **LLM10: Unbounded Consumption (Cost/DoS)** | Flood yêu cầu chat/brief làm tràn context window (8K) hoặc tăng chi phí OpenRouter bất thường. | - `LiteLLMClient._validate_input_tokens` chặn `LLM_MAX_INPUT_TOKENS = 8000` & `LLM_MAX_OUTPUT_TOKENS = 1000`.<br>- `prune_history_to_fit_token_budget` cắt lịch sử chat cũ; `DYNAMIC_MAX_TOKENS` giới hạn token theo intent.<br>- Failover 2 tầng: OpenRouter (timeout 30s) → `Ollama qwen2.5:3b` → Deterministic template `make_fallback` (`fallback_review`). | 🟡 Cần hoàn tất `BE-11` (`/metrics`) để theo dõi token/cost budget real-time và bật rate-limit per-user khi có JWT (`BE-08`). |

---

## 4. Rủi ro Chấp nhận & Điều kiện Gate trước Public Production

1. **Điều kiện Cấm Mở Public Internet (Hard Stop):** Cả Option A lẫn Option B **KHÔNG được mở truy cập công khai rộng rãi** khi `G-01` (`auth.py` `NotImplementedError`) chưa đóng. Trong giai đoạn phát triển/demo nội bộ trước khi đóng `BE-08`/`BE-09`, bắt buộc giữ IP allowlist (DigitalOcean Cloud Firewall `allowed_ssh_cidrs` / `ufw` hoặc Azure Container Apps IP restriction).
2. **Rủi ro Chấp nhận trên Option A (Azure Sandbox):** `1 role-assignment` cho CI OIDC/UAMI do Tenant Admin cấp (`runbooks/admin-requests.md`) và các policy `FSO-SZ` là ràng buộc của subscription FPT (`AZURE_CONSTRAINTS.md`), được xử lý bằng Jump VM + self-hosted runner.
3. **Rủi ro Chấp nhận trên Option B (DigitalOcean Single-VM):** Chấp nhận trade-off không có multi-node DB HA (`G-04`), bù đắp bằng `backup-db.sh` tự động trước mọi deploy + cron hàng ngày + DO Automated Backups + Terraform IaC khôi phục `< 15 phút`.
