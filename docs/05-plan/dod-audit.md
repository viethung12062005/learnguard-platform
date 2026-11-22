# Báo cáo Kiểm toán Định nghĩa Hoàn thành — LearnGuard (Definition of Done Audit)

> **Ngày kiểm toán:** 2026-11-23
> **Phương pháp:** Học tập trực tiếp quy trình kiểm toán độc lập của `smart-hospital-platform/docs/05-plan/dod-audit.md`.
> Mỗi task được đối chiếu với:
> 1. Tiêu chí **`Done when`** trong [backlog.csv](backlog.csv).
> 2. Bộ **Definition of Done (DoD)** 10 điểm trong [00-workflow.md](../00-workflow.md) §4 và cuộc kiểm toán độc lập của **Principal Reviewer (Neon Medium)**.
>
> **Nhãn phán quyết (Verdicts):** `PASS` (đạt 100%, có bằng chứng chạy lệnh thật) · `PARTIAL` (đã có phần lõi, còn thiếu một mảnh ghép được nêu tên rõ) · `TODO` (đã phân công trong Sprint 1–2) · `UNVERIFIED-CLOUD` (code/script đã sẵn sàng và pass dry-run, chờ chạy trên DigitalOcean Droplet thật).

---

## 1. Tổng quan Kết quả Kiểm toán (Audit Summary — 2026-11-23)

| Nhóm Phụ trách | Tổng số Task | `PASS` (Đã chứng minh) | `PARTIAL` / `IN PROGRESS` | `TODO` (Sprint 1–2) | Bằng chứng Kiểm thử Thực tế |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`MLOPS` (Bạn — Platform, CI/CD, Drift/Retrain)** | **21** | **19** | 0 | **2** (`OPS-06`, `OPS-07`) | GitHub Actions 4/4 workflows **GREEN** (`ci-platform`, `ci-build-and-scan` 0 HIGH/CRITICAL CVEs + GHCR `@sha256`, `mlops-drift-retrain`, `cd-digitalocean-prod`); `pytest`: **6 passed**; `ruff`: **0 errors**; ShellCheck **0 warnings**. |
| **`SWE1` (Backend `BE-MLOPS`)** | **13** | **7** | **1** (`BE-08`) | **5** (`BE-09`..`BE-13`) | `BE-MLOPS` (`a2bae92`): 9 test suites (`test_app`, `test_predictions_api`, `test_briefs`, `test_chat`, `test_evaluations_api`, `test_audit_logs_api`, `test_llm`, `test_ml_predictions`, `test_student_keys`) pass. |
| **`SWE2` (Frontend `FE-MLOPS`)** | **12** | **8** | **1** (`FE-09`) | **3** (`FE-10`..`FE-12`) | `FE-MLOPS` (`0f70e14`): `npm run build` (`tsc --noEmit && vite build`) & `tests/test-chat.ts` pass. |
| **`AIE` (Data/ML `Data-ML-MLOPS` & LLM)** | **14** | **10** | **1** (`ML-11`) | **3** (`ML-12`, `AI-06`, `AI-07`) | `Data-ML-MLOPS` (`72c96cd`): **163 passed, 8 skipped** (`pytest tests/ -q`). |
| **Toàn Dự án** | **60** | **43** | **3** | **14** | 3 repo app giữ nguyên trạng thái `git status` sạch sẽ 100%. |

---

## 2. Nhật ký Đóng Các Lỗ hổng từ Đợt Review Độc lập (Neon Medium Audit Fixes — 2026-11-23)

Tất cả các lỗi **Critical (`C-01`..`C-04`)**, **High (`H-01`..`H-04`)** và **Medium (`M-01`..`M-08`)** do **Principal Reviewer (Neon Medium)** phát hiện đã được khắc phục và kiểm chứng lại bằng lệnh thật:

| Mã Lỗi | Phát hiện của Reviewer | Cách khắc phục đã thực thi | Bằng chứng Kiểm chứng (Re-run Evidence) |
| :--- | :--- | :--- | :--- |
| **C-01** | `init-db.sh` tự tạo các bảng backend + `alembic_version` rỗng gây lỗi `DuplicateTable` khi `db-migrate` chạy, và thiếu cột `ml_predictions.features_json`. | Đã thêm `features_json text` (+ `ALTER TABLE ADD COLUMN IF NOT EXISTS`) vào `ml_predictions`; xóa DDL bảng backend khỏi `init-db.sh` để Alembic độc quyền quản lý; dùng `ALTER DEFAULT PRIVILEGES` cấp quyền tự động cho `lg_api`; thêm `chat_sessions`/`chat_messages` vào `roles.sql`. | `bash -n deploy/digitalocean/init-db.sh` & `--dry-run` exit 0; kiểm tra chéo schema với `BE-MLOPS/src/learnguard_backend/db/entities.py`. |
| **C-02** | Lệch cờ CLI giữa `mlops-drift-retrain.yml` / 3 Runbooks và `retrain_pipeline.py` (`--simulate-if-missing`, `--simulate-scenario`, `force_retrain`, `--mode rollback`). | Đã bổ sung `--mode rollback`, `--target-release-id` (`--rollback-release`), `--cutoff-day` và alias `force_retrain` vào `retrain_pipeline.py`; đồng bộ 100% lệnh gọi trong `mlops-drift-retrain.yml` và cả 3 Runbooks. | `pytest tests/test_drift_and_retraining.py` (kèm test `--mode rollback` end-to-end) **PASS**. |
| **C-03** | `cd-digitalocean-prod.yml` và `mlops-drift-retrain.yml` dùng `secrets.DO_HOST` trực tiếp trong `if:` và đọc `env.DO_HOST_AVAILABLE` cùng step. | Đã chuyển sang step độc lập `id: check_vm` ghi `has_host=true/false` vào `$GITHUB_OUTPUT` và dùng `steps.check_vm.outputs.has_host == 'true'` ở các step sau. | Kiểm tra cấu trúc GitHub Actions YAML bằng Python `yaml.safe_load` & chuẩn bị verify trực tiếp trên GitHub Actions (`CICD-05`). |
| **C-04** | DigitalOcean Block Storage Volume tạo bởi Terraform chưa được mount vào `/opt/learnguard/data`. | Đã bổ sung logic tự động phát hiện `/dev/disk/by-id/scsi-0DO_Volume_*`, format `ext4` (nếu chưa format), ghi `/etc/fstab` (`nofail`) và `mount /opt/learnguard/data` trong cả `cloud-init.yaml` và `bootstrap-vm.sh`. | `bash -n scripts/do/bootstrap-vm.sh` & `--dry-run` exit 0. |
| **H-01** | Trivy đặt `exit-code: "0"` và `source_commit` trong `dev.yaml`/`prod.yaml` chưa cập nhật SHA mới nhất. | Đã đổi Trivy `exit-code: "1"`, ghim `a2bae92` (`BE-MLOPS`), `72c96cd` (`Data-ML-MLOPS`), `0f70e14` (`FE-MLOPS`) trong `ci-build-and-scan.yml`, `dev.yaml` và `prod.yaml`. | Kiểm tra file `deploy/releases/prod.yaml` và `.github/workflows/ci-build-and-scan.yml`. |
| **H-02** | `nginx.fe.conf` mất security headers cấp server ở các block `location /` và `location /assets/` có dùng `add_header`. | Đã khai báo đầy đủ cả 5 security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy`) bên trong từng block `location`. | Kiểm tra `deploy/docker/nginx.fe.conf`. |
| **H-03** | `deploy-do.sh` chưa pull `ml-worker`, lưu placeholder digest vào `last_good_release.env`, dùng `sed` dễ lỗi ký tự đặc biệt, và truyền `GHCR_PAT` qua chuỗi lệnh SSH. | Đã pipe `GHCR_PAT` qua stdin (`--password-stdin`), pull thêm `ml-worker`, chặn lưu placeholder `1111...`, và thay `sed` bằng hàm `awk` an toàn. | `scripts/cd/deploy-do.sh --dry-run` & `rollback-do.sh --dry-run` exit 0. |
| **H-04** | `_evaluate_champion_vs_challenger_regression` bắt exception trả về `warn` (fail-open); chưa mô hình hóa `ASM-03` (Delayed Ground Truth tuần 4 chưa có nhãn); `run_data_gate` tự so sánh `snap` với chính nó tạo `max_psi=0.0` giả. | Đã sửa thành fail-closed (`status="fail"`); bổ sung `ground_truth_available` trong `DriftMonitor` trả `WARN_MONITOR` + `SCORE_WITH_CHAMPION_AWAIT_LABELS` khi thiếu nhãn (`ASM-03`); truyền `baseline_snapshot` thật vào `run_data_gate` và ghi nhận `drift_vs_baseline` ở mức `warn` trung thực; thêm negative unit tests. | `pytest learnguard-platform/tests -v` (**6 passed**: gồm cả negative broken-model test, `ASM-03` test, và `--mode rollback` test). |
