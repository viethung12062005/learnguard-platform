# Chiến lược Kiểm thử Hệ thống & Cổng Chất lượng (Test Strategy & Release Gates)

> **Phiên bản:** 1.0 (2026-11-23)
> **Nền tảng tham chiếu:** **CMU MLIP (Lectures 4–6)** — *Data Contracts, Behavioral Model Testing, LLM Evaluation, System-Level Testing ("Green components, red system"), Safeguard Drills* · Quy chuẩn [00-conventions.md](../00-conventions.md) §6 · Ma trận truy vết [traceability.md](../02-requirements/traceability.md).

---

## 1. Tháp Kiểm thử 6 Tầng (6-Layer AI System Testing Pyramid)

Để phòng tránh hiện tượng **"Green components, red system"** và **"Silent success"** (CMU MLIP Lec 6), LearnGuard thực thi kiểm thử bắt buộc từ đơn vị nhỏ nhất đến diễn tập sự cố trên hạ tầng cloud:

| Tầng | Phạm vi & Mục tiêu | Kho mã nguồn & Bộ kiểm thử | Lệnh Thực thi Chuẩn | Tiêu chí Chặn (Hard-Fail Gate) |
| :--- | :--- | :--- | :--- | :--- |
| **L1: Unit & Determinism** | Kiểm tra hàm đơn vị, schema Pydantic/TypeScript, tính tái lập deterministic (`seed=42`), lint/type-check. | • `Data-ML-MLOPS/tests/` (`163 passed, 8 skipped`)<br>• `BE-MLOPS/tests/` (9 suites)<br>• `FE-MLOPS`: `tsc --noEmit && vite build`, `tests/run.mjs`, `tests/test-chat.ts`<br>• `learnguard-platform`: `ruff check`, `bash -n` | `pytest tests/ -q` (`Data-ML-MLOPS`)<br>`python -m unittest discover -s tests -v` (`BE-MLOPS`)<br>`npm run build && node tests/run.mjs` (`FE-MLOPS`) | Bất kỳ unit test, lint hoặc type-check nào thất bại. |
| **L2: Semantic & Boundary Contracts** | Kiểm chứng hợp đồng liên repo: công thức `student_key` (16-hex SHA-256), 17 cột `ml_predictions`, 4 trạng thái `PredictionStatus`, `eval-report.v1`, `drift-report.v1`, quyền DB 2 role (`lg_api` read-only vs `lg_ml_writer`). | • `learnguard-platform/tests/test_system_contracts.py`<br>• `BE-MLOPS/tests/test_student_keys.py`, `test_ml_predictions.py`<br>• `BE-13` (`test_db_roles_and_resilience.py`) | `pytest tests/test_system_contracts.py -v` | Lệch test vector `student_key`, thiếu cột bắt buộc, hoặc `lg_api` có đường ghi vào `ml_predictions`. |
| **L3: Model & LLM Behavioral Testing (Lec 5)** | Kiểm chứng hành vi mô hình ngoài các metric tổng hợp: `MFT`, `Invariance`, `Directional`, `Abstention Routing`, `SHAP Additivity`, `6-Slice Fairness`, `Calibration`, `LLM Citation & Red-Team`. | • `learnguard-platform/deploy/ml/behavioral_gate.py` & `tests/test_behavioral_gate.py`<br>• `Data-ML-MLOPS/src/learnguard/evaluation/{ml_gate,llm_gate,llm_judge}.py`<br>• `BE-14`, `ML-11`, `AI-06` | `pytest tests/test_behavioral_gate.py -v`<br>`learnguard evaluate all` | Vi phạm tính đơn điệu (Directional), sai số SHAP `> 1e-8`, lộ PII/nhân quả trong LLM, hoặc `ROC-AUC < 0.70`. |
| **L4: Drift & Retraining Integration** | Kiểm thử toàn chuỗi `M1→M3 → DriftMonitor → M4 → 3-Gate → Champion vs Challenger → Release → M5` trên 5 kịch bản mô phỏng deterministic + `ASM-03` Delayed Label Guard + `--mode rollback`. | • `learnguard-platform/deploy/ml/{data_simulator,drift_monitor,retrain_pipeline}.py`<br>• `learnguard-platform/tests/test_drift_and_retraining.py` | `pytest tests/test_drift_and_retraining.py -v` | Tự động retrain trên dữ liệu lỗi ngữ nghĩa (`10x`), bỏ qua `ASM-03`, hoặc promote model kém hơn Champion. |
| **L5: Safeguard, Fault-Injection & E2E UX** | Kiểm thử ứng xử khi thành phần hỏng: LLM timeout/failover (`Ollama` → `fallback_review`), thiếu dữ liệu (`insufficient_data`), bất định (`manual_review`), DB sập (`503` không lộ DSN), a11y + Playwright E2E Human Oversight. | • `BE-MLOPS/tests/test_llm.py`, `test_briefs.py`, `BE-13`<br>• `FE-MLOPS`: `FE-11`, `FE-12` (Playwright E2E + a11y) | `pytest`/`unittest` + Playwright E2E suite | Hệ thống crash HTTP 500, lộ secret/DSN trong response/log, hoặc cho phép thao tác không qua Human Oversight. |
| **L6: Post-Deploy Smoke, IaC & GameDay Drills** | Kiểm chứng sau triển khai live (Option A Azure PaaS hoặc Option B DO VM) + diễn tập rollback container (`< 60s`), rollback model (`--mode rollback`), restore PostgreSQL. | • `scripts/cd/smoke-test.sh`, `rollback-do.sh`, `scripts/db/restore-db.sh`<br>• `scripts/guardrails/check_plan.py` (`OPS-06`, `OPS-07`, `OPS-08`) | `bash scripts/cd/smoke-test.sh`<br>`terraform validate && terraform plan` | Healthcheck/smoke test thất bại (tự động kích hoạt rollback) hoặc `terraform plan` Azure chứa `azurerm_role_assignment`. |

---

## 2. Bốn Cổng Đánh giá Tự động (`eval-report.v1`) & Ngưỡng Chặn

Hệ thống hợp nhất 4 scorecard chuẩn hóa để `BE-MLOPS` (`GET /evaluations`) và `FE-MLOPS` (`EvaluationsPage`) hiển thị đồng bộ:

| Cổng | File Scorecard & Nguồn Sinh | Danh sách Kiểm tra Cốt lõi (Checks) | Ngưỡng Pass / Warn / Fail |
| :--- | :--- | :--- | :--- |
| **Gate 1: Data** | `eval_data.json`<br>(`learnguard evaluate data`) | `snapshot_schema`, `ledger_consistency`, `split_integrity`, `label_balance`, `missing_rate`, `duplicate_keys`, `drift_vs_baseline`, kèm `LeakageAuditor` (**16 future-event probes**). | • Rò rỉ `date > 27` hoặc trùng PK hoặc lệch schema: **FAIL (Hard Stop)**.<br>• `missing_rate`: warn `> 30%`, fail `> 60%`.<br>• `PSI`: pass `<= 0.10`, warn `0.10–0.20`, fail `> 0.20`. |
| **Gate 2: ML** | `eval_ml.json`<br>(`learnguard evaluate ml`) | `artifact_integrity`, `validation_metrics`, `alert_budget`, `shap_additivity`, `fairness_slices` (**mở rộng 6 chiều ở `ML-11`**: `gender`, `code_module`, `age_band`, `disability`, `imd_band`, `highest_education`), `calibration` (`ECE`/`Brier`), `regression_vs_baseline`. | • `ROC-AUC >= 0.70` (warn `< 0.75`).<br>• `Precision@Top20% >= 0.50` (fail `< 0.35`), sai lệch ngân sách `<= 1%`.<br>• `SHAP additivity <= 1e-8`.<br>• `FNR gap <= 0.10` (có guard cỡ mẫu nhỏ). |
| **Gate 3: LLM** | `eval_llm.json`<br>(`learnguard evaluate llm`) | Schema JSON validity, 100% citation validity (`evidence_features`), deterministic causal/psychological/PII guardrails (`BE-14`), `LLM-as-a-Judge` rubric 4 tiêu chí, đối chiếu 30 golden briefs chấm tay 2 người & red-team prompt-injection (`AI-06`). | • Schema error `< 5%`.<br>• Citation validity `= 100%` (không bịa feature).<br>• Điểm rubric trung bình `>= 3.5 / 5.0`.<br>• `0` ca lọt từ khóa nhân quả/tâm lý/PII. |
| **Gate 4: Behavioral** | `eval_behavioral.json`<br>(`deploy/ml/behavioral_gate.py`) | (1) `MFT` (rủi ro cao vs tích cực cao), (2) `Row Permutation Invariance`, (3) `Pseudonymous Key Invariance`, (4) `Clicks Directional`, (5) `Score Directional`, (6) `Abstention Routing` (`insufficient_data` & `uncertainty >= 0.80`). | • `MFT gap >= 0.25`.<br>• `Invariance max diff <= 1e-12`.<br>• Vi phạm `Directional` hoặc `Abstention` → **FAIL (Chặn promote)**. |

---

## 3. Chính sách Vệ sinh Tập Holdout (Holdout Hygiene Policy)

- Tập `holdout` (`2014J`, **9,214 dòng**) đã được sử dụng **đúng một lần** trong `benchmark-20261105-shap` (`holdout_access_policy = forbidden_prior_consumed`).
- **Quy tắc Bất biến:** Mọi hoạt động tuning hyperparameter, hiệu chỉnh xác suất (calibration), đánh giá công bằng (`ML-11`), hoặc thử nghiệm non-linear challenger `HistGradientBoostingClassifier` (`ML-12`) **CHỈ được phép chạy trên tập `validation` (`2014B`, 6,510 dòng)** (bằng cờ `--validation-only`) hoặc trên dữ liệu mô phỏng mới từ `data_simulator.py`.
- Lệnh `learnguard ml verify-release` sẽ **FAIL** nếu phát hiện `holdout_access_policy` bị thay đổi hoặc artifact bị chỉnh sửa.

---

## 4. Kế hoạch Diễn tập Safeguard & Kiểm thử Chịu lỗi (GameDay Drills — `OPS-07`)

Sau khi triển khai live lên môi trường cloud khả dụng (`OPS-06` DigitalOcean VM hoặc `OPS-08` Azure PaaS), nhóm thực hiện và lưu biên bản kiểm chứng 5 kịch bản diễn tập:

| Kịch bản Diễn tập | Cách Kích hoạt Mô phỏng (Fault Injection) | Hành vi Kỳ vọng & Ngưỡng Đạt |
| :--- | :--- | :--- |
| **Drill 1: Container / App Auto-Rollback** | Deploy tag/digest cố tình lỗi healthcheck trong `cd-digitalocean-prod.yml` hoặc chạy `rollback-do.sh`. | `smoke-test.sh` phát hiện lỗi và tự động quay về `last_good_release.env` trong **`<= 60 giây`**, HTTP `/health` xanh trở lại. |
| **Drill 2: Model Release Rollback** | Thực thi `retrain_pipeline.py --mode rollback --target-release-id <prev>` và score lại. | `active_release.json` trỏ về release trước, bảng `ml_predictions` cập nhật nguyên vẹn theo `model_version` cũ. |
| **Drill 3: PostgreSQL Backup & Restore** | Chạy `backup-db.sh` → xóa/làm sai lệch bảng thử nghiệm → chạy `restore-db.sh`. | Toàn bộ dữ liệu `briefs`, `decisions`, `audit_logs`, `ml_predictions` khôi phục 100% không mất giao dịch đã backup. |
| **Drill 4: Corrupted Feed & Delayed Labels (`ASM-03`)** | Chạy `mlops-drift-retrain.yml` với kịch bản `corrupted_feed_quarantine` (`10x`) và `gradual_covariate_drift` không có nhãn. | Dữ liệu lỗi ngữ nghĩa bị chặn ở `QUARANTINE` (cấm retrain); thiếu nhãn cuối kỳ ghi nhận `ASM-03 WARN_MONITOR`, không promote bừa. |
| **Drill 5: LLM Provider Outage & DB Disconnect** | Đặt sai `LLM_API_KEY` (hoặc ngắt mạng OpenRouter) khi gọi `POST /briefs/generate`; kiểm tra DB outage qua `BE-13`. | `POST /briefs/generate` trả HTTP 200 với `status = fallback_review` (hoặc Ollama); DB outage trả `503` sạch, **0 secret/DSN trong logs**. |

---

## 5. Ma trận Lệnh Kiểm chứng Nhanh trước Merge / Release

```bash
# 1. Platform contracts, drift, behavioral gate & lint (learnguard-platform)
.venv/bin/python -m ruff check deploy/ tests/ scripts/
.venv/bin/python -m pytest tests/ -v
bash -n scripts/cd/*.sh scripts/db/*.sh scripts/do/*.sh deploy/digitalocean/init-db.sh

# 2. Data & ML Pipeline + Evaluation Gates (Data-ML-MLOPS)
.venv/bin/python -m pytest tests/ -q
.venv/bin/learnguard ml verify-release \
  --release-artifact-dir artifacts/model-releases/logistic-production-20261105 \
  --snapshot artifacts/manual-runs/20261105-004543/snapshot/snapshot.parquet

# 3. Backend API, Auth & Guardrails (BE-MLOPS)
.venv/bin/python -m unittest discover -s tests -v

# 4. Frontend Build, Unit & E2E Tests (FE-MLOPS)
npm run build && node tests/run.mjs

# 5. Azure IaC Guardrail Parity (Option A)
python3 scripts/guardrails/check_plan.py --tf-dir infra/env/dev
```
