# Kế hoạch Công việc Chi tiết: SWE2 — Software Engineer 2 (Frontend Advisor Dashboard, Human Oversight UX & E2E Testing)

> **Vai trò:** Chủ sở hữu `FE-MLOPS` (M9 React 18 + TypeScript 5.7 + Vite 5.4 Advisor & Admin Dashboard).
> **Kho mã nguồn chính:** `ntk223/FE-MLOPS` (`src/`, `tests/`, `docs/API_CONTRACT.md`).
> **Hợp đồng bắt buộc tuân thủ:** [API_CONTRACT.md](../../../../FE-MLOPS/docs/API_CONTRACT.md) và nguyên lý **Intelligence Experience & Human Oversight** ([00-conventions.md](../../00-conventions.md)).
> **Quy tắc bất biến:** Frontend chỉ gọi Backend qua REST API; luôn hiển thị disclaimer phi nhân quả; mọi hành động hỗ trợ sinh viên đều phải qua cố vấn xem xét, feedback và xác nhận.

**Định nghĩa Hoàn thành (DoD):** `npm run build` (`tsc --noEmit && vite build`) và `node tests/run.mjs` (cùng Vitest/Playwright khi có) pass 100%, giao diện xử lý phòng thủ mọi dữ liệu lỗi/rỗng mà không crash, tuân thủ phân quyền `advisor` vs `admin`.

Tổng cộng (**khớp 100% [backlog.csv](../backlog.csv)**): **13 tasks (46 giờ)**. Đã hoàn thành: **8 tasks (`☑`, 26 giờ)** · Đang làm: **1 task (`◐`, 4 giờ)** · Cần làm tiếp: **4 tasks (`☐`, 16 giờ)**.

---

## Giai đoạn Baseline — Đã hoàn thành trên nhánh `main` (`0f70e14`) (26 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `FE-01` | Xây dựng Typed API Client (`src/api/client.ts`) & Mock Client với Timeout/AbortController | Chuẩn hóa lỗi `ApiError { code, message }`, chuyển đổi `snake_case ↔ camelCase` phòng thủ. | 4 | — | `ENABLER` / `FR-04` |
| ☑ | `FE-02` | Xây dựng Khung Ứng dụng (`AppShell`), Định tuyến Phân quyền & `OverviewPage` | Tách menu Cố vấn và Quản trị với route guards và số liệu tổng quan. | 3 | `FE-01` | `US-05` / `FR-04` |
| ☑ | `FE-03` | Xây dựng Hàng đợi Ưu tiên Cố vấn (`AdvisorDashboardPage`) | Lọc theo học phần, kỳ học, trạng thái, sắp xếp theo `risk_score` / `uncertainty` và phân trang. | 4 | `FE-01`, `BE-02` | `US-05` / `FR-04` |
| ☑ | `FE-04` | Xây dựng Trang Hồ sơ Sinh viên (`StudentDetailPage`) — SHAP, Uncertainty & Disclaimer | Hiển thị `riskScore`, `threshold`, thanh `uncertainty`, top 5 SHAP signals kèm cảnh báo phi nhân quả và `insufficient_data` / `manual_review`. | 4 | `FE-03` | `US-07` / `FR-05` |
| ☑ | `FE-05` | Xây dựng Card Hành vi 4 Tuần trên `StudentDetailPage` (`/activity`) | Biểu đồ cột click 5 mốc tuần, timeline bài nộp (TMA/CMA) và chips phân loại tài liệu; graceful degradation khi 404/503. | 3 | `FE-04`, `BE-03` | `US-06` / `FR-04` |
| ☑ | `FE-06` | Xây dựng Luồng Tạo, Chỉnh sửa tại chỗ & Huy hiệu Trạng thái Brief | Tạo, chỉnh sửa brief tại chỗ và hiển thị rõ badge `fallback_review` / `unavailable`. | 4 | `FE-04`, `BE-04` | `US-08` / `FR-07` |
| ☑ | `FE-07` | Xây dựng Ngăn Chat Trợ lý Cố vấn (`AdvisorChatDrawer`) & `finalize-brief` | Starter prompts, trích dẫn bằng chứng từng lượt trả lời, tổng hợp hội thoại thành Brief chính thức. | 2 | `FE-06`, `BE-05` | `US-09` / `FR-06` |
| ☑ | `FE-08` | Xây dựng Trang Đánh giá (`EvaluationsPage`) & Nhật ký (`AuditPage`) | Hiển thị scorecard `eval-report.v1` và bảng tra cứu `audit_logs` cho vai trò `admin`. | 2 | `FE-02`, `BE-06`, `BE-07` | `US-13` / `FR-09` |

---

## Sprint 1 — Tích hợp Auth Thật, Behavioral/Telemetry UI & Đóng Gap Oversight (`FE-13`) (12 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ◐ | `FE-09` | **Tích hợp Đăng nhập JWT Thật (`POST /auth/login`) trong `LearnGuardApiClient` & `LoginPage`** | Thay `mock.login(credentials)` tại `src/api/index.ts:82` bằng real JWT auth, đính kèm header `Authorization: Bearer`, tự điều hướng `/login` khi `401`, giữ `VITE_USE_MOCK_AUTH` tách biệt an toàn. | 4 | `BE-08`, `BE-09` | `US-12` / `FR-09` |
| ☐ | `FE-10` | **Hiển thị Behavioral Gate, Drift Monitor, Active Release & LLM Telemetry trên `EvaluationsPage`** | Cập nhật `EvaluationsPage.tsx` (`SubjectFilter`) để hiển thị `eval_behavioral.json`, báo cáo `drift-report.v1`, `active_release.json` và p50/p95 latency + chi phí LLM từ `/metrics` / Admin API (`BE-11`, `BE-12`). | 4 | `MLO-02`, `BE-11`, `BE-12` | `US-13` / `NFR-ML3` |
| ☐ | `FE-13` | **Nối UI Chấp nhận/Từ chối + Feedback, Sửa Bộ lọc 7 Học phần/4 Kỳ & Thêm Triage Badges** | (1) Nối nút **Accept / Reject + ô nhập Advisor Feedback** (`saveBriefDecision`) và tự động tải lại active brief + lịch sử quyết định trên `StudentDetailPage.tsx`;<br>(2) Sửa `AdvisorDashboardPage.tsx:51-65` (đang hardcode 5/7 modules & 3/4 presentations) để nạp động đủ **7 học phần (`AAA..GGG`)** và **4 kỳ (`2013B..2014J`)** từ `/predictions/stats`;<br>(3) Thêm badge trạng thái triage (chờ duyệt vs đã accept/reject) trên hàng đợi. | 4 | `BE-14` | `US-10` / `FR-07` |

---

## Sprint 2 — Kiểm thử Tự động (Vitest / `run.mjs`), Accessibility & Playwright E2E (8 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☐ | `FE-11` | **Mở rộng Kiểm thử Component & Contract (`tests/run.mjs` / Vitest)** | Kiểm tra đủ 4 `PredictionStatus`, trạng thái `fallback_review` / `unavailable`, lưu quyết định kèm `feedback`, vòng đời JWT token và xử lý lỗi `401`/`403`/`503`. | 4 | `FE-09`, `FE-10`, `FE-13` | `US-11` / `FR-08` |
| ☐ | `FE-12` | **Kiểm toán Accessibility (a11y) & Kịch bản Playwright E2E Human Oversight** | Rà soát tương phản, điều hướng bàn phím, `aria-label`, hộp thoại xác nhận quyết định (tránh over-trust), và chạy kịch bản Playwright E2E hoàn chỉnh từ Queue → Student Detail → Brief Edit/Decision + Feedback. | 4 | `FE-11` | `US-10` / `FR-07` |
