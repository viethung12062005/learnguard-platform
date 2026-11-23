# Kế hoạch Công việc Chi tiết: AIE — AI / ML Engineer (Data Pipeline M1–M3, ML M4–M5, LLM M8 & Eval Gates)

> **Vai trò:** Chủ sở hữu Khoa học Dữ liệu, Huấn luyện & Giải thích Mô hình ML (`Data-ML-MLOPS`), Dịch vụ LLM Advisor Brief & Chatbot (`BE-MLOPS/src/learnguard_backend/services/{llm,briefs,chat,chat_context}.py`), và Bộ Cổng Đánh giá (`learnguard evaluate {data,ml,llm}`).
> **Kho mã nguồn chính:** `ntk223/Data-ML-MLOPS` và `ntk223/BE-MLOPS/src/learnguard_backend/services/`.
> **Hợp đồng bắt buộc tuân thủ:** [PIPELINE_GUIDE.md](../../../../Data-ML-MLOPS/docs/PIPELINE_GUIDE.md), [MODEL_EVALUATION_RELEASE_GUIDE.md](../../../../Data-ML-MLOPS/docs/MODEL_EVALUATION_RELEASE_GUIDE.md), [M5_PREDICTION_BATCH.md](../../../../Data-ML-MLOPS/docs/M5_PREDICTION_BATCH.md) và [product-value-protocol.md](../../01-business-analysis/product-value-protocol.md).
> **Ba Luật Vàng Bất biến:** (1) Tune hyperparameter và chọn threshold **CHỈ trên tập `validation` (`2014B`, 6,510 dòng)**; (2) Tập `holdout` (`2014J`, 9,214 dòng) **ĐÃ TIÊU THỤ (`forbidden_prior_consumed`)** — nghiêm cấm tái sử dụng; (3) Không bao giờ sửa `snapshot.parquet` hay đi vòng qua `LeakageAuditor`.

**Định nghĩa Hoàn thành (DoD):** `pytest Data-ML-MLOPS/tests -q` pass 100%, mọi artifact có `manifest.json` + `success.json` kèm SHA-256 hợp lệ, không lộ `id_student` thô hoặc thuộc tính nhân khẩu học sang DB/LLM.

Tổng cộng (**khớp 100% [backlog.csv](../backlog.csv)**): **14 tasks (50 giờ)**. Đã hoàn thành: **10 tasks (`☑`, 34 giờ)** · Đang làm: **1 task (`◐`, 4 giờ)** · Cần làm tiếp: **3 tasks (`☐`, 12 giờ)**.

---

## Giai đoạn Baseline — Đã hoàn thành trên nhánh `main` (`72c96cd` & `a2bae92`) (34 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `ML-01` | **M1 Data Ingestion (`ingestion.py`)** | Kiểm định schema 7 bảng OULAD CSV, cách ly dòng lỗi vào `quarantine/`, xuất `canonical/*.parquet` + SHA-256. | 3 | — | `US-01` / `FR-01` |
| ☑ | `ML-02` | **M2 Point-in-Time Feature Snapshot (`features.py`)** | Cohort tại `cutoff_day=27` (loại `5,040` rút `<=27` + `18` đăng ký `>27` → `27,535` dòng), 15 đặc trưng + `AsOfLedger`. | 4 | `ML-01` | `US-01` / `FR-01` |
| ☑ | `ML-03` | **M3 Temporal Leakage Auditor (`leakage.py`)** | Kiểm toán 3 lớp (ledger hash, row recompute, 16 temporal injection probes) đạt 100% phát hiện rò rỉ `date > 27`. | 4 | `ML-02` | `US-02` / `FR-02` |
| ☑ | `ML-04` | **M3 Data Quality Gate & Gate 1 (`data_gate.py`)** | Xuất `eval_data.json` (`eval-report.v1`) kiểm tra 7 tiêu chí schema, ledger, split, balance, missing, duplicate, PSI. | 3 | `ML-02` | `US-02` / `FR-02` |
| ☑ | `ML-05` | **M4 Preprocessing & Logistic Baseline v2 (`training.py`)** | Fit preprocessor trên `train` (38 cột `float64`), huấn luyện Logistic v2 deterministic + `shap_background.npz`. | 4 | `ML-03`, `ML-04` | `US-03` / `FR-03` |
| ☑ | `ML-06` | **M4 Benchmark, SHAP & Immutable Release (`release.py`)** | Benchmark 5 models, xuất 21 Confusion Matrices, khóa ngưỡng Top-20% (`0.810348`), đóng gói `model-release.v1`. | 4 | `ML-05` | `US-04` / `NFR-ML1` |
| ☑ | `ML-07` | **M5 Batch Scoring & PG Upsert (`scoring.py`)** | Ẩn danh `student_key` (16-hex SHA-256), định tuyến 4 trạng thái abstention, upsert all-or-nothing `ml_predictions`. | 4 | `ML-06` | `US-04` / `FR-05` |
| ☑ | `ML-08` | **Gate 2 ML Evaluation Scorecard (`ml_gate.py`)** | Xuất `eval_ml.json` (`artifact_integrity`, `validation_metrics`, `alert_budget`, `shap_additivity <= 1e-8`, `fairness_slices`, `regression`). | 2 | `ML-06` | `US-13` / `NFR-ML1` |
| ☑ | `AI-01` | **M8 LiteLLM Client & Ollama Failover (`services/llm.py`)** | Giới hạn `8000/1000` tokens, retry & failover sang local `Ollama (qwen2.5:3b)`, ghi `latency_ms`, `tokens`, `cost_usd`. | 3 | — | `US-08` / `FR-08` |
| ☑ | `AI-02` | **M8 Brief Generator, Citation Validator, Chat & Gate 3 (`llm_gate.py`)** | Grounding, kiểm tra trích dẫn `evidence_features`, deterministic `fallback_review`, và `llm_gate.py`. | 3 | `AI-01` | `US-08` / `FR-06` |

---

## Sprint 1 — 6-Slice Fairness, Calibration ECE/Brier & Non-Linear Validation Analysis (8 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ◐ | `ML-11` | **Mở rộng `ml_gate.py` sang 6 Fairness Slices, Calibration (`ECE`/`Brier`) & Multi-K Workload Curves** | Mở rộng `ml_gate.py:42` từ `gender`-only sang **6 chiều** (`gender`, `code_module`, `age_band`, `disability`, `imd_band`, `highest_education`) kèm small-sample guard; bổ sung ngưỡng `ECE`/`Brier` calibration và đường cong FPR + `Precision@K`/`Recall@K` tại `K ∈ {10%, 20%, 30%}`. | 4 | `ML-08` | `US-15` / `NFR-ML4` |
| ☐ | `ML-12` | **Phân tích Tự động False Negatives Tuần 4 & Đánh giá Calibrated `HistGradientBoostingClassifier` trên `2014B`** | Tự động hóa phân nhóm lỗi False Negatives ở tuần 4 và đánh giá challenger phi tuyến `HistGradientBoostingClassifier` có hiệu chỉnh + `TreeSHAP` / permutation importance **chỉ trên `validation` (`2014B`)** (tuyệt đối không tái sử dụng `2014J`), lưu báo cáo tại `docs/reports/early-detection-and-workload-analysis.md`. | 4 | `ML-06`, `ML-11` | `US-04` / `NFR-ML2` |

---

## Sprint 2 — Calibration LLM-as-a-Judge, Chat Red-Team & Product Value Benchmark (8 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☐ | `AI-06` | **Hiệu chỉnh `llm_judge.py` trên 30 Dual-Human Golden Briefs & Thêm Red-Team Tests cho Chat Copilot** | Chấm chéo 2 người trên 30 golden briefs đa trạng thái và hiệu chỉnh `llm_judge.py` (kèm tiêu chí tuân thủ `advisor_guidelines.md`); bổ sung bộ test **red-team / prompt-injection & causal-claim blocking** cho Chat Copilot vào `llm_gate.py`. | 4 | `AI-02`, `BE-14` | `US-08` / `NFR-LLM1` |
| ☐ | `AI-07` | **Thực thi & Báo cáo Đo lường Giá trị Sản phẩm (`product-value-protocol.md`)** | Thực hiện thí nghiệm đối chứng bấm giờ và chấm chất lượng quyết định trên 10 hồ sơ chuẩn hóa (có vs không có LearnGuard) theo đúng [product-value-protocol.md](../../01-business-analysis/product-value-protocol.md); xuất báo cáo vào `docs/reports/product-value-evaluation.md`. | 4 | `AI-06`, `FE-13` | `US-10` / `FR-07` |
