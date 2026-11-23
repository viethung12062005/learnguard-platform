# Đặc tả Kỹ thuật: Phát hiện Data Drift, Mô phỏng Dữ liệu Mới và Pipeline Tái huấn luyện Liên tục (Continual Retraining Specification)

> **Phiên bản:** 1.0 (2026-11-23)
> **Nền tảng lý thuyết:** CMU MLIP Ch. 13, 15, 16, 17, 19 & Bài giảng Lec 4 (Data Quality Engineering), Lec 5 (Model Quality & Behavioral Testing), Lec 6 (System-Level Testing).
> **Thành phần thực thi:** `learnguard-platform/deploy/ml/{drift_monitor.py, data_simulator.py, behavioral_gate.py, retrain_pipeline.py}`.

---

## 1. Phân loại Dịch chuyển Phân bố & Quy tắc Phản ứng (Lecture 4 Q19–Q22)

Trong hệ thống dự báo sớm kết quả học tập LearnGuard, không phải mọi thay đổi phân bố đều giống nhau và **không phải mọi cảnh báo drift đều được phép kích hoạt retraining ngay lập tức**.

### 1.1. Bảng Phân loại 5 Dạng Dịch chuyển (Drift Taxonomy)

| Loại Dịch chuyển | Định nghĩa Toán học / Kỹ thuật | Ví dụ Thực tế trong LearnGuard | Quyết định Vận hành Chuẩn (Lec 4 Q20) |
| :--- | :--- | :--- | :--- |
| **1. Schema / Semantic Drift** | Cấu trúc cột giữ nguyên nhưng ý nghĩa/đơn vị thay đổi hoặc lỗi bộ trích xuất LMS (`quantity` nhân 100, ngày âm vô lý, điểm `> 100`). | LMS nâng cấp làm `sum_click` ghi nhận cả heartbeat tự động (tăng 50 lần) hoặc mất toàn bộ sự kiện nộp bài. | **CẤM RETRAIN.** Đưa vào `quarantine` / `SAFE_MODE`, giữ nguyên model Champion hiện tại, cảnh báo Data Engineer sửa bộ trích xuất. |
| **2. Covariate Shift** | $P(X)$ thay đổi nhưng $P(Y \mid X)$ tương đối ổn định. | Học kỳ mới có tỷ lệ sinh viên học trực tuyến nhiều hơn (`n_clicks_before_cutoff` dịch chuyển với `PSI > 0.20`). | Chẩn đoán theo slice (`code_module`, `code_presentation`). Khi có nhãn xác thực của kỳ mới → **Kích hoạt Retraining & Champion-vs-Challenger Gate**. |
| **3. Label-Prior Shift** | $P(Y)$ thay đổi ($\lvert \text{rate}_{\text{new}} - \text{rate}_{\text{base}} \rvert > 0.10$). | Tỷ lệ sinh viên bỏ học/trượt trong kỳ mới tăng đột biến do thay đổi quy chế thi. | Kiểm tra độ lệch `realized_alert_rate` so với ngân sách 20%; tái huấn luyện và hiệu chỉnh lại ngưỡng Top-20% trên tập validation mới. |
| **4. Concept Shift** | $P(Y \mid X)$ thay đổi (mối quan hệ giữa hành vi tuần 1–4 và kết quả cuối kỳ thay đổi). | Học phần chuyển từ bài tập tự luận sang trắc nghiệm hàng tuần khiến số lần nộp bài sớm mang ý nghĩa khác. | Mô hình cũ giảm `ROC-AUC` / `Precision@20%`. **Bắt buộc Retraining**, kiểm tra `regression_vs_baseline` và `Behavioral Gate` trước khi promote. |
| **5. Individual OOD / Missingness** | Một cá thể sinh viên nằm ngoài vùng phân bố hoặc không có dữ liệu tương tác. | Sinh viên đăng ký muộn, 0 click và 0 bài nộp tính tới ngày 27, hoặc `uncertainty >= 0.80`. | Xử lý ở tầng **Abstention** (`status = insufficient_data` hoặc `manual_review`), không dùng để retrain. |

---

## 2. Đặc tả Các Chỉ số Đo lường Drift (`drift-report.v1`)

Module `drift_monitor.py` nhận vào `current_snapshot.parquet` và `baseline_snapshot.parquet` (cùng ledger tương ứng) để tính toán bộ chỉ số toàn diện:

1. **Population Stability Index (PSI) cho biến số (`NUMERIC_FEATURES`) và biến phân loại (`CATEGORICAL_FEATURES`):**
   $$\text{PSI} = \sum_{i=1}^{B} \left( p_{\text{cur}, i} - p_{\text{base}, i} \right) \times \ln\left(\frac{\max(p_{\text{cur}, i}, \epsilon)}{\max(p_{\text{base}, i}, \epsilon)}\right), \quad \epsilon = 10^{-6}$$
   - Chỉ tính khi cả hai tập có cỡ mẫu $\ge \text{MIN\_PSI\_SAMPLE} = 200$ (tránh nhiễu mẫu nhỏ).
   - Ngưỡng:
     - $\text{PSI} \le 0.10$: `pass` (ổn định)
     - $0.10 < \text{PSI} \le 0.20$: `warn` (dịch chuyển nhẹ — theo dõi)
     - $\text{PSI} > 0.20$: `fail` (dịch chuyển mạnh — cần triage/retrain)
2. **Kiểm định Two-Sample Kolmogorov-Smirnov (KS Statistic & p-value) cho biến số:**
   - Đo khoảng cách cực đại giữa hai hàm phân bố tích lũy thực nghiệm $D_{\text{KS}} = \sup_x \lvert F_{\text{cur}}(x) - F_{\text{base}}(x) \rvert$.
   - Ngưỡng cảnh báo kết hợp: $D_{\text{KS}} > 0.15$ và $p\text{-value} < 0.01$.
3. **Kiểm định Ngữ nghĩa & Quy mô Vật lý (Semantic & Scale Anomaly Guard):**
   - Phát hiện lỗi ngữ nghĩa (Lec 4 Q05/Q12) khi trung vị hoặc phân vị 95% của biến hành vi (`n_clicks_before_cutoff`, `n_submitted_before_cutoff`) tăng/giảm đột biến quá $10\times$ so với baseline hoặc vi phạm miền giá trị vật lý (`avg_score_submitted < 0` hoặc `> 100`, tỷ lệ null tăng vọt $> 60\%$).
   - Nếu phát hiện → gắn cờ `semantic_anomaly_detected = True` và chuyển thẳng sang trạng thái `DATA_QUALITY_OR_SEMANTIC_FAILURE` (chặn retrain!).
4. **Phân tích Drift theo Lát cắt (Slice-Level Drift Diagnosis — Lec 4 Q21):**
   - Tính PSI riêng cho từng `code_module` để chỉ rõ drift xảy ra trên toàn hệ thống (`global_shift`) hay chỉ cục bộ ở một số học phần (`localized_slice_shift`).
5. **Tuyên bố Cảnh báo Hành động (Actionable Alert-to-Response Statement — Lec 4 Q22):**
   - Mỗi báo cáo `drift_report.json` bắt buộc xuất trường `actionable_response`:
     - `recommended_action`: `SCORE_WITH_CHAMPION` | `SCORE_WITH_CHAMPION_AND_MONITOR` | `SCORE_WITH_CHAMPION_AWAIT_LABELS` | `TRIGGER_RETRAINING` | `QUARANTINE_AND_SAFE_MODE`
     - `owner`: `mlops_engineer` | `data_engineer`
     - `affected_features`: danh sách đặc trưng vượt ngưỡng kèm PSI & KS
     - `affected_slices`: danh sách học phần bị ảnh hưởng
     - `rationale`: giải thích rõ lý do theo chuẩn MLIP (bao gồm trường hợp `ASM-03` chưa có nhãn `final_result` ở tuần 4 thì chấm điểm bằng Champion và chờ nhãn cuối kỳ thay vì retrain mù).

---

## 3. Đặc tả Cổng Kiểm thử Hành vi Mô hình (`behavioral_gate.py` — Lecture 5)

Ngoài `DataGate` (7 checks) và `MLGate` (6 checks) có sẵn trong `Data-ML-MLOPS`, `learnguard-platform` bổ sung **Gate 4: Behavioral Model Testing (`subject = "behavioral"`)** theo chuẩn `eval-report.v1`:

| Check ID | Kỹ thuật (Lec 5) | Mô tả Kiểm định | Tiêu chí Pass |
| :--- | :--- | :--- | :--- |
| `mft_canonical_profiles` | **Minimum Functionality Test (MFT)** | Tạo 2 nhóm hồ sơ cực trị từ phân vị thực tế: (A) Sinh viên tích cực (clicks P90, nộp đủ bài, điểm >= 85) và (B) Sinh viên ngưng trệ (clicks rất thấp P10, 0 bài nộp). | `mean_risk(B) > mean_risk(A) + 0.25` và `100%` hồ sơ nhóm B có rủi ro cao hơn nhóm A cùng học phần. |
| `invariance_row_permutation` | **Invariance / Metamorphic Test (INV)** | Hoán vị ngẫu nhiên thứ tự các dòng trong tập dữ liệu đầu vào trước khi transform & predict. | Sai số tuyệt đối cực đại của `risk_score` sau khi khớp lại theo khóa $\le 10^{-12}$. |
| `invariance_pseudonymous_key` | **Contract Invariance (INV)** | Kiểm tra tính bất biến của hàm ẩn danh `student_key` trên các test vector chuẩn (`AAA/2013B/1 -> 4c337e13fc7b6871`). | Khớp 100% với test vector trong `DB_CONTRACT.md`. |
| `directional_clicks_monotonicity` | **Directional Expectation Test (DIR)** | Giữ nguyên mọi đặc trưng khác (*ceteris paribus*), giảm `n_clicks_before_cutoff` và `click_trend_w3_w4` đi 50% trên tập mẫu validation. | Điểm rủi ro trung bình không được giảm (`mean_delta >= -1e-9`) và $\ge 95\%$ cá thể có rủi ro tăng hoặc giữ nguyên. |
| `directional_score_monotonicity` | **Directional Expectation Test (DIR)** | Giữ nguyên mọi đặc trưng khác, giảm `avg_score_submitted` đi 25 điểm trên các sinh viên đã nộp bài. | Điểm rủi ro trung bình phải tăng hoặc giữ nguyên (`mean_delta >= -1e-9`) và $\ge 95\%$ cá thể thỏa mãn kỳ vọng hướng. |
| `abstention_and_uncertainty_routing` | **Safeguard & Abstention Test (Lec 1/5/6)** | Kiểm tra bộ định tuyến trạng thái `BatchScorer.assign_review_state` trên các trường hợp `insufficient_data` và `uncertainty >= 0.80`. | 100% dòng `insufficient_data` có `predicted_label = None`; 100% dòng `uncertainty >= 0.80` (và đủ dữ liệu) có `status = manual_review`. |

---

## 4. Đặc tả Bộ Mô phỏng Dữ liệu Mới & Kịch bản Retraining (`data_simulator.py`)

Để phục vụ kiểm thử tự động trong CI/CD, diễn tập vận hành (GameDay / Chaos testing — Lec 6) và trình diễn (demo) khả năng thích ứng của hệ thống khi có dữ liệu mới, `data_simulator.py` hỗ trợ 5 kịch bản mô phỏng hoàn toàn cô lập (không làm bẩn dữ liệu gốc):

1. **`baseline_no_drift`**:
   - Dữ liệu kỳ hiện tại không đổi so với baseline.
   - **Kỳ vọng:** `DriftMonitor` trả về `NO_DRIFT`, bỏ qua huấn luyện lại, chấm điểm trực tiếp bằng Champion hiện hành.
2. **`gradual_covariate_drift`**:
   - Mô phỏng học kỳ mới trong đó mức độ tương tác LMS (`n_clicks_before_cutoff`, `click_trend_w3_w4`) và điểm đánh giá sớm (`avg_score_submitted`) dịch chuyển đáng kể ($\text{PSI} > 0.20$), kèm nhãn kết quả học kỳ mới.
   - **Kỳ vọng:** `DriftMonitor` phát hiện `DRIFT_RETRAIN_RECOMMENDED` → Kích hoạt `retrain_pipeline.py` → Huấn luyện Challenger → Vượt qua cả 3 cổng (`Data Gate`, `ML Gate`, `Behavioral Gate`) → Đóng gói release mới (`model-release.v1`), cập nhật `active_release.json` và chấm điểm M5.
3. **`new_semester_cohort`**:
   - Mô phỏng dữ liệu học kỳ mới được sáp nhập/cập nhật vào kho dữ liệu huấn luyện & kiểm định với quy mô mẫu mở rộng và phân bố đặc trưng mới.
   - **Kỳ vọng:** Toàn bộ chuỗi `M1 → M2 → M3 → Drift Monitor → M4 → Multi-Gate Evaluation → Release → M5` chạy thành công đầu-cuối, tạo phiên bản `snapshot_version` mới và `model_version` mới có đầy đủ provenance hash.
4. **`corrupted_feed_quarantine`** *(Kiểm chứng Lec 4 Q05/Q12/Q20)*:
   - Mô phỏng sự cố bộ trích xuất LMS bị lỗi ngữ nghĩa (ví dụ: cột click bị nhân hệ số $50\times$ do lỗi đơn vị hoặc tỷ lệ thiếu dữ liệu vượt ngưỡng 75%).
   - **Kỳ vọng:** Hệ thống **tự động phát hiện lỗi ngữ nghĩa / chất lượng dữ liệu**, trả về `DATA_QUALITY_OR_SEMANTIC_FAILURE`, **CHẶN quá trình retraining** để bảo vệ Champion model không bị nhiễm dữ liệu rác, và giữ hệ thống ở trạng thái Safe Mode.
5. **`rejected_challenger_guard`** *(Kiểm chứng Lec 5/6 Release Gate)*:
   - Mô phỏng trường hợp một ứng viên Challenger không đạt ngưỡng chất lượng (`min_roc_auc` cao hơn khả năng của model hoặc bị suy giảm so với Champion).
   - **Kỳ vọng:** Cổng `MLGate` trả về `FAIL`, pipeline **từ chối promote Challenger**, giữ nguyên Champion cũ trong `active_release.json`.
