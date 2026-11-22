# Kế hoạch Công việc Chi tiết: AIE — AI / ML Engineer (Data Pipeline M1–M3, Non-Gen ML M4–M5, LLM M8 & Evaluation Gates)

> **Vai trò:** Chủ sở hữu Khoa học Dữ liệu, Huấn luyện & Giải thích Mô hình ML (`Data-ML-MLOPS`), Dịch vụ Tổng hợp LLM Advisor Brief & Chatbot (`BE-MLOPS/src/learnguard_backend/services/{llm,briefs,chat,chat_context}.py`), và Bộ Cổng Đánh giá Chất lượng (`learnguard evaluate {data,ml,llm}`).
> **Kho mã nguồn chính:** `ntk223/Data-ML-MLOPS` và `ntk223/BE-MLOPS/src/learnguard_backend/services/`.
> **Hợp đồng bắt buộc tuân thủ:** [PIPELINE_GUIDE.md](../../../Data-ML-MLOPS/docs/PIPELINE_GUIDE.md), [MODEL_EVALUATION_RELEASE_GUIDE.md](../../../Data-ML-MLOPS/docs/MODEL_EVALUATION_RELEASE_GUIDE.md), [M5_PREDICTION_BATCH.md](../../../Data-ML-MLOPS/docs/M5_PREDICTION_BATCH.md) và các nguyên lý **Data Quality, Model Quality & LLM Evaluation** của **CMU MLIP (Lec 4, Lec 5, Lec 6)**.
> **Ba Luật Vàng Bất biến:** (1) Tune hyperparameter và chọn threshold **CHỈ trên tập `validation` (`2014B`)**; (2) Tập `holdout` (`2014J`) chỉ chạm đúng 1 lần khi báo cáo benchmark; (3) Không bao giờ sửa trực tiếp `snapshot.parquet` hay đi vòng qua `LeakageAuditor`.

**Định nghĩa Hoàn thành (DoD) cho mọi Task:** `pytest Data-ML-MLOPS/tests -q` và `unittest` trong `BE-MLOPS` pass 100%, mọi artifact sinh ra đều có `manifest.json` + `success.json` kèm SHA-256 hợp lệ, không lộ `id_student` thô ra khỏi `snapshot.parquet`.

Tổng cộng: **14 tasks (50 giờ)**. Đã hoàn thành trong Baseline: **10 tasks (`☑`, 34 giờ)**, Đang mở / Cần làm tiếp: **4 tasks (`◐`/`☐`, ~16 giờ)**.

---

## Giai đoạn Baseline — Đã hoàn thành trên nhánh `main` (`72c96cd` & `a2bae92`) (34 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `ML-01` | **M1 Data Ingestion (`ingestion.py`)**: Kiểm định schema 7 bảng OULAD CSV, cách ly dòng lỗi vào `quarantine/`, khử trùng lặp và xuất Parquet canonical | `ingest_oulad` xuất `canonical/*.parquet` kèm SHA-256 và `ingestion_report.json`; không tự ý xóa hay impute mù dữ liệu lỗi. | 3 | — | `FR-01` |
| ☑ | `ML-02` | **M2 Point-in-Time Feature Snapshot (`features.py`)**: Xây dựng cohort đang học tại `cutoff_day=27`, 15 đặc trưng và `AsOfLedger` | Loại bỏ sinh viên đã rút học trước ngày 27 (`date_unregistration <= 27`); gán temporal split (`2013B+2013J -> train`, `2014B -> validation`, `2014J -> holdout`); xuất `snapshot.ledger.json`. | 4 | `ML-01` | `FR-01`, `FR-02` |
| ☑ | `ML-03` | **M3 Temporal Leakage Auditor (`leakage.py`)**: Kiểm toán 3 lớp chống rò rỉ dữ liệu tương lai | Verify ledger hash, tính lại đặc trưng từng dòng mẫu, và chạy 16 temporal injection probes; phát hiện 100% sự kiện có `date > 27`. | 4 | `ML-02` | `FR-02`, `NFR-ML1` |
| ☑ | `ML-04` | **M3 Data Quality Gate (`quality.py`) & Gate 1 (`data_gate.py`)**: Kiểm tra schema, missingness, volume ratio và PSI drift | Xuất scorecard `eval_data.json` (`eval-report.v1`) gồm 7 checks (`snapshot_schema`, `ledger_consistency`, `split_integrity`, `label_balance`, `missing_rate`, `duplicate_keys`, `drift_vs_baseline`). | 3 | `ML-02` | `FR-02`, `NFR-MLO1` |
| ☑ | `ML-05` | **M4 Train-Only Preprocessing & Logistic Regression Baseline v2 (`preprocessing.py`, `training.py`)** kèm Linear SHAP Background | Fit preprocessor chỉ trên `train`; huấn luyện Logistic Regression deterministic (`threadpool_limits=1`), đóng gói `shap_background.npz` và verify toàn vẹn bằng SHA-256. | 4 | `ML-03`, `ML-04` | `FR-03`, `FR-05` |
| ☑ | `ML-06` | **M4 Multi-Model Benchmark (`benchmark.py`), SHAP Explainability (`explainability.py`) & Immutable Release (`release.py`)** | So sánh Dummy, Logistic, ExtraTrees, HistGradientBoosting, RandomForest; xuất 21 Confusion Matrix CSV/PNG; khóa ngưỡng Top-20% Alert Budget (`0.810348`) và đóng gói `model-release.v1`. | 4 | `ML-05` | `FR-03`, `NFR-ML1`, `NFR-ML2` |
| ☑ | `ML-07` | **M5 Batch Scoring & PostgreSQL Upsert (`scoring.py`, `predictions_store.py`)** | Ẩn danh hóa `student_key` (16-hex SHA-256), định tuyến 4 trạng thái (`scored`, `manual_review`, `insufficient_data`, `no_prediction`), xuất `prediction-batch.v1` và upsert all-or-nothing vào `ml_predictions`. | 4 | `ML-06` | `FR-03`, `FR-05`, `FR-08` |
| ☑ | `ML-08` | **Gate 2 ML Evaluation Scorecard (`ml_gate.py`)**: Kiểm định 6 tiêu chí chất lượng model trên tập Validation | Xuất `eval_ml.json` (`artifact_integrity`, `validation_metrics`, `alert_budget`, `shap_additivity <= 1e-8`, `fairness_slices`, `regression_vs_baseline`). | 2 | `ML-06` | `NFR-ML1`, `NFR-ML4` |
| ☑ | `AI-01` | **M8 LiteLLM Client & Ollama Failover (`services/llm.py`)**: Điều phối LLM đồng bộ/bất đồng bộ kèm kiểm soát token & timeout | Giới hạn `8000` input tokens / `1000` output tokens; tự động failover từ OpenRouter/Gemini sang local `Ollama (qwen2.5:3b)` khi lỗi; chuẩn hóa `latency_ms`, `tokens`, `cost_usd`. | 3 | — | `FR-06`, `FR-08`, `NFR-PERF1` |
| ☑ | `AI-02` | **M8 Advisor Brief Generator, Citation Validator & Interactive Chat (`services/briefs.py`, `chat.py`, `chat_context.py`)** | Grounding vào `advisor_guidelines.md` và dữ liệu hành vi ẩn danh; kiểm tra trích dẫn `evidence_features`; tự động tạo `fallback_review` khi LLM không khả dụng; xuất `eval_llm.json` qua `llm_gate.py` & `llm_judge.py`. | 3 | `AI-01` | `FR-06`, `FR-08`, `NFR-LLM1` |

---

## Sprint 1 — Mở rộng Đánh giá Công bằng Đa Chiều (Multi-Slice Fairness) & Độ Hiệu chỉnh (Calibration) (8 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ◐ | `ML-11` | **Mở rộng Slice-based Evaluation & Fairness Analysis trên nhiều chiều (`gender`, `code_module`, `age_band`, `disability`, `imd_band`)** | Sử dụng `learnguard.ml.evaluation.fairness_slices` để xuất báo cáo đánh giá độ bền vững (robustness) và chênh lệch `FNR gap` / `Precision@Top20%` trên toàn bộ 5 chiều phân nhóm kèm cảnh báo cỡ mẫu nhỏ (`small_sample`), phục vụ mục 4 `ML robustness` & `Privacy & fairness` của đề bài. | 4 | `ML-08` | `NFR-ML4` |
| ☐ | `ML-12` | **Phân tích Chuyên sâu Early Detection (Week 4 False Negatives) & Trade-off Alert Workload (Top-10% vs Top-20% vs Top-30%)** | Viết script/report phân tích các ca sinh viên `At-risk` bị bỏ sót tại tuần 4 (False Negatives: sinh viên vẫn click đều ở 4 tuần đầu nhưng sụp đổ ở giữa kỳ) và đường cong đánh đổi giữa `Recall@K` với tải công việc cố vấn (`Alert Workload`), lưu kết quả vào `docs/reports/early-detection-and-workload-analysis.md`. | 4 | `ML-06`, `ML-11` | `NFR-ML1`, `NFR-ML2` |

---

## Sprint 2 — Hiệu chỉnh LLM-as-a-Judge với Đánh giá Con người & Thử nghiệm Giá trị Sản phẩm (8 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☐ | `AI-06` | **Hiệu chỉnh `LLM-as-a-Judge` (`llm_judge.py`) đối chiếu với Human Rubric Evaluation trên 20–30 Advisor Briefs mẫu (Lec 5)** | Tạo bộ 20–30 Advisor Briefs trên các tình huống đa dạng (`scored` rủi ro cao, `manual_review` độ không chắc chắn cao, `insufficient_data`, `fallback_review`); 2 thành viên chấm độc lập theo rubric 4 tiêu chí (Đúng dữ liệu, Có căn cứ trích dẫn, Hữu ích, Không suy diễn nhân quả/tâm lý) và so sánh hệ số đồng thuận với `learnguard evaluate llm`. | 4 | `AI-02` | `NFR-LLM1` |
| ☐ | `AI-07` | **Thực nghiệm Đo lường Giá trị Sản phẩm (Product/User Value Benchmark — Đề bài §4)** | Thiết kế và ghi nhận kết quả thử nghiệm so sánh thời gian cố vấn tổng hợp/đánh giá 10 hồ sơ sinh viên khi **không có AI hỗ trợ** (chỉ đọc bảng số liệu thô) so với khi **có LearnGuard (Risk Score + SHAP + Advisor Brief)**; lưu báo cáo vào `docs/reports/product-value-evaluation.md`. | 4 | `AI-06`, `FE-06` | `FR-06`, `FR-07` |
