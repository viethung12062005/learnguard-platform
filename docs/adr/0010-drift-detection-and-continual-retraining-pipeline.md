# ADR-0010 — Kiến trúc Phát hiện Data Drift, Chẩn đoán Triage và Pipeline Tái huấn luyện Liên tục (Champion vs. Challenger)

- **Trạng thái:** Accepted
- **Ngày:** 2026-11-23

## 1. Bối cảnh

Theo giáo trình **CMU MLIP** (Ch. 13, 15, 16, 17, 19) và **Bài giảng Lec 4–6**:
1. Dữ liệu hành vi học tập trên LMS thay đổi theo từng khóa/kỳ học (covariate shift, label-prior shift, concept shift) hoặc chịu ảnh hưởng từ lỗi thu thập/đồng bộ dữ liệu (data cascades, schema/semantic drift).
2. Nếu pipeline tự động huấn luyện lại mô hình ngay khi thấy cảnh báo `PSI > threshold` mà không phân biệt lỗi dữ liệu với dịch chuyển phân bố thực tế (Lec 4 Q20), mô hình mới sẽ học trên dữ liệu hỏng.
3. Ngược lại, nếu một mô hình mới được huấn luyện khi có dữ liệu kỳ mới nhưng chỉ được kiểm tra bằng một chỉ số tổng hợp (như ROC-AUC), nó có thể vi phạm ngân sách cảnh báo 20% của cố vấn, vi phạm tính đơn điệu hành vi (Lec 5 Directional Expectation), hoặc gây sai lệch công bằng giữa các nhóm sinh viên.
4. Đồng thời, repo `Data-ML-MLOPS` là upstream read-only theo quy ước ranh giới dự án (`AGENT.md` §2).

## 2. Quyết định

1. **Đặt tầng điều phối Drift, Simulation, Behavioral Gate và Continual Retraining tại `learnguard-platform/deploy/ml/`:**
   - Tái sử dụng trực tiếp các hàm lõi đã kiểm định của package `learnguard` (`ingest_oulad`, `build_feature_snapshot`, `LeakageAuditor`, `DataQualityGate`, `build_preprocessing_artifact`, `train_logistic_baseline`, `run_data_gate`, `run_ml_gate`, `publish_evaluation_run`, `score_snapshot`, `PredictionStore`) mà không cần sửa code nội bộ của `Data-ML-MLOPS`.
2. **Thiết kế Bộ Chẩn đoán Drift Đa tầng (`drift_monitor.py`):**
   - Kết hợp kiểm tra cấu trúc/ngữ nghĩa (Semantic & Scale Anomaly Check), tỷ lệ thiếu dữ liệu (Missingness Delta), tỷ lệ quy mô (Volume Ratio), kiểm định phân bố (PSI + Two-Sample KS test) và phân tích theo lát cắt học phần (Slice PSI).
   - Phân tách rõ 4 quyết định điều phối:
     - `NO_DRIFT`: Chấm điểm bằng Champion hiện hành.
     - `WARN_MONITOR`: Ghi cảnh báo, tiếp tục chấm điểm bằng Champion hiện hành.
     - `DATA_QUALITY_OR_SEMANTIC_FAILURE`: **Chặn retraining và chặn ghi đè dự đoán**, kích hoạt Safe Mode và báo cáo lỗi dữ liệu.
     - `DRIFT_RETRAIN_RECOMMENDED`: Kích hoạt huấn luyện Challenger và đánh giá Champion vs. Challenger.
3. **Thiết kế Cổng Đánh giá Champion vs. Challenger 3 Lớp (`retrain_pipeline.py` + `behavioral_gate.py`):**
   - Mọi mô hình Challenger vừa huấn luyện phải vượt qua đồng thời 3 Scorecard (`eval-report.v1`):
     - **Gate 1 — Data Scorecard (`eval_data.json`):** Đảm bảo snapshot huấn luyện hợp lệ.
     - **Gate 2 — ML Scorecard (`eval_ml.json`):** So sánh trực tiếp với Champion thông qua tham số `baseline_model_dir` (`regression_vs_baseline` không tụt quá `0.01`, `roc_auc >= min_roc_auc`, `precision@Top20% >= 0.35`, `shap_additivity <= 1e-8`, `fairness_slices`).
     - **Gate 3 — Behavioral Scorecard (`eval_behavioral.json`):** Kiểm thử hành vi theo Lec 5 (`mft_canonical_profiles`, `invariance_row_permutation`, `invariance_pseudonymous_key`, `directional_clicks_monotonicity`, `directional_score_monotonicity`, `abstention_and_uncertainty_routing`).
   - Tất cả Scorecard được xuất nguyên tử (atomic publish) vào `artifacts/evaluations/<run-id>/` để Backend API (`GET /evaluations`) hiển thị ngay trên giao diện quản trị.
4. **Quản lý Phiên bản Release Bất biến & Con trỏ Active Release (`active_release.json`):**
   - Khi Challenger vượt qua toàn bộ cổng, pipeline đóng gói release bất biến kèm ngưỡng Top-20% mới trên tập validation và cập nhật nguyên tử file `artifacts/model-releases/active_release.json` (lưu cả `current_release` lẫn `previous_release` để hỗ trợ rollback mô hình tức thì).
5. **Bộ Mô phỏng Kịch bản Drift Có Kiểm soát (`data_simulator.py`):**
   - Cung cấp 5 kịch bản mô phỏng deterministic (`baseline_no_drift`, `gradual_covariate_drift`, `new_semester_cohort`, `corrupted_feed_quarantine`, `rejected_challenger_guard`) chạy trên không gian tạm cô lập hoặc thư mục mô phỏng chỉ định, cho phép kiểm chứng toàn bộ hành vi của pipeline trong CI/CD và demo.

## 3. Hệ quả

- Đáp ứng trọn vẹn yêu cầu lý thuyết của sách **CMU MLIP** và bài giảng **Lec 1–6**.
- Vừa tự động hóa được quá trình retraining khi có dữ liệu mới / drift thật, vừa có chốt chặn an toàn chống lại lỗi dữ liệu (Data Cascades) và suy thoái mô hình (Model Regression).
- Có thể chạy mô phỏng lại toàn bộ chu trình bất cứ lúc nào chỉ với 1 lệnh CLI hoặc 1 lần bấm trên GitHub Actions.
