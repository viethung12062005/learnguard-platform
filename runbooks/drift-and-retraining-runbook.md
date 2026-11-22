# Runbook Giám sát Data Drift, Chẩn đoán Sự cố Dữ liệu & Tái huấn luyện Liên tục (Continual Retraining)

> **Phiên bản:** 3.0 (2026-11-23)
> **Nền tảng lý thuyết:** CMU MLIP Lecture 4 (*Data Quality, Drift & Continual Learning*, Q15–Q22), Lecture 5 (*Behavioral Testing: MFT, Invariance, Directional*) & Lecture 6 (*Safeguards & Closed-Loop Telemetry*).
> **Tham chiếu ADR:** [ADR-0010](../../docs/adr/0010-drift-detection-and-continual-retraining-pipeline.md).

---

## 1. Nguyên tắc Cốt lõi: Không Retrain Mù quáng (Lecture 4 Q20 Protocol)

Khi bộ giám sát phát hiện phân bố dữ liệu đầu vào thay đổi mạnh (`PSI > 0.20`), **nguyên nhân phổ biến nhất trong thực tế không phải là hành vi sinh viên thay đổi đột ngột, mà là lỗi đường ống dữ liệu** (thay đổi đơn vị đo, thiếu file log VLE, nhân bản bản ghi, hoặc rò rỉ dữ liệu tương lai `date > 27`).

Do đó, hệ thống **LearnGuard** bắt buộc tuân thủ quy trình **Chẩn đoán 4 Trạng thái (4-State Drift Triage Protocol)** trước khi quyết định tái huấn luyện:

| Trạng thái Chẩn đoán (`triage_action`) | Điều kiện Kích hoạt | Hành động Tự động của `retrain_pipeline.py` | Hành động của Kỹ sư Vận hành |
| :--- | :--- | :--- | :--- |
| **`1. DATA_QUALITY_OR_SEMANTIC_FAILURE`** | Vi phạm schema `M1/M3`, phát hiện rò rỉ tương lai (`date > 27`), `sum_click <= 0`, `score ∉ [0, 100]`, `missing_rate > 60%`, hoặc `volume_ratio ∉ [0.10, 10.0]`. | **CHẶN RETRAIN & CHẶN SCORING (Safe Mode).** Giữ nguyên Champion model và dữ liệu `ml_predictions` hiện tại trong DB. | Kiểm tra file báo cáo `drift-report.v1` và thư mục `quarantine/`, liên hệ đội LMS/Data Engineering sửa nguồn trích xuất. |
| **`2. NO_DRIFT`** | Toàn bộ đặc trưng có `PSI <= 0.10`, `KS p-value >= 0.01`, tỷ lệ thiếu ổn định (`delta <= 5%`), không có nhãn học kỳ mới. | **Không cần retrain.** Sử dụng Champion Release hiện tại để chấm điểm (`M5 score`) và cập nhật bảng `ml_predictions`. | Không cần can thiệp. |
| **`3. WARN_MONITOR`** | Có ít nhất 1 đặc trưng rơi vào vùng cảnh báo sớm (`0.10 < PSI <= 0.20`) hoặc độ lệch tỷ lệ cảnh báo dự kiến (`alert_rate_shift`) nằm trong ngưỡng `3%–5%`, hoặc có drift nhưng **chưa có nhãn kết quả cuối kỳ (`ASM-03: Delayed Ground Truth`)**. | **Ghi nhận cảnh báo vào `drift-report.v1`.** Nếu chưa có nhãn mới để kiểm định Challenger, tiếp tục dùng Champion hiện tại và gắn cờ theo dõi sát hàng đợi `manual_review`. | Xem xét đặc trưng bị dịch chuyển trên Dashboard `/evaluations`; chuẩn bị thu thập nhãn từ kỳ học vừa kết thúc. |
| **`4. DRIFT_RETRAIN_RECOMMENDED`** | Dữ liệu vượt qua 100% kiểm tra ngữ nghĩa & chống rò rỉ (`M1–M3 PASS`), nhưng có `PSI > 0.20` (hoặc có thêm cohort học kỳ mới đã có nhãn `final_result`). | **Kích hoạt huấn luyện mô hình Challenger (`M4`)** và đưa vào **3 Cổng Kiểm định Bắt buộc (Data + ML Champion-vs-Challenger + Behavioral MFT/INV/DIR)** trước khi quyết định Promote. | Kiểm tra kết quả so sánh Champion vs Challenger trong `eval-report.v1`. |

---

## 2. Cách Đọc và Giải thích Báo cáo `drift-report.v1`

Mỗi lần chạy, `drift_monitor.py` xuất báo cáo JSON chuẩn hóa tại:
`/opt/learnguard/data/artifacts/drift-reports/<run_id>/drift_report.json`

Các trường quan trọng cần chú ý:
- `triage_status`: Một trong 4 trạng thái ở Mục 1 (`NO_DRIFT`, `WARN_MONITOR`, `DRIFT_RETRAIN_RECOMMENDED`, `DATA_QUALITY_OR_SEMANTIC_FAILURE`).
- `overall_max_psi` & `drifted_features`: Danh sách các đặc trưng có `PSI > 0.10` (ví dụ `n_clicks_before_cutoff`, `avg_score_submitted`, `click_trend_w3_w4`).
- `ks_tests`: Kết quả kiểm định phi tham số Kolmogorov-Smirnov (`statistic`, `p_value`) cho từng biến liên tục.
- `semantic_checks`: Kết quả kiểm tra tính bất biến ngữ nghĩa (`negative_clicks_count == 0`, `out_of_range_scores_count == 0`, `temporal_cutoff_violations == 0`, `volume_ratio`).
- `slice_drift`: Phân tích PSI theo từng lát cắt học phần (`code_module`) để tránh hiện tượng **Simpson's Paradox** (tổng thể ổn định nhưng một học phần cụ thể bị lệch nặng).

---

## 3. Ba Cổng Kiểm định Bắt buộc Khi Promote Mô hình Challenger

Mô hình Challenger chỉ được phép thay thế Champion trong `active_release.json` khi **cả 3 cổng** đều đạt trạng thái `PASS`:

1. **Cổng 1 — Data & Point-in-Time Leakage Gate (`M3`):**
   - `0` vi phạm rò rỉ tương lai qua 3 lớp kiểm tra (Ledger SHA-256, tính lại từng dòng, 16 probe tiêm sự kiện `date > 27`).
   - Không có khóa trùng lặp `(code_module, code_presentation, student_key)`.
2. **Cổng 2 — ML & Champion-vs-Challenger Gate:**
   - `ROC-AUC >= 0.70` và không thấp hơn Champion hiện tại quá ngưỡng dung sai (`-0.01`), hoặc cải thiện trực tiếp `Precision@Top20%` trên phân phối mới.
   - `Primary Outcome (Precision@Top20%) >= 0.50` (hard fail nếu `< 0.35`).
   - Sai lệch tỷ lệ cảnh báo thực tế so với ngân sách 20% của cố vấn (`alert_rate_error <= 0.01` trên tập validation).
   - `Fairness Slice FNR Gap <= 0.10` giữa các nhóm sinh viên.
3. **Cổng 3 — Behavioral Testing Gate (`behavioral_gate.py` — CMU MLIP Lec 5):**
   - **Minimum Functionality Tests (MFT):** Dự đoán đúng trạng thái `alert` cho hồ sơ sinh viên rủi ro rõ rệt, `normal` cho hồ sơ sinh viên tích cực điểm cao, và `insufficient_data` cho sinh viên có `0 click & 0 submission`.
   - **Invariance Tests (INV):** Hoán vị ngẫu nhiên thứ tự dòng dữ liệu không làm thay đổi điểm `risk_score` quá `1e-12`.
   - **Directional Expectation Tests (DIR):** Giảm số lượng click (`n_clicks_before_cutoff`) hoặc giảm điểm bài tập (`avg_score_submitted`) **không bao giờ được làm giảm điểm rủi ro** (`risk_score` phải đơn điệu không giảm khi hành vi học tập xấu đi).
   - **SHAP Additivity Invariant:** Sai số cộng tính Linear SHAP `max_abs_error <= 1e-8`.

---

## 4. Hướng dẫn Thực thi Pipeline trong Thực tế & Mô phỏng

### 4.1. Chạy trên DigitalOcean Production VM (Chế độ Tự động)
```bash
cd /opt/learnguard/deploy/digitalocean
docker compose -f docker-compose.prod.yml --profile batch run --rm ml-worker --mode auto
```

> [!NOTE]
> Trong kiến trúc Docker Compose tách biệt container (`api` và `ml-worker` độc lập), endpoint `POST /evaluations/run` trên UI mặc định trả về `HTTP 503` có chủ đích vì `ML_REPO_DIR` không được mount vào container `api`. Việc chạy pipeline đánh giá và tái huấn luyện được thực thi an toàn qua `ml-worker` (systemd timer hàng tuần `learnguard-ml-batch.timer`, chạy thủ công qua Docker Compose hoặc workflow `mlops-drift-retrain.yml`), và xuất kết quả `eval-report.v1` vào shared volume để trang `/evaluations` đọc qua `GET /evaluations`.

### 4.2. Chạy Mô phỏng các Kịch bản Drift để Kiểm định Hệ thống (`data_simulator.py`)

Bạn có thể chạy trực tiếp các kịch bản mô phỏng để kiểm chứng phản ứng của pipeline:

```bash
# Kịch bản 1: Dịch chuyển phân bố hành vi tự nhiên (Covariate Shift — kích hoạt đánh giá & retrain)
python learnguard-platform/deploy/ml/retrain_pipeline.py \
  --mode simulate \
  --scenario gradual_covariate_drift \
  --artifacts-dir /tmp/lg-sim-covariate

# Kịch bản 2: Học kỳ mới có thêm dữ liệu có nhãn (New Labeled Semester Cohort — promote Challenger)
python learnguard-platform/deploy/ml/retrain_pipeline.py \
  --mode simulate \
  --scenario new_semester_cohort \
  --artifacts-dir /tmp/lg-sim-cohort

# Kịch bản 3: Lỗi dữ liệu ngữ nghĩa / rò rỉ thời gian (Corrupted Feed — BẮT BUỘC chặn retrain theo Lec 4 Q20)
python learnguard-platform/deploy/ml/retrain_pipeline.py \
  --mode simulate \
  --scenario corrupted_feed_quarantine \
  --artifacts-dir /tmp/lg-sim-corrupted
```
