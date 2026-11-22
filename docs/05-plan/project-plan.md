# Kế hoạch Tổng thể Dự án & Phân công Công việc cho 4 Thành viên (Master Project Plan)

> **Phiên bản:** 2.0 (2026-11-23)
> **Phương pháp lập kế hoạch:** Học tập mô hình quản trị dự án của `smart-hospital-platform/docs/05-plan/project-plan.md` (phân rã theo vai trò chuyên trách, cổng phê duyệt `G1`–`G4`, mỗi task `<= 4–6 giờ`, có điều kiện `Done when` kiểm chứng được bằng lệnh và danh sách ưu tiên cắt giảm phạm vi MoSCoW).
> **Bối cảnh Baseline hiện tại (Snapshot 2026-11-23):**
> - `Data-ML-MLOPS` (`72c96cd`): Đã hoàn thành M1–M5, Linear SHAP, Benchmark, Validation Release Top-20%, và 3 cổng `learnguard evaluate {data,ml,llm}` (`163 passed`).
> - `BE-MLOPS` (`a2bae92`): Đã hoàn thành `/health`, `/predictions*` (kèm `/stats`, `/activity`), `/briefs*` (generate, edit, decision), `/briefs/chat/*` (interactive chatbot), `/evaluations*`, `/audit-logs`. **Điểm còn thiếu lớn nhất:** M6 Authentication & RBAC (`POST /auth/login`, JWT middleware, thay `system@learnguard.local` bằng user thực tế) và endpoint `/metrics` + rate-limit tầng app.
> - `FE-MLOPS` (`0f70e14`): Đã hoàn thành giao diện Dashboard, Student Detail (kèm 4-week Activity), Brief Review/Edit, Advisor Chat Drawer, Evaluations Page, Audit Page. **Điểm còn thiếu:** Tích hợp đăng nhập JWT thật với Backend M6, bộ kiểm thử UI tự động (Vitest / Playwright E2E) và kiểm tra Accessibility (a11y).
> - `learnguard-platform` (Repo này): Đã hoàn thành bộ quy chuẩn CMU MLIP, kiến trúc DigitalOcean VM (Terraform + Docker Compose 2 mạng cô lập + Nginx + DB least-privilege + Backup/Rollback), 4 workflows GitHub Actions CI/CD, và động cơ Drift Triage + Data Simulator + Behavioral Gate + Continual Retraining.

---

## 1. Tài liệu Đầu vào theo Từng Thành viên

| Nội dung cần nắm | Đường dẫn Tài liệu |
| :--- | :--- |
| Đề bài gốc & Ràng buộc nghiệp vụ Chủ đề 4 | [requirements.md](../requirements/requirements.md) · [PROJECT_CONTEXT.md](../../PROJECT_CONTEXT.md) |
| Quy chuẩn SE, DevOps & MLOps (CMU MLIP Lec 1–6) | [software-engineering-and-mlops-conventions.md](../conventions/software-engineering-and-mlops-conventions.md) |
| Quy trình nhánh, PR, DoR/DoD & Phân quyền repo | [00-delivery-process.md](../00-delivery-process.md) · [00-workflow.md](../00-workflow.md) |
| Ma trận Truy vết hai chiều (`FR`/`NFR` ↔ `ADR` ↔ `Task` ↔ `Test`) | [02-requirements/traceability.md](../02-requirements/traceability.md) |
| Kiến trúc Đích trên DigitalOcean VM & Drift/Retraining Spec | [digitalocean-target-architecture.md](../architecture/digitalocean-target-architecture.md) · [drift-and-retraining-specification.md](../architecture/drift-and-retraining-specification.md) |
| Hợp đồng Giao tiếp (DB, API, Prediction Batch) | [DB_CONTRACT.md](../../BE-MLOPS/docs/DB_CONTRACT.md) · [API_CONTRACT.md](../../FE-MLOPS/docs/API_CONTRACT.md) · [M5_PREDICTION_BATCH.md](../../Data-ML-MLOPS/docs/M5_PREDICTION_BATCH.md) |
| **Kế hoạch chi tiết từng thành viên (Checklist)** | **[MLOPS (Bạn)](by-person/MLOPS.md)** · **[SWE1 (Backend)](by-person/SWE1.md)** · **[SWE2 (Frontend)](by-person/SWE2.md)** · **[AIE (AI/ML)](by-person/AIE.md)** |
| Toàn bộ Backlog (Import GitHub Projects) & Kiểm toán DoD | [backlog.csv](backlog.csv) · [dod-audit.md](dod-audit.md) |

---

## 2. Phân vai & Trách nhiệm Cốt lõi của 4 Thành viên

| Mã Vai trò | Thành viên | Kho Mã nguồn Sở hữu Chính | Phạm vi Trách nhiệm (Ownership Scope) |
| :--- | :--- | :--- | :--- |
| **`MLOPS`** | **Bạn (MLOps + DevOps + Solution Architect / PM)** | `learnguard-platform` (toàn quyền) + Quản trị nhánh `main` của cả 4 repo | **Toàn bộ Hạ tầng, CI/CD, MLOps Orchestration & Quản trị Chất lượng:**<br>• Quy chuẩn kỹ thuật CMU MLIP, ADRs, Contracts & Guardrails.<br>• Hạ tầng DigitalOcean (Terraform VPC/Droplet/Firewall/Volume, `bootstrap-vm.sh`).<br>• Docker Compose Prod Stack (2 mạng cô lập, Nginx reverse proxy, PostgreSQL least-privilege `lg_api` & `lg_ml_writer`, `backup-db.sh` / `restore-db.sh`).<br>• 4 luồng GitHub Actions CI/CD (`ci-platform`, `ci-build-and-scan`, `cd-digitalocean-prod`, `mlops-drift-retrain`) + Smoke Test + Auto-Rollback.<br>• Động cơ Phát hiện Drift, Mô phỏng 5 kịch bản dữ liệu mới, Behavioral Testing Gate (`MFT`/`INV`/`DIR`) & Continual Retraining Champion-vs-Challenger.<br>• Observability (Prometheus/cAdvisor/Node-Exporter), Chaos/Fault-Injection Drills & Phê duyệt Release. |
| **`SWE1`** | **Software Engineer 1 (Backend Core, Security & Persistence)** | `BE-MLOPS` (`api/`, `db/`, `migrations/`, `observability.py`, `settings.py`) | **Toàn bộ Backend API, Bảo mật M6, Persistence M7 & Telemetry:**<br>• Hoàn thiện **M6 Authentication & RBAC** (`POST /auth/login`, `GET /auth/me`, JWT middleware, phân quyền `advisor` vs `admin`, gắn `user_id` thật vào `briefs`, `decisions`, `chat_sessions`, `audit_logs`).<br>• Quản lý schema & Alembic migrations cho các bảng backend sở hữu; đảm bảo chỉ `SELECT` trên `ml_predictions`.<br>• Tối ưu hóa các API `/predictions*` (kèm `/stats`, `/activity`), `/evaluations*`, `/audit-logs`.<br>• Xuất metrics vận hành (`/metrics` cho Prometheus: request duration p50/p95, LLM token/cost/failover counters) & structured JSON logging không chứa PII. |
| **`SWE2`** | **Software Engineer 2 (Frontend Dashboard, Human Oversight UX & E2E QA)** | `FE-MLOPS` (`src/`, `tests/`, `docs/API_CONTRACT.md`) | **Toàn bộ Giao diện Cố vấn/Quản trị (M9) & Trải nghiệm Con người - AI:**<br>• Chuyển đổi `LoginPage` và `LearnGuardApiClient` từ mock auth sang **Real JWT Auth** kết nối với `SWE1` (`POST /auth/login`, lưu trữ token an toàn, tự động xử lý `401 Unauthorized`, route guard theo role).<br>• Hoàn thiện **Hàng đợi Ưu tiên (Priority Queue)** & **Hồ sơ Sinh viên (`StudentDetailPage`)**: hiển thị rõ thanh độ không chắc chắn (`uncertainty`), cảnh báo phi nhân quả (SHAP disclaimer), biểu đồ hành vi 4 tuần (`/activity`) và 4 trạng thái dự báo (`scored`, `manual_review`, `insufficient_data`, `no_prediction`).<br>• Hoàn thiện luồng **100% Human Oversight**: xem/sửa Brief (`PUT /briefs/{id}`), phê duyệt/từ chối kèm lý do (`POST /briefs/{id}/decision`), Advisor Chat Drawer (`/briefs/chat/*`), trang Đánh giá tự động (`/evaluations`) và Nhật ký hệ thống (`/audit`).<br>• Xây dựng bộ kiểm thử Frontend tự động (Vitest unit/component tests + Playwright E2E) và Accessibility (a11y). |
| **`AIE`** | **AI / ML Engineer (Data Pipeline M1–M3, ML M4–M5, LLM M8 & Eval Gates)** | `Data-ML-MLOPS` (`src/learnguard/`) & `BE-MLOPS/src/learnguard_backend/services/{llm,briefs,chat,chat_context}.py` | **Toàn bộ Khoa học Dữ liệu, Mô hình ML, Dịch vụ LLM & Đánh giá Chất lượng:**<br>• Duy trì & mở rộng pipeline dữ liệu M1–M3 (`cutoff_day=27`, `LeakageAuditor` 16 probes, `DataQualityGate`).<br>• Huấn luyện & đánh giá mô hình ML M4–M5 (Logistic Regression v2 + Linear SHAP, benchmark với RandomForest/HistGB/ExtraTrees, khóa ngưỡng Top-20% Alert Budget, đánh giá Calibration ECE/Brier & Fairness Slices trên nhiều chiều nhân khẩu học/học phần).<br>• Tối ưu hóa dịch vụ **M8 LLM Advisor Brief & Chatbot**: thiết kế prompt bám sát `Common Advisor Guidelines`, bộ kiểm tra trích dẫn cứng (`evidence_features`), chặn suy diễn nhân quả/tâm lý, điều phối failover `OpenRouter/Gemini -> Ollama (qwen2.5:3b) -> Rule-based fallback_review`.<br>• Hiệu chỉnh **Gate 3 (`learnguard evaluate llm`)**: xây dựng bộ golden rubric dataset và đối chiếu độ tương đồng giữa `LLM-as-a-Judge` với đánh giá của con người (Lec 5). |

---

## 3. Lộ trình Thực hiện & Cổng Kiểm soát (Roadmap & Gates)

```text
Giai đoạn Baseline (Đã hoàn thành):
  [G1/G2/G3] Chốt đề bài Chủ đề 4, DB Contract, API Contract, M1–M5 Batch Pipeline, FastAPI Core + Briefs/Chat/Eval/Audit, React SPA.

Sprint 1 (Tuần hiện tại — Platform, CI/CD, Drift/Retrain & Security M6):
  • MLOPS : Hoàn tất Quy chuẩn CMU MLIP, Hạ tầng DigitalOcean, Docker Compose Prod, 4 GitHub Actions CI/CD, Drift Monitor + Behavioral Gate + Retraining Pipeline (Đạt Gate G4).
  • SWE1  : Triển khai M6 JWT Auth & RBAC (BE-08..BE-10), nối user_id thật vào Briefs/Decisions/Chat/Audit, thêm rate-limit & /metrics (BE-11).
  • SWE2  : Tích hợp Real JWT Auth trên Frontend (FE-09), hoàn thiện banner cảnh báo Uncertainty/Abstention & trạng thái Fallback Brief (FE-10).
  • AIE   : Mở rộng Fairness Slices đa chiều (code_module, age_band, disability, imd_band) trong ML Gate (ML-11) & bộ Golden Set 30 hồ sơ cho LLM Brief Eval (AI-06).

Sprint 2 (Tuần kế tiếp — Tích hợp Cloud E2E, Calibration LLM Judge & Kiểm thử Hệ thống Lec 6):
  • MLOPS : Triển khai thực tế lên DigitalOcean Droplet VM, bật systemd timer cho Drift/Retraining, diễn tập Chaos/Safeguard & Rollback (OPS-07, CICD-06, MLO-07).
  • SWE1  : Kiểm thử tích hợp PostgreSQL với 2 role (lg_api vs lg_ml_writer), tối ưu cache cho /activity và /evaluations (BE-12, BE-13).
  • SWE2  : Viết bộ kiểm thử tự động Vitest & Playwright E2E cho luồng Advisor Review Queue -> Brief Decision -> Audit Log (FE-11, FE-12).
  • AIE   : Thực nghiệm hiệu chỉnh LLM-as-a-Judge với Human Rubric (AI-07) & phân tích False Negatives / Alert Workload Top-20% cho báo cáo cuối kỳ (ML-12, AI-08).

Sprint 3 (Tuần Tổng kết & Bảo vệ Đồ án — Production Engineering & Defense):
  • Cả nhóm: Đo đạc Product/User Value (thời gian cố vấn xử lý hồ sơ có/không có AI), tổng hợp báo cáo thực nghiệm theo 11 tiêu chí mục 4 Chủ đề 4, diễn tập Demo trực tiếp trên DigitalOcean Cloud.
```

---

## 4. Phân bổ Khối lượng Công việc (Workload Summary)

| Thành viên | Vai trò | Tổng số Task | Đã xong (`☑`) | Đang làm / Một phần (`◐`) | Cần làm tiếp (`☐`) | Tổng Giờ Ước tính (Remaining) | Trọng tâm Sắp tới |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`MLOPS`** | MLOps + DevOps + Architect (Bạn) | **21** | 19 | 0 | **2** | ~8h | Provision DO Droplet & chạy live stack (`OPS-06`), diễn tập Chaos/Rollback (`OPS-07`), review PR của 3 thành viên. |
| **`SWE1`** | Backend Engineer (`BE-MLOPS`) | **13** | 7 | 1 | **5** | ~16h | M6 JWT Login & RBAC (`BE-08`, `BE-09`), thay `system` actor bằng user thật (`BE-10`), Prometheus `/metrics` & latency logging (`BE-11`). |
| **`SWE2`** | Frontend Engineer (`FE-MLOPS`) | **12** | 8 | 1 | **3** | ~14h | Nối Real JWT Auth (`FE-09`), Vitest component tests (`FE-11`), Playwright E2E luồng cố vấn duyệt Brief (`FE-12`). |
| **`AIE`** | AI / ML Engineer (`Data-ML-MLOPS` + LLM) | **14** | 10 | 1 | **3** | ~14h | Đa chiều Fairness Slices & Calibration ECE (`ML-11`), Human-calibrated LLM Rubric Experiment (`AI-07`), Báo cáo False Negative & Workload (`ML-12`). |
| **Tổng cộng** | **4 Thành viên** | **60** | **43** | **3** | **14** | **~54h** | Cân bằng ~10–16 giờ/người để hoàn tất 100% tiêu chí xuất sắc trước bảo vệ. |

---

## 5. Thứ tự Ưu tiên & Cắt giảm Phạm vi khi Thiếu Thời gian (MoSCoW Cut Order)

1. **Không bao giờ cắt (MUST — Điều kiện bắt buộc của Chủ đề 4 & CMU MLIP):**
   - Pipeline dữ liệu M1–M3 chống rò rỉ thời gian (`cutoff_day=27`, 100% probe detection).
   - Mô hình Logistic Baseline + Linear SHAP + ít nhất 1 mô hình ML so sánh + chính sách ngưỡng Top-20% Alert Budget.
   - Dịch vụ LLM tạo Advisor Brief có trích dẫn dữ liệu nguồn + Ollama/Rule-based Fallback khi LLM lỗi.
   - Luồng 100% Human Oversight (cố vấn xem, sửa, chấp nhận/từ chối Brief + ghi `audit_logs`).
   - Kiểm soát truy cập cơ bản (M6 JWT Auth & RBAC cho `advisor` và `admin`).
   - Pipeline CI/CD triển khai lên DigitalOcean VM + Pipeline phát hiện Drift & Continual Retraining (kèm chế độ mô phỏng 5 kịch bản).
2. **Nên hoàn thành để đạt điểm tối đa (SHOULD):**
   - Mở rộng Fairness Slices ra toàn bộ các chiều (`code_module`, `age_band`, `disability`, `imd_band`) kèm khoảng tin cậy cỡ mẫu.
   - Thử nghiệm đối chiếu độ tương đồng giữa `LLM-as-a-Judge` (`learnguard evaluate llm`) với điểm chấm thủ công của 2 thành viên trong nhóm trên 30 Brief mẫu.
   - Bộ kiểm thử E2E tự động cho Frontend và Prometheus `/metrics` endpoint.
3. **Có thể giản lược nếu sát hạn (COULD):**
   - Chạy Ollama `qwen2.5:3b` trực tiếp24/7 trên Droplet RAM nhỏ (có thể tắt profile `llm-fallback` trên VM 4GB để tiết kiệm RAM và chỉ dùng deterministic `fallback_review` khi OpenRouter lỗi).
   - Giao diện quản trị trigger retraining trực tiếp bằng nút bấm trên Web (hiện đã có trigger an toàn qua GitHub Actions `mlops-drift-retrain.yml` và systemd timer trên VM).

---

## 6. Quản trị Rủi ro Dự án (Project Risk Register)

| Rủi ro | Tác động | Biện pháp Phòng ngừa & Giảm thiểu | Chủ sở hữu |
| :--- | :--- | :--- | :--- |
| **R-01: Chậm trễ tích hợp M6 Auth giữa `SWE1` và `SWE2`** | Trang web vẫn dùng mock login khi demo hoặc lỗi 401 hàng loạt. | Giữ cờ `VITE_USE_MOCK_AUTH` độc lập với `VITE_USE_MOCK`: `SWE2` có thể bật real auth ngay khi `SWE1` merge `BE-08`, hoặc fallback về mock session nếu cần demo khẩn cấp. | **SWE1** + **SWE2** |
| **R-02: Đứt kết nối hoặc hết hạn quota OpenRouter API khi bảo vệ đồ án** | Không tạo được Advisor Brief mới trực tiếp lúc demo. | Đã có 2 tầng dự phòng: (1) Cấu hình sẵn `LLM_FALLBACK_MODEL` (Ollama hoặc Gemini key dự phòng), (2) `BriefService.make_fallback` luôn trả HTTP 200 với mẫu `fallback_review` dựa trên SHAP signals thật. | **AIE** + **MLOPS** |
| **R-03: Tràn RAM trên DigitalOcean Droplet khi chạy M1 (`studentVle.csv` ~454MB) cùng lúc với Postgres & API** | Container `ml-worker` bị OOM-killed (exit 137). | `bootstrap-vm.sh` & `cloud-init.yaml` tự động cấu hình swap / Droplet 4–8GB RAM; `ml-worker` chỉ chạy dạng batch ngắn hạn và hỗ trợ chạy mô phỏng trên tập mẫu chuẩn. | **MLOPS** |
| **R-04: Lệch schema giữa `Data-ML-MLOPS` và `BE-MLOPS`** | Hiện tượng "Green components, red system" (Lec 6). | Bắt buộc chạy `tests/test_system_contracts.py` trong `ci-platform.yml` trên mọi PR để kiểm tra từng cột của `ml_predictions` và schema `eval-report.v1`. | **MLOPS** |
