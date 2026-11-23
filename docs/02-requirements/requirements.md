# Đặc tả Yêu cầu Hệ thống LearnGuard (Functional & Non-Functional Requirements)

> **Phiên bản:** 3.0 (2026-11-23)
> **Nguồn chuẩn:** Đề bài **Chủ đề 4 — Student Success Early-Warning Assistant** · Khung **CMU MLIP `ASM ∧ SPEC => REQ` & Defensible Success Portfolio (Lec 1–6)** · Đối chiếu hiện trạng code tại [app-facts.md](app-facts.md).

---

## 1. Khung `ASM ∧ SPEC => REQ` & Danh mục Thành công (CMU MLIP Lec 2)

Ba yêu cầu thế giới thực cốt lõi (`REQ-01..03`), các giả định môi trường (`ASM-01..03`), đặc tả giao diện máy (`SPEC-01..04`) và **Defensible Success Portfolio** (Primary Outcome, Guardrails, Balancing Measures, Leading Indicators, Model Diagnostics) được chuẩn hóa tại [00-conventions.md](../00-conventions.md) §2.

---

## 2. Yêu cầu Chức năng (`FR-01` → `FR-09`) & Tiêu chí Chấp nhận (Acceptance Criteria)

| Mã FR | Mô tả Yêu cầu (Đề bài Chủ đề 4) | Tiêu chí Chấp nhận Kiểm chứng được (Acceptance Criteria) |
| :--- | :--- | :--- |
| **FR-01** | **Tiếp nhận OULAD & Feature Snapshot tại tuần 4** | • Đọc đủ 7 CSV (`courses`, `studentInfo`, `studentVle`, `studentAssessment`, `assessments`, `vle`, `studentRegistration`), cách ly dòng lỗi vào `quarantine/`.<br>• Loại SV rút học `<= 27` (5,040) và đăng ký `> 27` (18) → cohort `27,535` dòng (`15` input cols → `38` encoded cols), gắn cờ `insufficient_data` và xuất `snapshot.ledger.json`. |
| **FR-02** | **Chống rò rỉ dữ liệu tương lai (`date <= 27`)** | • Loại 11 Exams `date = NULL` và mọi sự kiện `date > 27`.<br>• `M3 LeakageAuditor` kiểm tra 3 lớp (ledger hash, row recomputation, 16 temporal injection probes) đạt **100% detection (`0 violations`)**.<br>• Tập `holdout` (`2014J`, 9,214 rows) chỉ dùng 1 lần; mọi tuning/selection mới bị khóa chỉ chạy trên `validation` (`2014B`, 6,510 rows). |
| **FR-03** | **Huấn luyện ML tự chủ & Ngưỡng Top-20%** | • Logistic Regression v2 (`seed=42`) là production incumbent; benchmark với ít nhất 3 mô hình khác (Dummy, RandomForest, ExtraTrees, HistGradientBoosting).<br>• Khóa ngưỡng theo ngân sách tải cố vấn **Top-20%** (`0.810348`), sai lệch tỷ lệ cảnh báo thực tế `<= 1%` trên validation. |
| **FR-04** | **Dashboard Hàng đợi Ưu tiên & Biểu đồ Hành vi 4 tuần** | • Hiển thị hàng đợi ưu tiên từ `/predictions`, hỗ trợ lọc động đầy đủ **7 học phần (`AAA..GGG`)** và **4 học kỳ (`2013B, 2013J, 2014B, 2014J`)** từ `/predictions/stats`, trạng thái dự báo & trạng thái duyệt Brief (`FE-13`).<br>• Hiển thị biểu đồ click 5 mốc tuần & timeline bài nộp từ `/predictions/{m}/{p}/{s}/activity` với graceful degradation khi 404/503. |
| **FR-05** | **Giải thích Phi nhân quả (SHAP) & Độ Bất định** | • Hiển thị top 5 tín hiệu `Linear SHAP` (`increases_risk` / `decreases_risk`, sai số additivity `<= 1e-8`) và thanh `uncertainty`.<br>• Luôn gắn cảnh báo phi nhân quả (association ≠ causation); `uncertainty >= 0.80` tự động định tuyến `manual_review`. |
| **FR-06** | **Advisor Brief & Chatbot Grounded vào Guidelines** | • Cả one-shot `AdvisorBriefService.generate()` (`BE-14`) lẫn Interactive Chat Copilot (`services/chat.py`) đều nạp `advisor_guidelines.md`, chỉ dùng dữ liệu tối thiểu phi PII.<br>• 100% reason có `evidence_features` khớp dữ liệu thật; bộ lọc deterministic chặn phát ngôn nhân quả/tâm lý/PII trước khi trả kết quả. |
| **FR-07** | **Quy trình Human Oversight 100%** | • Cố vấn có thể xem, sửa tại chỗ (`PUT /briefs/{id}` giữ vết `edited_at`), chấp nhận hoặc từ chối (`POST /briefs/{id}/decision`) **kèm ô nhập `feedback`** (`BE-14`, `FE-13`).<br>• Tải lại active brief + lịch sử decision qua reload (`GET /predictions/{m}/{p}/{s}/brief`); 0% luồng gửi thẳng tới sinh viên. |
| **FR-08** | **Độ tin cậy & Trạng thái Lỗi Tường minh** | • Xử lý đủ 4 trạng thái `ml_predictions`: `scored`, `manual_review`, `insufficient_data` (`predicted_label = NULL`), `no_prediction`.<br>• LLM lỗi/timeout → failover sang `Ollama (qwen2.5:3b)` → `fallback_review` (HTTP 200 kèm badge cảnh báo).<br>• DB outage → `/health` báo `database: unreachable`, API trả `503` không lộ stacktrace/DSN (`BE-13`). |
| **FR-09** | **Truy vết, Evaluation Scorecards & Kiểm soát Truy cập** | • `audit_logs` append-only ghi nhận thao tác gắn `user_id` & `email` thật từ JWT (xóa `system@learnguard.local` ở `BE-10`).<br>• Trang `/evaluations` hiển thị cả 4 cổng (`data`, `ml`, `llm`, `behavioral`) + Drift + Active Release + LLM telemetry (`FE-10`).<br>• JWT Auth (`POST /auth/login`, `GET /auth/me`) và RBAC (`advisor` vs `admin` — `BE-08`, `BE-09`, `FE-09`). |

---

## 3. Yêu cầu Phi chức năng Định lượng (`NFR`)

| Mã NFR | Nhóm Chất lượng | Chỉ tiêu Định lượng & Quy chuẩn Bắt buộc |
| :--- | :--- | :--- |
| **NFR-ML1** | **Chất lượng & Calibration Mô hình** | `ROC-AUC >= 0.70` (warn `< 0.75`), theo dõi `PR-AUC`, `F1`, `Brier Score`, `ECE` (`ML-11`); so sánh Logistic v2 với `HistGradientBoostingClassifier` + TreeSHAP/permutation trên `validation` `2014B` (`ML-12`). |
| **NFR-ML2** | **Ngân sách Tải Cố vấn & Trade-off** | `Precision@Top20% >= 0.50` (fail `< 0.35`); phân tích đường cong đánh đổi `Precision@K` / `Recall@K` / `FPR` tại `K ∈ {10%, 20%, 30%}` và đặc trưng False Negative tuần 4 (`ML-12`). |
| **NFR-ML3** | **Kiểm thử Hành vi (Behavioral Gate — Lec 5)** | Vượt qua 6 kiểm thử trong `behavioral_gate.py`: `MFT` (gap `>= 0.25`), `Row Permutation Invariance` (`<= 1e-12`), `Pseudonymous Key Invariance`, `Clicks Directional`, `Score Directional`, `Abstention Routing`. |
| **NFR-ML4** | **Công bằng Đa chiều (6-Slice Fairness)** | Mở rộng `ml_gate.py` đánh giá `FNR gap` & `Precision@20%` trên **6 chiều** (`gender`, `code_module`, `age_band`, `disability`, `imd_band`, `highest_education`) kèm guard cỡ mẫu nhỏ; cảnh báo khi `max_fnr_gap > 0.10` (`ML-11`). |
| **NFR-MLO1** | **Phát hiện Drift & Triage (Lec 4 Q19–22)** | Đo `PSI` (`<= 0.10` pass, `> 0.20` fail), `Two-Sample KS` (`D_KS > 0.15`), `Missingness`, `Volume Ratio [0.10, 10.0]`, `Semantic Scale Guard (10x)`, `Slice PSI`, và `ASM-03 Delayed Label Guard` (chặn promote bừa khi thiếu nhãn cuối kỳ). |
| **NFR-MLO2** | **Continual Retraining & Rollback** | Tự động điều phối `M1→M5` qua `retrain_pipeline.py`; chỉ promote Challenger khi pass cả `Data + ML + Behavioral Gates` và không tụt `ROC-AUC > 0.01` (fail-closed); hỗ trợ `--mode rollback`. |
| **NFR-LLM1** | **Chất lượng, An toàn & Red-Team LLM** | Schema error `< 5%`, Citation validity `= 100%`, `LLM-as-a-Judge >= 3.5 / 5.0`; hiệu chỉnh trên 30 golden briefs chấm tay 2 người + điểm bám `advisor_guidelines.md` + red-team prompt-injection trên Chat Copilot (`AI-06`). |
| **NFR-PERF1** | **Hiệu năng & Chi phí Vận hành** | `observability.py` xuất JSON structured logs (PII-scrubbed + `request_id`) & Prometheus `/metrics` (`BE-11`); p95 tạo Brief `<= 15s`; `/predictions/.../activity` cached `< 300ms` (`BE-12`); ghi `llm_calls` (`tokens`, `cost_usd`, `latency_ms`). |
| **NFR-SEC1** | **Bảo mật, Quyền riêng tư & Cô lập Mạng** | `0%` `id_student` thô & thuộc tính nhạy cảm trong DB backend/logs/LLM; tách 2 role DB `lg_ml_writer` & `lg_api` (read-only `ml_predictions`); cô lập `lg_backend_net` (`internal: true`); container non-root `UID 10001`; Nginx rate-limit `20r/s` + 5 security headers. |
| **NFR-OPS1** | **Cloud-Portable Dual-Option Deployment & CI/CD** | **Deploy-Where-Available (Option A Azure PaaS hoặc Option B DigitalOcean VM — không chạy đồng thời cả hai):**<br>• Duy trì IaC & CD parity cho cả Azure (`infra/env/dev`, tuân thủ [AZURE_CONSTRAINTS.md](../memory/AZURE_CONSTRAINTS.md) cấm `azurerm_role_assignment`, `OPS-08`) và DigitalOcean (`infra/digitalocean/`, `OPS-06`).<br>• 4 GitHub Actions workflows GREEN; image GHCR ghim `@sha256` + Trivy `exit-code: 1`; backup DB trước deploy + auto-rollback `< 60s`. |
