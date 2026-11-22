# Kế hoạch Công việc Chi tiết: SWE2 — Software Engineer 2 (Frontend Advisor Dashboard, Human Oversight UX & E2E Testing)

> **Vai trò:** Chủ sở hữu `FE-MLOPS` (M9 React 18 + TypeScript 5.7 + Vite 5.4 Advisor & Admin Dashboard).
> **Kho mã nguồn chính:** `ntk223/FE-MLOPS` (`src/`, `tests/`, `docs/API_CONTRACT.md`).
> **Hợp đồng bắt buộc tuân thủ:** [API_CONTRACT.md](../../../FE-MLOPS/docs/API_CONTRACT.md) và các nguyên lý **Intelligence Experience & Human Oversight** của giáo trình **CMU MLIP (Lec 1, Lec 2, Lec 5)**.
> **Quy tắc bất biến:** Frontend chỉ gọi Backend qua REST API; không bao giờ trình bày điểm rủi ro ML hay gợi ý của LLM như kết luận nhân quả chắc chắn; mọi hành động hỗ trợ sinh viên đều phải qua cố vấn xem xét và xác nhận.

**Định nghĩa Hoàn thành (DoD) cho mọi Task:** `npm run build` (`tsc --noEmit && vite build`) và `node tests/run.mjs` pass 100%, giao diện xử lý phòng thủ mọi dữ liệu lỗi/rỗng mà không crash, tuân thủ phân quyền route `advisor` vs `admin`.

Tổng cộng: **12 tasks (42 giờ)**. Đã hoàn thành trong Baseline: **8 tasks (`☑`, 26 giờ)**, Đang mở / Cần làm tiếp: **4 tasks (`◐`/`☐`, ~16 giờ)**.

---

## Giai đoạn Baseline — Đã hoàn thành trên nhánh `main` (`0f70e14`) (26 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `FE-01` | Xây dựng Typed API Client (`src/api/client.ts`) & Mock Client (`src/mocks/mock-client.ts`) với Timeout/AbortController | Chuẩn hóa lỗi về `ApiError { code, message }`, chuyển đổi `snake_case ↔ camelCase` phòng thủ, điều khiển qua `VITE_BACKEND_API_URL` và `VITE_USE_MOCK`. | 4 | — | `FR-04`, `FR-08` |
| ☑ | `FE-02` | Xây dựng Khung Ứng dụng (`AppShell`), Định tuyến Phân quyền (`advisor` vs `admin`) & Trang Tổng quan (`OverviewPage`) | Phân tách rõ menu Cố vấn (Tổng quan, Hàng đợi sinh viên) và Quản trị (Đánh giá tự động, Nhật ký hệ thống); chặn truy cập trái quyền. | 3 | `FE-01` | `FR-04`, `FR-09` |
| ☑ | `FE-03` | Xây dựng Hàng đợi Ưu tiên Cố vấn (`AdvisorDashboardPage`) kết nối API `/predictions` & `/predictions/stats` | Hỗ trợ lọc theo học phần (`code_module`), kỳ học (`code_presentation`), trạng thái (`status`), sắp xếp theo `risk_score` / `uncertainty`, phân trang thực tế với `total`. | 4 | `FE-01`, `BE-02` | `FR-04` |
| ☑ | `FE-04` | Xây dựng Trang Hồ sơ Chi tiết Sinh viên (`StudentDetailPage`) hiển thị SHAP Signals, Uncertainty & Disclaimer | Hiển thị rõ `riskScore`, `threshold`, thanh `uncertainty`, top 5 tín hiệu SHAP (`increases_risk` / `decreases_risk`) kèm nhãn cảnh báo phi nhân quả và trạng thái `insufficient_data` / `manual_review`. | 4 | `FE-03` | `FR-05` |
| ☑ | `FE-05` | Xây dựng Card Hành vi 4 Tuần Trước Ngày Cắt trên `StudentDetailPage` (`/predictions/.../activity`) | Biểu đồ cột lượt click theo 5 mốc tuần ("Trước khóa" + Tuần 1–4), timeline điểm số bài nộp (TMA/CMA) và chips phân loại hoạt động (`forum`, `quiz`, `resources`); tự ẩn khi 404 và báo lỗi nhẹ khi 503 mà không làm hỏng trang. | 3 | `FE-04`, `BE-03` | `FR-04`, `FR-05` |
| ☑ | `FE-06` | Xây dựng Luồng Tạo, Chỉnh sửa tại chỗ & Phê duyệt Advisor Brief (`/briefs/generate`, `PUT /briefs/{id}`, `POST /briefs/{id}/decision`) | Cố vấn có thể sửa `summary`, `reasons`, `supportSuggestions`, `limitations` (hiển thị dấu vết `editedAt`), bấm Chấp nhận / Từ chối; hiển thị nhãn riêng khi Brief ở trạng thái `fallback_review` hoặc `unavailable`. | 4 | `FE-04`, `BE-04` | `FR-06`, `FR-07`, `FR-08` |
| ☑ | `FE-07` | Xây dựng Ngăn Chat Trợ lý Cố vấn (`AdvisorChatDrawer`) & Tổng hợp Hội thoại thành Brief (`/briefs/chat/*`) | Hỗ trợ starter prompts, trích dẫn bằng chứng trên từng lượt trả lời, nút "Tổng hợp thành Brief chính thức" (`finalize-brief`) và bộ test `tests/test-chat.ts`. | 2 | `FE-06`, `BE-05` | `FR-06`, `FR-07` |
| ☑ | `FE-08` | Xây dựng Trang Đánh giá Tự động (`EvaluationsPage` — `/evaluations`) & Nhật ký Hệ thống (`AuditPage` — `/audit`) | Hiển thị Scorecard các cổng (`data`, `ml`, `llm`, `behavioral`) với badge trạng thái `PASS`/`WARN`/`FAIL`/`SKIPPED`, chi tiết `<details>` mở rộng và bảng tra cứu nhật ký kiểm toán có bộ lọc `action`/`entity`. | 2 | `FE-02`, `BE-06`, `BE-07` | `FR-09`, `NFR-ML1` |

---

## Sprint 1 — Tích hợp Xác thực JWT Thật & Hiển thị Cổng Hành vi / Telemetry (8 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ◐ | `FE-09` | **Tích hợp Đăng nhập JWT Thật (`POST /auth/login`) trong `LearnGuardApiClient` & `LoginPage`** | Cập nhật `client.ts`: gửi `POST /auth/login`, lưu JWT vào session storage, tự động đính kèm header `Authorization: Bearer <token>` vào mọi request, và tự động điều hướng về `/login` khi gặp `401 Unauthorized`. Hỗ trợ fallback mock login khi `VITE_USE_MOCK=true`. | 4 | `BE-08`, `BE-09` | `FR-09`, `NFR-SEC1` |
| ☐ | `FE-10` | **Hiển thị Scorecard `behavioral` (Gate 4) & Thẻ Telemetry Hiệu năng/Chi phí LLM trên `EvaluationsPage`** | Cập nhật `EvaluationsPage.tsx` để hiển thị đẹp mắt bảng điểm `eval_behavioral.json` (`MFT`, `Invariance`, `Directional`, `Abstention`) và thông số p50/p95 latency + chi phí LLM từ `/metrics` (hoặc `/evaluations`). | 4 | `MLO-02`, `BE-11` | `NFR-ML3`, `NFR-PERF1` |

---

## Sprint 2 — Kiểm thử Tự động Giao diện (Component & E2E) và Accessibility (8 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☐ | `FE-11` | **Mở rộng Bộ Kiểm thử Tự động Frontend (`tests/run.mjs`) cho Contracts, Error States & Abstention UI** | Viết thêm các bài test tự động kiểm tra: (1) Xử lý đủ 4 trạng thái `PredictionStatus` (`scored`, `manual_review`, `insufficient_data`, `no_prediction`), (2) Hiển thị đúng cảnh báo khi Brief ở trạng thái `fallback_review` / `unavailable`, (3) Luồng JWT token & xử lý lỗi `401`/`403`/`503`. | 4 | `FE-09`, `FE-10` | `FR-08`, `NFR-ML3` |
| ☐ | `FE-12` | **Kiểm tra Accessibility (a11y), UX Human Oversight & Chuẩn hóa Kịch bản Demo E2E** | Rà soát tương phản màu, điều hướng bàn phím (`aria-label`, focus states), hộp thoại xác nhận trước khi cố vấn bấm "Chấp nhận/Từ chối Brief" (tránh over-trust theo Lec 1/2), và viết kịch bản walkthrough demo trên trình duyệt. | 4 | `FE-11` | `FR-05`, `FR-07` |
