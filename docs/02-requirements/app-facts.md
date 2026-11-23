# Đối chiếu Hiện trạng Mã nguồn 4 Kho (Verified Repository Facts — Snapshot 2026-11-23)

> **Mục đích:** Tổng hợp sự thật đã xác minh trực tiếp từ mã nguồn của 4 kho (`learnguard-platform`, `BE-MLOPS`, `Data-ML-MLOPS`, `FE-MLOPS`) làm căn cứ đầu vào cho [requirements.md](requirements.md), [traceability.md](traceability.md) và kế hoạch 4 thành viên.
> **Snapshot Commit SHA (đã kiểm chứng trên nhánh `main` ngày 2026-11-23):**

| Kho mã nguồn | HEAD SHA | Nhánh | Vai trò |
| :--- | :--- | :--- | :--- |
| `learnguard-platform` | `e9f9c81` | `main` | Platform Orchestrator, IaC Dual-Cloud (Option A Azure + Option B DigitalOcean), Dockerfiles, Compose, Nginx, CI/CD GHCR, Drift & Retraining Engine |
| `BE-MLOPS` (`ntk223/BE-MLOPS`) | `a2bae92` | `main` | FastAPI Modular Monolith (M6–M8, Briefs, Chat, Evaluations, Audit Logs) |
| `Data-ML-MLOPS` (`ntk223/Data-ML-MLOPS`) | `72c96cd` | `main` | Data Pipeline M1–M3, ML M4–M5, Linear SHAP, Evaluation Gates (`data`, `ml`, `llm`) |
| `FE-MLOPS` (`ntk223/FE-MLOPS`) | `0f70e14` | `main` | React 18 + TypeScript 5.7 + Vite 5.4 Advisor & Admin Dashboard (M9) |

---

## 1. Kho `BE-MLOPS` (`a2bae92`)

### 1.1. Kiến trúc & Những phần Đã Hoàn thiện
- **Stack:** Python `>=3.10`, FastAPI, `uvicorn[standard]`, SQLAlchemy 2, `psycopg[binary]`, `pydantic-settings`, `litellm`, `tenacity`, `python-jose`, `passlib[bcrypt]`, `alembic` (`migrations/`).
  - *Lưu ý build container:* `alembic` **không** nằm trong `dependencies` của `pyproject.toml` → `Dockerfile.api` cài bổ sung `alembic`.
  - *Entrypoint:* `uvicorn learnguard_backend.main:app --host 0.0.0.0 --port 8000` (nếu chạy `main.py` trực tiếp sẽ bind `127.0.0.1:8000`).
- **Hợp đồng DB:** [DB_CONTRACT.md](../../../BE-MLOPS/docs/DB_CONTRACT.md) — Backend sở hữu `users`, `briefs`, `decisions`, `llm_calls`, `audit_logs`, `chat_sessions`, `chat_messages`; **chỉ `SELECT`** trên `ml_predictions`.
- **Các route đã hoạt động:** `/health`, `/predictions`, `/predictions/stats`, `/predictions/{m}/{p}/{s}`, `/predictions/by-student/{s}`, `/predictions/{m}/{p}/{s}/activity`, `/briefs/generate`, `/briefs/{id}` (`GET`/`PUT`), `/briefs/{id}/decision`, `/briefs/chat/*`, `/evaluations`, `/evaluations/{run_id}`, `/evaluations/run`, `/evaluations/run-status`, `/audit-logs`.
- **Kiểm thử hiện có:** 9 suites trong `BE-MLOPS/tests/` (`test_app`, `test_predictions_api`, `test_briefs`, `test_chat`, `test_evaluations_api`, `test_audit_logs_api`, `test_llm`, `test_ml_predictions`, `test_student_keys`).

### 1.2. Các Lỗ hổng Thực tế Đã Xác minh trong Code (In-Scope Gaps)
| Vị trí Code | Hiện trạng Thực tế | Task Đóng Gap |
| :--- | :--- | :--- |
| `src/learnguard_backend/api/auth.py` (`AuthenticationService`) | Toàn bộ phương thức (`authenticate`, `create_access_token`, `require_role`) hiện `raise NotImplementedError`. | `BE-08`, `BE-09` |
| `src/learnguard_backend/db/repository.py:582` & `api/app.py` | Dùng `SYSTEM_EMAIL = "system@learnguard.local"` thay cho user đang đăng nhập trong `briefs`, `decisions`, `chat_sessions`, `audit_logs`. | `BE-10` |
| `src/learnguard_backend/observability.py` | `StructuredLogger`, `MetricsCollector`, `write_run_summary` hiện `raise NotImplementedError`; chưa có endpoint `/metrics` để `deploy/digitalocean/prometheus.yml` scrape `api:8000`. | `BE-11` |
| `src/learnguard_backend/services/student_activity.py` & `api/app.py` | Chưa cache ánh xạ `student_key -> id_student` theo `(code_module, code_presentation)`; chưa có endpoint/field đọc `eval_behavioral.json`, `drift-report.v1`, `active_release.json` cho Admin UI. | `BE-12` |
| `src/learnguard_backend/api/app.py:206` (`BriefDecisionRequestBody`) | Chỉ nhận `decision: str`, **thiếu trường `feedback`** dù bảng `decisions` trong `DB_CONTRACT.md` §6.5 có `feedback TEXT NULL`. | `BE-14` |
| `src/learnguard_backend/api/app.py` | Thiếu `GET /predictions/{m}/{p}/{s}/brief` để tải lại active brief + lịch sử decision khi reload trang. | `BE-14` |
| `src/learnguard_backend/services/briefs.py` (`BRIEF_SYSTEM_PROMPT`) | Chỉ `chat_context.py` nạp `advisor_guidelines.md`; luồng one-shot `AdvisorBriefService` **chưa nạp `advisor_guidelines.md`** và thiếu bộ lọc deterministic chặn phát ngôn nhân quả/tâm lý/PII trước khi trả output. | `BE-14` |

---

## 2. Kho `Data-ML-MLOPS` (`72c96cd`)

### 2.1. Dữ liệu OULAD & Baseline Thực nghiệm Đã Xác minh
- **Dữ liệu nguồn (`Data-ML-MLOPS/data/archive.zip`):** 43 MB nén / 464.4 MB giải nén:
  - `courses.csv`: 22 dòng (7 học phần `AAA..GGG`, 4 kỳ `2013B, 2013J, 2014B, 2014J`).
  - `studentInfo.csv`: 32,593 dòng (`Pass` 12,361 / 37.9%, `Distinction` 3,024 / 9.3%, `Fail` 7,052 / 21.6%, `Withdrawn` 10,156 / 31.2%).
  - `studentVle.csv`: 10,655,280 dòng (~453.8 MB); `studentAssessment.csv`: 173,912 dòng; `assessments.csv`: 206 dòng (11 Exams null date bị loại); `vle.csv`: 6,364 dòng.
- **Cohort tại `cutoff_day = 27`:** Loại 5,040 SV rút học `<= 27` + 18 SV đăng ký `> 27` → **27,535 dòng** (`train` `2013B+2013J`: 11,811 / 44.4% at-risk; `validation` `2014B`: 6,510 / 48.4% at-risk; `holdout` `2014J`: 9,214 / 40.8% at-risk — **SINGLE-USE CONSUMED**, không tái sử dụng cho tuning).
- **Đặc trưng:** 15 cột đầu vào → 38 cột `float64` sau mã hóa (4 hành vi `date<=27`, 3 học tập, 6 nhóm nhân khẩu học/nhạy cảm + `imd_band_missing` không gửi sang DB/LLM, kèm `insufficient_data`).
- **Mô hình & Benchmark (`benchmark-20261105-shap`, `logistic-production-20261105`):**
  - Production incumbent: `Logistic Regression v2` (`logreg-v2:cea6cdea:48843ee8:1ccd9891`), ngưỡng Top-20% Alert Budget `0.8103480496322563`; Linear SHAP `max additivity error = 1.78e-15`.
  - Benchmark 5 mô hình: `HistGradientBoosting B` đạt PR-AUC `0.7211` / ROC-AUC `0.7283` trên validation; holdout một lần PR-AUC `0.5832` / ROC-AUC `0.6956` / Recall@top-20% `0.3007`.
- **Kiểm thử hiện có:** `pytest tests/ -q` → **`163 passed, 8 skipped`** (8 test Postgres skip khi không có DB local).
- **Lưu ý wrapper CLI:** `cli.py` dùng default tương đối `Path("artifacts")` và argparse không tự đọc env `LEARNGUARD_ARTIFACTS_DIR`, nên container wrapper phải truyền `--artifacts-dir` hoặc đặt đúng `WORKDIR`.

### 2.2. Các Lỗ hổng Thực tế Đã Xác minh trong Code (In-Scope Gaps)
| Vị trí Code | Hiện trạng Thực tế | Task Đóng Gap |
| :--- | :--- | :--- |
| `src/learnguard/evaluation/ml_gate.py:42` | `FAIRNESS_COLUMN = "gender"` — chỉ kiểm tra 1/6 chiều protected slices; thiếu ngưỡng kiểm định Calibration (`ECE`/`Brier`) và đường cong FPR / Multi-K (`10%/20%/30%`). | `ML-11` |
| `src/learnguard/ml/` & `docs/` | Thiếu phân tích chuyên sâu False Negatives tại tuần 4 và chưa đánh giá non-linear challenger (`HistGradientBoostingClassifier` + TreeSHAP/permutation) riêng trên `validation` (`2014B`). | `ML-12` |
| `src/learnguard/evaluation/llm_judge.py` & `llm_gate.py` | Chưa hiệu chỉnh LLM-as-a-Judge với 30 golden briefs chấm tay 2 người; chưa chấm mức tuân thủ `advisor_guidelines.md` và chưa có red-team / prompt-injection tests cho Chat Copilot. | `AI-06` |
| Thử nghiệm Giá trị Sản phẩm | Chưa có số liệu thực nghiệm so sánh thời gian/chất lượng cố vấn rà soát hồ sơ có vs không có LearnGuard AI. | `AI-07` |

---

## 3. Kho `FE-MLOPS` (`0f70e14`)

### 3.1. Hiện trạng Build & Kiến trúc
- React 18.3, React Router 6, TypeScript 5.7, Vite 5.4 (`npm ci && npm run build` = `tsc --noEmit && vite build`).
- Các trang đã có: `LoginPage`, `OverviewPage`, `AdvisorDashboardPage`, `StudentDetailPage`, `EvaluationsPage`, `AuditPage`, `AdvisorChatDrawer`.

### 3.2. Các Lỗ hổng Thực tế Đã Xác minh trong Code (In-Scope Gaps)
| Vị trí Code | Hiện trạng Thực tế | Task Đóng Gap |
| :--- | :--- | :--- |
| `src/api/index.ts:82` | `login: (credentials) => mock.login(credentials)` vẫn gọi mock login thay vì real JWT `POST /auth/login`. | `FE-09` |
| `src/pages/EvaluationsPage.tsx:24` | `SubjectFilter = 'all' | 'data' | 'ml' | 'llm'` — thiếu tab `behavioral` (`eval_behavioral.json`), thiếu card Drift Monitor (`drift-report.v1`), Active Release (`active_release.json`) và LLM Latency/Cost. | `FE-10` |
| `src/pages/StudentDetailPage.tsx` | Đã có `Edit brief`, nhưng **chưa nối nút Chấp nhận / Từ chối + ô nhập Feedback cố vấn** (`saveBriefDecision`) và chưa tải lại active brief + lịch sử decision khi reload trang. | `FE-13` |
| `src/pages/AdvisorDashboardPage.tsx:51-65` | `MODULE_OPTIONS` hardcode 5/7 học phần (`AAA..EEE`, thiếu `FFF`, `GGG`); `PRESENTATION_OPTIONS` hardcode 3/4 kỳ (`2013J, 2014B, 2013B`, thiếu `2014J`) thay vì đọc động từ `/predictions/stats`; thiếu badge trạng thái triage (chờ duyệt vs đã accept/reject). | `FE-13` |
| `tests/` | `tests/run.mjs` & `tests/test-chat.ts` mới kiểm tra một phần client; thiếu unit tests cho đủ 4 `PredictionStatus`, `fallback_review`, `401/403/503`, Accessibility (a11y) và Playwright E2E Human Oversight. | `FE-11`, `FE-12` |

---

## 4. Kho `learnguard-platform` (`e9f9c81`)

- **Đã hoàn tất & kiểm chứng (`e9f9c81`):**
  - 4/4 GitHub Actions workflows chạy **XANH** (`ci-platform.yml`, `ci-build-and-scan.yml` Trivy `exit-code: 1` + GHCR `@sha256` digests ghim trong `deploy/releases/prod.yaml`, `cd-digitalocean-prod.yml`, `mlops-drift-retrain.yml`).
  - `deploy/ml/` (`drift_monitor.py`, `data_simulator.py` 5 kịch bản, `behavioral_gate.py`, `retrain_pipeline.py` + `--mode rollback`) pass `pytest` (`6 passed`) & `ruff check` (`0 errors`).
  - Có sẵn 2 phương án hạ tầng IaC (**Dual-Cloud Deploy-Where-Available**):
    - **Option A (Azure PaaS):** `infra/env/dev/` (`terraform validate/plan` 39 resources sạch guardrail `AZURE_CONSTRAINTS.md`) + `cd-dev-*.yml`.
    - **Option B (DigitalOcean Droplet VM):** `infra/digitalocean/` + `deploy/digitalocean/` (`docker-compose.prod.yml`, `init-db.sh` 2 roles `lg_api`/`lg_ml_writer`, `prometheus.yml`, `nginx.fe.conf`) + `scripts/cd/` & `scripts/db/`.
- **Còn lại:** Triển khai live lên nhà cung cấp cloud khả dụng (`OPS-06` Option B DO VM hoặc `OPS-08` Option A Azure PaaS parity) và diễn tập GameDay Safeguard/Rollback (`OPS-07`).
