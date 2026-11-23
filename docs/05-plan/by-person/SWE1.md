# Kế hoạch Công việc Chi tiết: SWE1 — Software Engineer 1 (Backend API, Auth/RBAC, Persistence & Telemetry)

> **Vai trò:** Chủ sở hữu `BE-MLOPS` (FastAPI Modular Monolith: M6 Authentication & RBAC, M7 Persistence, Audit Trail, Student Activity API, One-Shot Guidelines & Observability).
> **Kho mã nguồn chính:** `ntk223/BE-MLOPS` (`src/learnguard_backend/api/`, `db/`, `migrations/`, `services/`, `observability.py`, `settings.py`, `tests/`).
> **Hợp đồng bắt buộc tuân thủ:** [DB_CONTRACT.md](../../../../BE-MLOPS/docs/DB_CONTRACT.md) và [API_CONTRACT.md](../../../../FE-MLOPS/docs/API_CONTRACT.md).
> **Quy tắc bất biến:** Backend chỉ `SELECT` trên bảng `ml_predictions` (qua role `lg_api`), tuyệt đối không `INSERT`/`UPDATE`/DDL trên `ml_predictions`.

**Định nghĩa Hoàn thành (DoD):** `python -m unittest discover -s tests -v` pass 100%, `ruff check .` sạch, mọi endpoint mới có ghi `audit_logs`, không chứa PII hoặc secret trong log, cập nhật `API_CONTRACT.md` nếu thêm/sửa schema response.

Tổng cộng (**khớp 100% [backlog.csv](../backlog.csv)**): **14 tasks (50 giờ)**. Đã hoàn thành: **7 tasks (`☑`, 26 giờ)** · Đang làm: **1 task (`◐`, 4 giờ)** · Cần làm tiếp: **6 tasks (`☐`, 20 giờ)**.

---

## Giai đoạn Baseline — Đã hoàn thành trên nhánh `main` (`a2bae92`) (26 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `BE-01` | Khởi tạo FastAPI App Factory, Settings, `/health` & SQLAlchemy 2 + Alembic Migrations | `GET /health` kiểm tra kết nối DB (`SELECT 1`) và trạng thái LLM; 7 bảng backend sở hữu tạo sạch qua Alembic. | 4 | — | `ENABLER` / `FR-08` |
| ☑ | `BE-02` | Triển khai API Đọc Dự đoán (`/predictions`, `/stats`, `/{m}/{p}/{s}`, `/by-student/{s}`) | Phân trang, lọc theo `status`/`code_module`/`code_presentation`, sắp xếp `DESC NULLS LAST`, xử lý đủ 4 trạng thái `PredictionStatus`. | 4 | `BE-01` | `US-05` / `FR-04` |
| ☑ | `BE-03` | Triển khai API Hành vi Sinh viên 4 Tuần (`GET /predictions/{m}/{p}/{s}/activity`) | Đảo ngược `student_key` an toàn trong phạm vi học phần từ `OULAD_DATA_DIR`, tổng hợp 5 bucket tuần + timeline bài nộp + category breakdown. | 4 | `BE-02` | `US-06` / `FR-04` |
| ☑ | `BE-04` | Triển khai Persistence & Endpoints cho Advisor Briefs (`generate`, `get`, `PUT`, `decision`) | Lưu `briefs`, chỉnh sửa tại chỗ giữ `source_history`, lưu `decisions` (`accept`/`reject`) và `llm_calls`. | 4 | `BE-01` | `US-08` / `FR-06` |
| ☑ | `BE-05` | Triển khai API Advisor Chatbot (`/briefs/chat/*`) | Quản lý phiên chat theo `(code_module, code_presentation, student_key)`, lưu hội thoại và tổng hợp thành Brief (`finalize-brief`). | 4 | `BE-04` | `US-09` / `FR-06` |
| ☑ | `BE-06` | Triển khai API Scorecard Đánh giá Tự động (`/evaluations*`) | Đọc atomic scorecards (`eval-report.v1`) từ `EVALUATIONS_DIR`, tổng hợp `combined_summary` và chạy background runner có mutex lock. | 3 | `BE-01` | `US-13` / `FR-09` |
| ☑ | `BE-07` | Triển khai API Nhật ký Hệ thống (`GET /audit-logs`) & ghi vết tự động | Lọc theo `action` và `entity`, trả distinct `actions`/`entities`; không tự ghi log khi đọc `/audit-logs`. | 3 | `BE-01` | `US-12` / `FR-09` |

---

## Sprint 1 — Hoàn thiện Bảo mật M6 (Auth/RBAC) & Đóng Gap Brief/Guidelines (`BE-14`) (16 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ◐ | `BE-08` | **M6 Authentication API (`POST /auth/login`, `GET /auth/me`)** | Thay thế `NotImplementedError` trong `api/auth.py` (`AuthenticationService`): xác thực email/password bằng bcrypt/argon2 đối chiếu bảng `users`, cấp JWT ký số có claim `role`, ghi `audit_logs` (`login_success`/`login_failed`). | 4 | `BE-01` | `US-12` / `FR-09` |
| ☐ | `BE-09` | **RBAC Dependencies (`require_advisor`, `require_admin`)** | Bảo vệ các route `/predictions*`, `/briefs*`, `/evaluations*`, `/audit-logs` (trả `401`/`403` chuẩn), hỗ trợ cờ `AUTH_REQUIRED` để tương thích test contract. | 4 | `BE-08` | `US-12` / `FR-09` |
| ☐ | `BE-10` | **Thay thế `system@learnguard.local` bằng Principal Thực tế** | Xóa fallback `SYSTEM_EMAIL = "system@learnguard.local"` tại `db/repository.py:582` & `api/app.py`; ghi `user_id` và `email` thật từ JWT vào `briefs`, `decisions`, `chat_sessions`, `audit_logs`. | 4 | `BE-09` | `US-10` / `FR-07` |
| ☐ | `BE-14` | **Đóng 3 Gap Brief Oversight & Guardrails (`app.py:206` & `services/briefs.py`)** | (1) Thêm trường `feedback: str \| None` vào `BriefDecisionRequestBody` (`POST /briefs/{id}/decision`, khớp `DB_CONTRACT.md` §6.5 `decisions.feedback`);<br>(2) Thêm `GET /predictions/{m}/{p}/{s}/brief` trả active brief + lịch sử decision để giữ trạng thái qua reload;<br>(3) Nạp `advisor_guidelines.md` + bộ lọc deterministic (chặn phát ngôn nhân quả/tâm lý/PII) vào one-shot `AdvisorBriefService.generate()`. | 4 | `BE-04` | `US-10` / `FR-07` |

---

## Sprint 2 — Observability (`/metrics`), Tối ưu Caching & Kiểm thử Chịu lỗi (8 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☐ | `BE-11` | **Triển khai `observability.py` & Prometheus `/metrics`** | Thay thế `NotImplementedError` trong `observability.py` bằng JSON `StructuredLogger` (lọc PII + gắn `request_id`), `MetricsCollector`, và endpoint `GET /metrics` (API latency p50/p95, 4xx/5xx, LLM cost/tokens/fallback rate) để `deploy/digitalocean/prometheus.yml` scrape `api:8000`. | 3 | `BE-04` | `US-13` / `NFR-PERF1` |
| ☐ | `BE-12` | **Tối ưu Cache `student_activity.py` & Expose Admin Readouts** | Cache ánh xạ `(code_module, code_presentation, student_key) -> id_student` giúp `/activity` lặp lại `< 300ms`; đồng thời expose endpoint/trường read-only cho Admin đọc `eval_behavioral.json`, `drift-report.v1` và `active_release.json`. | 3 | `BE-03` | `US-06` / `NFR-PERF1` |
| ☐ | `BE-13` | **Kiểm thử Chịu lỗi DB & Hợp đồng Read-Only `lg_api`** | Viết `test_db_roles_and_resilience.py`: chứng minh DB outage trả `503` sạch (không lộ DSN/stacktrace) và không có bất kỳ đường ghi nào tới `ml_predictions` dưới quyền `lg_api`. | 2 | `BE-09`, `OPS-02` | `US-11` / `FR-08` |
