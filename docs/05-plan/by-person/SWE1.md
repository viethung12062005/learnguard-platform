# Kế hoạch Công việc Chi tiết: SWE1 — Software Engineer 1 (Backend API, Auth/RBAC, Persistence & Telemetry)

> **Vai trò:** Chủ sở hữu `BE-MLOPS` (FastAPI Modular Monolith: M6 Authentication & RBAC, M7 Persistence, Audit Trail, Student Activity API & Operational Metrics).
> **Kho mã nguồn chính:** `ntk223/BE-MLOPS` (`src/learnguard_backend/api/`, `db/`, `migrations/`, `observability.py`, `settings.py`, `tests/`).
> **Hợp đồng bắt buộc tuân thủ:** [DB_CONTRACT.md](../../../BE-MLOPS/docs/DB_CONTRACT.md) và [API_CONTRACT.md](../../../FE-MLOPS/docs/API_CONTRACT.md).
> **Quy tắc bất biến:** Backend chỉ `SELECT` trên bảng `ml_predictions` (qua role `lg_api`), tuyệt đối không `INSERT`/`UPDATE`/DDL trên `ml_predictions`.

**Định nghĩa Hoàn thành (DoD) cho mọi Task:** `python -m unittest discover -s tests -v` pass 100%, `ruff check .` sạch, mọi endpoint mới có ghi `audit_logs`, không chứa PII hoặc secret trong log, cập nhật `API_CONTRACT.md` nếu thêm/sửa schema response.

Tổng cộng: **13 tasks (46 giờ)**. Đã hoàn thành trong Baseline: **7 tasks (`☑`, 26 giờ)**, Đang làm: **1 task (`◐`)**, Cần làm tiếp: **5 tasks (`☐`, ~20 giờ)**.

---

## Giai đoạn Baseline — Đã hoàn thành trên nhánh `main` (`a2bae92`) (26 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `BE-01` | Khởi tạo FastAPI App Factory, Settings, `/health` & SQLAlchemy 2 + Alembic Migrations (`1de0e14023d0`, `4b5c6d7e8f90`) | `GET /health` kiểm tra kết nối DB (`SELECT 1`) và trạng thái cấu hình LLM; 7 bảng backend sở hữu tạo sạch qua Alembic. | 4 | — | `FR-08`, `FR-09` |
| ☑ | `BE-02` | Triển khai API Đọc Dự đoán: `GET /predictions`, `GET /predictions/stats`, `GET /predictions/{m}/{p}/{s}`, `GET /predictions/by-student/{s}` | Phân trang, lọc theo `status`/`code_module`/`code_presentation`, sắp xếp `DESC NULLS LAST`, xử lý đủ 4 trạng thái (`scored`, `manual_review`, `insufficient_data`, `no_prediction`). | 4 | `BE-01` | `FR-04`, `FR-05` |
| ☑ | `BE-03` | Triển khai API Hành vi Sinh viên 4 Tuần: `GET /predictions/{m}/{p}/{s}/activity` (`student_activity.py`) | Đảo ngược `student_key` an toàn trong phạm vi học phần từ `OULAD_DATA_DIR`, tổng hợp 5 bucket tuần + timeline bài nộp + breakdown theo loại tài liệu; trả `404`/`503` chuẩn. | 4 | `BE-02` | `FR-04`, `FR-05` |
| ☑ | `BE-04` | Triển khai Persistence & Endpoints cho Advisor Briefs (`POST /briefs/generate`, `GET /briefs/{id}`, `PUT /briefs/{id}`, `POST /briefs/{id}/decision`) | Lưu trữ `briefs` (tăng version khi regenerate, giữ nguyên version khi advisor edit kèm `edited_at`/`source_history`), lưu `decisions` (`accept`/`reject`) và `llm_calls`. | 4 | `BE-01` | `FR-06`, `FR-07` |
| ☑ | `BE-05` | Triển khai API Advisor Chatbot: `GET /briefs/chat/quick-prompts`, `POST /briefs/chat/sessions`, `GET/POST .../messages`, `POST .../finalize-brief` | Quản lý phiên chat theo `(code_module, code_presentation, student_key)`, lưu lịch sử hội thoại và tổng hợp thành Brief chính thức (`status = finalized`). | 4 | `BE-04` | `FR-06`, `FR-07` |
| ☑ | `BE-06` | Triển khai API Scorecard Đánh giá Tự động: `GET /evaluations`, `GET /evaluations/{run_id}`, `POST /evaluations/run`, `GET /evaluations/run-status` | Đọc atomic scorecards (`eval-report.v1`) từ `EVALUATIONS_DIR`, tổng hợp `combined_summary` và `overall_status`; hỗ trợ chạy background runner có mutex lock. | 3 | `BE-01` | `FR-09`, `NFR-ML1` |
| ☑ | `BE-07` | Triển khai API Nhật ký Hệ thống: `GET /audit-logs` & ghi vết tự động trên mọi route nghiệp vụ | Lọc theo `action` và `entity`, trả danh sách distinct `actions`/`entities` cho bộ lọc UI; không tự ghi log khi đọc `/audit-logs` để tránh nhiễu. | 3 | `BE-01` | `FR-09`, `NFR-SEC1` |

---

## Sprint 1 — Hoàn thiện Bảo mật M6 (JWT Auth & RBAC) và Truy vết Người dùng Thật (12 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ◐ | `BE-08` | **M6 Authentication API (`POST /auth/login`, `GET /auth/me`)** với JWT (`python-jose`) và Bcrypt (`passlib`) | Xác thực email/password từ bảng `users` (seed sẵn `advisor@learnguard.vn` và `admin@learnguard.vn`); trả JWT token có claims `sub`, `email`, `role`, `exp`; ghi `audit_logs` cho cả `login_success` và `login_failed` (`401`). | 4 | `BE-01` | `FR-09`, `NFR-SEC1` |
| ☐ | `BE-09` | **RBAC Dependency Middleware (`require_advisor`, `require_admin`)** kèm cờ tương thích `AUTH_REQUIRED` | Bảo vệ các route `/predictions*`, `/briefs*` (cho `advisor` & `admin`) và `/audit-logs`, `POST /evaluations/run` (chỉ `admin`, trả `403 Forbidden` nếu `advisor` gọi). Hỗ trợ `AUTH_REQUIRED=true|false` để không làm gãy các bài test contract hiện có. | 4 | `BE-08` | `FR-09`, `NFR-SEC1` |
| ☐ | `BE-10` | **Thay thế `system@learnguard.local` bằng Principal Thực tế** trong Briefs, Decisions, Chat Sessions & Audit Logs | Xóa các `TODO(M6 auth)` tại `app.py` (L1142, L1193, L1268, L1466, L1581): lấy `user_id` và `email` trực tiếp từ JWT token của cố vấn đang đăng nhập; viết unit test kiểm tra `actor_email` trong `GET /audit-logs`. | 4 | `BE-09` | `FR-07`, `FR-09` |

---

## Sprint 2 — Observability, Hiệu năng & Kiểm thử Chịu lỗi (8 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☐ | `BE-11` | **Endpoint Telemetry & Metrics (`GET /metrics` hoặc `GET /ops/telemetry`)** báo cáo p50/p95 Latency & Chi phí LLM | Truy vấn bảng `llm_calls` và in-memory request histogram để xuất chỉ số: tổng số request, p50/p95 latency tạo Brief (`latency_ms`), tổng `prompt_tokens`/`completion_tokens`, tổng `cost_usd`, và tỷ lệ failover/error theo model; đáp ứng yêu cầu System Performance của đề bài §4. | 3 | `BE-04` | `NFR-PERF1` |
| ☐ | `BE-12` | **Tối ưu Cache & Hiệu năng Đọc `OULAD_DATA_DIR` trong `student_activity.py`** | Bổ sung LRU/TTL cache cho ánh xạ `(code_module, code_presentation, student_key) -> id_student` và chỉ đọc các cột cần thiết từ `studentVle.csv` để giảm thời gian phản hồi `GET /predictions/.../activity` xuống `< 300ms` ở lần gọi thứ hai. | 3 | `BE-03` | `NFR-PERF1` |
| ☐ | `BE-13` | **Kiểm thử Chịu lỗi & Phân quyền Database (`test_db_roles_and_resilience.py`)** | Viết bộ test kiểm chứng: (1) Khi DB mất kết nối → `/health` trả `database: unreachable` (200) và các route dữ liệu trả `503` rõ ràng không lộ stacktrace/DSN; (2) Không có bất kỳ phương thức ghi nào trên `SQLPredictionRepository`. | 2 | `BE-09`, `OPS-02` | `FR-08`, `NFR-SEC1` |
