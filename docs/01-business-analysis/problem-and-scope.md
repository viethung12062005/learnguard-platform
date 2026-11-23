# Phân tích Bài toán, Dữ liệu OULAD và Phạm vi Hệ thống (Problem Framing & Scope)

> **Phiên bản:** 1.0 (2026-11-23)
> **Nền tảng tham chiếu:** Đề bài **Chủ đề 4 — Student Success Early-Warning Assistant** · Khung thiết kế **CMU MLIP (Lectures 1–2: Four Boundaries & Problem Framing)** · Quy chuẩn [00-conventions.md](../00-conventions.md).

---

## 1. Bối cảnh Bài toán & Tuyên bố Giá trị Sản phẩm (Problem Framing)

### 1.1. Thách thức Nghiệp vụ
Trong các khóa học đại học quy mô lớn trên hệ thống LMS (Open University Learning Analytics Dataset — **OULAD**), tỷ lệ sinh viên không hoàn thành khóa học rất cao (**52.8%** tổng số lượt đăng ký rơi vào `Fail` hoặc `Withdrawn`). Tuy nhiên, đội ngũ cố vấn học tập (**Academic Advisors**) gặp 3 rào cản lớn khi thực hiện hỗ trợ sớm:
1. **Quá tải dữ liệu thô:** Mỗi khóa học phát sinh hàng triệu dòng tương tác LMS (`studentVle.csv` có >10.6 triệu dòng), cố vấn không thể đọc thủ công từng sinh viên.
2. **Đánh đổi thời điểm can thiệp:** Can thiệp quá muộn (sau kỳ thi giữa kỳ/cuối kỳ) làm mất cơ hội hỗ trợ; can thiệp quá sớm (tuần 1) thiếu tín hiệu hành vi ổn định. Mốc **cuối tuần 4 (`cutoff_day = 27`)** là điểm cân bằng: đủ dữ liệu click LMS và bài nộp đầu kỳ, đồng thời vẫn còn đủ thời gian học kỳ để cố vấn hỗ trợ kịp thời.
3. **Ngân sách công sức có hạn (Alert Budget):** Cố vấn không thể liên hệ 100% sinh viên. Một hệ thống chỉ có giá trị nếu xếp hạng ưu tiên gọn trong ngân sách tải công việc (**Top-20% sinh viên đang theo học tại tuần 4**, `target_alert_fraction = 0.20`), đi kèm giải thích dựa trên dữ liệu quan sát được (phi nhân quả) và bản tóm tắt **Advisor Brief** ngắn gọn dưới quyền quyết định **100% của con người**.

### 1.2. Tuyên bố Giá trị (Product Claim)
> **LearnGuard** hỗ trợ cố vấn học tập phát hiện sớm và ưu tiên xem xét nhóm sinh viên có nguy cơ `Fail`/`Withdrawn` ngay sau **tuần 4 (`cutoff_day = 27`)** trong giới hạn **Top-20% ngân sách cảnh báo**, bằng cách kết hợp mô hình ML tự huấn luyện giải thích được (`Logistic Regression v2` + `Linear SHAP`), cơ chế trì hoãn khi bất định/thiếu dữ liệu (`manual_review` / `insufficient_data`), và dịch vụ LLM tạo **Advisor Brief** + **Chatbot hỏi đáp** bám sát `advisor_guidelines.md` — bảo đảm **100% quyết định cuối cùng thuộc về cố vấn**, không tự động gửi cảnh báo hay phán xét sinh viên.

---

## 2. Chân dung Dữ liệu OULAD & Phân tách Thời gian (Verified Data Facts)

Số liệu dưới đây được kiểm chứng trực tiếp từ gói dữ liệu nguồn `Data-ML-MLOPS/data/archive.zip` (**43 MB** nén / **464.4 MB** giải nén) và pipeline `M1–M3`:

### 2.1. Thống kê 7 Bảng CSV Nguồn
| Bảng CSV | Số dòng (Rows) | Dung lượng / Ghi chú Kiểm chứng |
| :--- | :---: | :--- |
| `courses.csv` | **22** | **7 học phần** (`AAA`: 748, `BBB`: 7,909, `CCC`: 4,434, `DDD`: 6,272, `EEE`: 2,934, `FFF`: 7,762, `GGG`: 2,534 SV) × **4 học kỳ** (`2013B`, `2013J`, `2014B`, `2014J`). |
| `studentInfo.csv` | **32,593** | Nhãn gốc (`final_result`): `Pass`: **12,361** (37.9%) · `Distinction`: **3,024** (9.3%) · `Fail`: **7,052** (21.6%) · `Withdrawn`: **10,156** (31.2%). |
| `studentVle.csv` | **10,655,280** | ~453.8 MB — nhật ký tương tác click hàng ngày theo tài nguyên VLE. |
| `studentAssessment.csv` | **173,912** | Lịch sử nộp bài & điểm các bài đánh giá (TMA/CMA/Exam). |
| `assessments.csv` | **206** | Siêu dữ liệu bài kiểm tra; có **11 bài Exam có `date = NULL`** → bị loại trừ khi tính feature point-in-time. |
| `vle.csv` | **6,364** | Danh mục loại tài nguyên học tập trên LMS (`oucontent`, `forumng`, `quiz`, `resource`, v.v.). |
| `studentRegistration.csv` | **32,593** | Ngày đăng ký (`date_registration`) và ngày rút học (`date_unregistration`). |

### 2.2. Cohort tại `cutoff_day = 27` & Phân tách Thời gian (Temporal Splits)
Để đảm bảo **Point-in-Time Correctness (CMU MLIP Lec 4)** và loại trừ hoàn toàn rò rỉ dữ liệu tương lai (`date > 27`):
- **Loại trừ hợp lệ tại thời điểm dự báo (tuần 4):**
  - `5,040` lượt đã rút học trước hoặc tại ngày 27 (`date_unregistration <= 27`).
  - `18` lượt đăng ký muộn sau ngày 27 (`date_registration > 27`).
  - **Cohort đang theo học còn lại:** **27,535** lượt `(code_module, code_presentation, id_student)`.
- **3 Tập dữ liệu theo trình tự thời gian (Temporal Splits):**

| Split | Học kỳ (`code_presentation`) | Số dòng (Rows) | Tỷ lệ At-Risk (`Fail`/`Withdrawn`) | Quy tắc Sử dụng Bắt buộc |
| :--- | :--- | :---: | :---: | :--- |
| **`train`** | `2013B` + `2013J` | **11,811** | **44.4%** | Duy nhất dùng để fit preprocessor và huấn luyện tham số mô hình. |
| **`validation`** | `2014B` | **6,510** | **48.4%** | Dùng để chọn mô hình, khóa ngưỡng Top-20% (`0.810348`), đánh giá Fairness/Calibration/Challenger. |
| **`holdout`** | `2014J` | **9,214** | **40.8%** | **SINGLE-USE CONSUMED** trong `benchmark-20261105-shap` (`holdout_access_policy = forbidden_prior_consumed`). **CẤM tái sử dụng** cho tuning hoặc model selection! Mọi thực nghiệm challenger/tuning mới chỉ dùng `validation` (`2014B`) hoặc dữ liệu mô phỏng từ `data_simulator.py`. |

### 2.3. Đặc trưng Đầu vào & Chính sách Tách Dữ liệu Nhạy cảm
- Pipeline M2 tạo **15 cột đầu vào** (`snapshot.parquet` 21 cột gồm khóa, split, nhãn, cờ) → sau preprocessing tạo **38 cột `float64` mã hóa**:
  - **4 đặc trưng hành vi (`date <= 27`):** lượt click trước ngày 27, số ngày hoạt động, xu hướng tương tác.
  - **3 đặc trưng học tập (`date <= 27`):** số bài nộp trước cắt, điểm trung bình bài đã nộp, chỉ báo thiếu bài nộp.
  - **6 nhóm nhân khẩu học / protected slices** (`gender`, `code_module`, `age_band`, `disability`, `imd_band`, `highest_education`) + `imd_band_missing`: chỉ phục vụ đánh giá công bằng (**Fairness Slices** ở M4/Gate 2) và **TUYỆT ĐỐI KHÔNG gửi sang DB backend (`ml_predictions`) hay prompt LLM**.
  - **Cờ chất lượng dữ liệu:** `insufficient_data` (true khi không có click và không có bài nộp trước ngày 27).

---

## 3. Bốn Ranh giới Hệ thống (Four Boundaries — CMU MLIP Lec 1)

Chi tiết phân rã 4 ranh giới lồng nhau (`Model → Pipeline → System → Product`) được quy chuẩn hóa tại [00-conventions.md](../00-conventions.md) §1.1:
1. **Model Boundary:** `Logistic Regression v2` (`logreg-v2:cea6cdea:48843ee8:1ccd9891`) + `Linear SHAP` (`shap_additivity <= 1e-8`) + dịch vụ `LLM Advisor Brief & Chat` (`LiteLLM` + `Ollama` failover + `fallback_review`).
2. **Pipeline Boundary:** `M1 (Ingest/Quarantine) → M2 (Snapshot day 27) → M3 (LeakageAuditor 16 probes + DataGate) → DriftMonitor → M4 (Preprocess/Train/Benchmark/MLGate/BehavioralGate) → Release → M5 (Batch Score & PG Upsert)`.
3. **System Boundary:** `PostgreSQL 16` (tách 2 role `lg_ml_writer` & `lg_api`) ↔ `FastAPI Backend` (`BE-MLOPS`) ↔ `React Advisor Dashboard` (`FE-MLOPS`) ↔ `Nginx Reverse Proxy` ↔ **Cố vấn học tập (`Human-in-the-loop`)**.
4. **Product Boundary:** Quy trình ra quyết định của cố vấn ở tuần 5, chính sách ngân sách cảnh báo 20%, bảo vệ quyền riêng tư sinh viên và đo lường giá trị thực tế theo [product-value-protocol.md](product-value-protocol.md).

---

## 4. Các Bên Liên quan & Phân quyền Tương tác (Stakeholders)

| Vai trò | Phạm vi Tương tác Hợp lệ | Tài nguyên / Route Được phép |
| :--- | :--- | :--- |
| **Advisor (Cố vấn học tập)** | Đăng nhập, lọc hàng đợi ưu tiên (`7` học phần, `4` kỳ), xem hồ sơ sinh viên & SHAP/4-week activity, tạo/sửa/duyệt/từ chối Advisor Brief kèm feedback, hỏi đáp Chat Copilot. | `/overview`, `/advisor`, `/students/:m/:p/:s`, `/predictions*`, `/briefs*` |
| **Admin (Quản trị viên / MLOps)** | Toàn quyền Advisor + giám sát Evaluation Scorecards (`data`, `ml`, `llm`, `behavioral`), Drift & Active Release, Telemetry (`/metrics`), nhật ký kiểm toán (`audit_logs`), kích hoạt evaluation run. | Toàn bộ route Advisor + `/evaluations`, `/audit`, `POST /evaluations/run`, `GET /audit-logs`, `GET /metrics` |
| **Student (Sinh viên)** | **Không tương tác trực tiếp với hệ thống.** Danh tính gốc `id_student` được băm thành `student_key` (16-hex) trước khi vào backend/UI/LLM. | **0 endpoints / 0 UI / 0 auto-emails** |

---

## 5. Ranh giới Phạm vi Hệ thống (Strict In-Scope vs Out-of-Scope)

### 5.1. Trong Phạm vi (In-Scope — Thực thi trong Đồ án Chủ đề 4)
- Dự báo rủi ro theo lô tại mốc `cutoff_day = 27` với 4 trạng thái tường minh (`scored`, `manual_review`, `insufficient_data`, `no_prediction`).
- Giải thích phi nhân quả bằng Linear SHAP top 5 signals + thanh độ bất định (`uncertainty`).
- Tạo Advisor Brief + Chat Copilot tiếng Việt bám `advisor_guidelines.md`, kiểm tra trích dẫn cứng (`evidence_features`), chặn suy diễn nhân quả/tâm lý, failover `Ollama` & `fallback_review`.
- Quy trình Human Oversight hoàn chỉnh: `edit`, `accept`/`reject` kèm `feedback`, lưu lịch sử qua reload và ghi `audit_logs` theo `user_id` thực tế.
- Xác thực JWT + RBAC (`advisor`/`admin`), Observability JSON logs + Prometheus `/metrics`.
- Đóng gói & triển khai **Dual-Cloud Portable (Deploy-Where-Available)**: giữ sẵn sàng hạ tầng cho cả **Option A (Azure PaaS)** và **Option B (DigitalOcean Droplet VM)**, thực thi triển khai live trên nhà cung cấp khả dụng mà không đổi code ứng dụng.
- Pipeline phát hiện Drift (PSI, KS, Semantic `10x`, `ASM-03` Delayed Label Guard), Behavioral Gate & Continual Retraining Champion-vs-Challenger (kèm simulator 5 kịch bản).

### 5.2. Ngoài Phạm vi — CẤM TUYỆT ĐỐI (Strict Out-of-Scope Boundaries)
1. **No Auto-Interventions:** Không có bất kỳ hành động can thiệp tự động nào được kích hoạt từ điểm rủi ro hoặc gợi ý của LLM.
2. **No Student-Facing Endpoints / Auto-Emails:** Không xây dựng cổng sinh viên, không gửi email/SMS/push notification tự động tới sinh viên.
3. **No Grading / Disciplinary Actions:** Kết quả dự báo không được dùng để chấm điểm môn học, cảnh cáo học vụ tự động hay xử lý kỷ luật.
4. **No Psychological / Motivation / Character Profiling:** Cấm suy diễn nguyên nhân tâm lý ("sinh viên lười biếng", "mất động lực", "trầm cảm") hoặc kết luận nhân quả từ SHAP hoặc LLM.
5. **No PII / Sensitive Attributes in Backend DB, Logs, or LLM Prompts:** Tuyệt đối không đưa `id_student` thô, tên, hay thuộc tính nhạy cảm (`gender`, `disability`, `imd_band`, v.v.) vào bảng backend, file log hoặc prompt LLM.
6. **No Live LMS / SIS Connectors:** Không tích hợp trực tiếp Moodle/Canvas/SIS thật; nguồn dữ liệu là bộ OULAD chuẩn và `data_simulator.py`.
7. **No Reuse of `2014J` Holdout for Tuning:** Không chạy lại tuning hoặc model selection trên tập `2014J`.

---

## 6. Phân tích Chế độ Lỗi & Tác động (System FMEA)

| Mã FMEA | Chế độ Lỗi (Failure Mode) | Hậu quả tới Thế giới thực (Product Impact) | Cơ chế Phòng ngừa & Kiểm soát (Controls) |
| :--- | :--- | :--- | :--- |
| **FMEA-01** | **Rò rỉ Dữ liệu Tương lai (`date > 27`)** | Mô hình đạt điểm ảo trên paper nhưng vô dụng ngoài thực tế tuần 4. | `M3 LeakageAuditor` 3 lớp (ledger hash, row recompute, 16 future probes = 100% hard-fail). |
| **FMEA-02** | **Quá tải Cảnh báo (Alert Fatigue)** | Quá nhiều sinh viên bị gắn cờ (>30%) khiến cố vấn bỏ qua toàn bộ cảnh báo. | Khóa ngưỡng `validation_alert_budget_scalar_v1` (Top-20%), kiểm tra sai lệch `<= 1%` ở Gate 2 (`ml_gate.py`). |
| **FMEA-03** | **Tin cậy Mù quáng (Automation Bias)** | Cố vấn coi `risk_score` hay câu chữ LLM là chân lý nhân quả, hỗ trợ sai đối tượng. | Thanh `uncertainty` (`>=0.80 -> manual_review`), `insufficient_data` abstention, non-causal disclaimer, bắt buộc Accept/Reject + Feedback. |
| **FMEA-04** | **LLM Bịa số liệu / Suy diễn Tâm lý** | Cố vấn nhận tư vấn sai lệch hoặc mang tính kỳ thị/phán xét sinh viên. | Nạp `advisor_guidelines.md` + deterministic guardrails chặn từ khóa nhân quả/tâm lý/PII + kiểm chứng `evidence_features` + `llm_gate.py`. |
| **FMEA-05** | **Sự cố Dịch vụ LLM / DB / Drift Dữ liệu Bẩn** | Gián đoạn luồng làm việc cố vấn hoặc tự động retrain làm hỏng mô hình production. | 2 tầng failover (`Ollama -> fallback_review`), DB `503` an toàn, Drift Triage chặn retrain khi lỗi ngữ nghĩa (`10x`) hoặc thiếu nhãn (`ASM-03`). |
