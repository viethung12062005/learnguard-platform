# Báo cáo Kiểm toán Định nghĩa Hoàn thành — LearnGuard (Definition of Done Audit)

> **Ngày kiểm toán:** 2026-11-23
> **Nguồn đối chiếu duy nhất:** [backlog.csv](backlog.csv) · [00-workflow.md](../00-workflow.md) §4 · [test-strategy-and-gates.md](../06-testing/test-strategy-and-gates.md).
> **Nhãn phán quyết:** `PASS` (`Done`, đã có bằng chứng kiểm chứng thật) · `IN PROGRESS` (đang thực thi trên phần lõi) · `TODO` (đã xác minh gap & phân công trong Sprint 1–2).

---

## 1. Tổng quan Kết quả Kiểm toán (Audit Summary — 100% Parity với `backlog.csv`)

| Nhóm Phụ trách | Tổng Task | `PASS` (`Done`) | `IN PROGRESS` | `TODO` | Tổng Giờ (Còn lại) | Bằng chứng Kiểm thử Đã Xác minh |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`MLOPS`** (`learnguard-platform` `e9f9c81`) | **23** | **20** | **0** | **3** (`OPS-06`, `OPS-07`, `OPS-08`) | **84h** (12h) | Commit `e9f9c81`: 4/4 GitHub Actions workflows **GREEN**, 3 GHCR `@sha256` digests ghim trong `deploy/releases/prod.yaml`, `pytest` 6 passed, `ruff` 0 errors, `bash -n` & `--dry-run` pass, chuẩn hóa docs `00-*..06-*` (`ARC-05` & `CICD-05` `PASS`). |
| **`SWE1`** (`BE-MLOPS` `a2bae92`) | **14** | **7** | **1** (`BE-08`) | **6** (`BE-09`..`BE-14`) | **50h** (24h) | 9 test suites (`test_app`, `test_predictions_api`, `test_briefs`, `test_chat`, `test_evaluations_api`, `test_audit_logs_api`, `test_llm`, `test_ml_predictions`, `test_student_keys`) pass. Đã xác minh gap thật tại `api/auth.py`, `observability.py`, `repository.py:582`, `app.py:206`, `services/briefs.py`. |
| **`SWE2`** (`FE-MLOPS` `0f70e14`) | **13** | **8** | **1** (`FE-09`) | **4** (`FE-10`..`FE-13`) | **46h** (20h) | `npm run build` (`tsc --noEmit && vite build`) & `tests/test-chat.ts` pass. Đã xác minh gap thật tại `src/api/index.ts:82`, `AdvisorDashboardPage.tsx:51-65`, `StudentDetailPage.tsx`, `EvaluationsPage.tsx:24`. |
| **`AIE`** (`Data-ML-MLOPS` `72c96cd` & LLM) | **14** | **10** | **1** (`ML-11`) | **3** (`ML-12`, `AI-06`, `AI-07`) | **50h** (16h) | `pytest tests/ -q`: **163 passed, 8 skipped**; `verify-release` (`0.810348`, `2014J` `forbidden_prior_consumed`). Đã xác minh gap tại `ml_gate.py:42` (`gender`-only), challenger trên `2014B`, human calibration + red-team, value benchmark. |
| **Toàn Dự án** | **64** | **45** | **3** | **16** | **230h** (**72h**) | 3 repo app giữ `git status` sạch; mọi đường dẫn & số liệu khớp `backlog.csv` 100%. |

---

## 2. Xác minh Các Mốc Mới Đạt `PASS` (2026-11-23)

| Task ID | Hạng mục | Bằng chứng Đạt DoD |
| :--- | :--- | :--- |
| **`CICD-05`** | Push `learnguard-platform` & Xác minh 4/4 GitHub Actions Workflows | Commit `e9f9c81` trên `viethung12062005/learnguard-platform`: `ci-platform.yml`, `ci-build-and-scan.yml` (Trivy `exit-code: 1`, đẩy & ghim 3 immutable `@sha256` digests lên GHCR), `cd-digitalocean-prod.yml`, `mlops-drift-retrain.yml` đều **GREEN**. |
| **`ARC-05`** | Chuẩn hóa Bộ Tài liệu SHP `00-*..06-*`, Dual-Cloud Parity & Agent Harness | Toàn bộ `docs/00-*..06-*` liên thông không gãy link, khóa rõ mô hình **Deploy-Where-Available** (`OPS-06` Option B DigitalOcean VM vs `OPS-08` Option A Azure PaaS — không chạy song song hai cloud). |

---

## 3. Danh mục Kiểm toán Các Khoảng trống Đang Mở (Verified In-Scope Gaps)

| Nhóm | Task IDs | Bằng chứng Khảo sát Code (Code Audit Evidence) | Điều kiện Chuyển sang `PASS` |
| :--- | :--- | :--- | :--- |
| **Cloud & Ops (`MLOPS`)** | `OPS-06` / `OPS-08`, `OPS-07` | Triển khai live **trên cloud khả dụng** (`OPS-06` DO Droplet VM hoặc `OPS-08` Azure PaaS parity tuân thủ `AZURE_CONSTRAINTS.md` cấm `azurerm_role_assignment`). | `smoke-test.sh` xanh trên môi trường live + `check_plan.py` pass + biên bản 5 GameDay Drills (`OPS-07`). |
| **Backend (`SWE1`)** | `BE-08`..`BE-14` | `api/auth.py` (`NotImplementedError`), `observability.py` (`NotImplementedError`), `repository.py:582` (`system@learnguard.local`), `app.py:206` (thiếu `feedback` & `GET .../brief`), `services/briefs.py` (thiếu `advisor_guidelines.md` & guardrails). | `unittest` pass 100% cho JWT Auth, RBAC, real `user_id`, `/metrics`, cache `/activity` `<300ms`, DB `503` tests & `BE-14`. |
| **Frontend (`SWE2`)** | `FE-09`..`FE-13` | `src/api/index.ts:82` (`mock.login`), `EvaluationsPage.tsx:24` (thiếu `behavioral`/drift/cost), `AdvisorDashboardPage.tsx:51-65` (hardcode 5/7 modules & 3/4 presentations), `StudentDetailPage.tsx` (chưa nối Accept/Reject + Feedback). | `tsc --noEmit && vite build`, `node tests/run.mjs` / Vitest & Playwright E2E + a11y pass 100%. |
| **AI/ML (`AIE`)** | `ML-11`, `ML-12`, `AI-06`, `AI-07` | `ml_gate.py:42` mới kiểm `gender` (thiếu 5 slices + `ECE`/calibration + multi-K); chưa có báo cáo FN & `HistGB` + TreeSHAP trên `2014B`; chưa có 30 dual-human golden briefs + Chat red-team; chưa chạy `product-value-protocol.md`. | `learnguard evaluate all` pass 6 slices, `2014J` giữ nguyên `forbidden_prior_consumed`, báo cáo `AI-06` & `AI-07` hoàn tất. |

---

## 4. Nhật ký Đóng Các Lỗ hổng Review Độc lập Trước đó (`C-01..C-04`, `H-01..H-04`)

| Mã Lỗi | Phát hiện & Khắc phục đã Đóng | Bằng chứng Kiểm chứng |
| :--- | :--- | :--- |
| **C-01** | Sửa `init-db.sh` (thêm `features_json`, xóa DDL bảng backend khỏi init để tránh đụng Alembic `db-migrate`, dùng `ALTER DEFAULT PRIVILEGES` cho `lg_api`). | `bash -n` & `--dry-run` exit 0; khớp `entities.py`. |
| **C-02** | Đồng bộ cờ CLI `--mode rollback`, `--target-release-id`, `--cutoff-day`, `force_retrain` giữa `retrain_pipeline.py`, workflow và 3 runbooks. | `pytest tests/test_drift_and_retraining.py` PASS. |
| **C-03** | Dùng step `check_vm` ghi `has_host` vào `$GITHUB_OUTPUT` trong `cd-digitalocean-prod.yml` và `mlops-drift-retrain.yml`. | `yaml.safe_load` & live workflow run GREEN (`e9f9c81`). |
| **C-04** | Tự động format `ext4`, ghi `/etc/fstab` (`nofail`) và mount Block Storage Volume vào `/opt/learnguard/data` trong `cloud-init.yaml` & `bootstrap-vm.sh`. | `bash -n scripts/do/bootstrap-vm.sh` & `--dry-run` exit 0. |
| **H-01..H-04** | Trivy `exit-code: 1`, 5 Nginx security headers trong mọi `location` block, `deploy-do.sh` pipe `GHCR_PAT` qua stdin & `awk`, fail-closed Champion-vs-Challenger & `ASM-03` Delayed Label Guard. | `pytest learnguard-platform/tests -v` (**6 passed**) & CI build GREEN (`e9f9c81`). |
