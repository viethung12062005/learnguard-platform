# ADR-0009 — Pipeline CI/CD Đa Tầng với GitHub Actions, GHCR Immutable Digests và Auto-Rollback trên DigitalOcean

- **Trạng thái:** Accepted
- **Ngày:** 2026-11-23
- **Supersedes:** ADR-0006 (CI/CD self-hosted runner + Azure OIDC).

## 1. Bối cảnh

Khi chuyển sang triển khai trên DigitalOcean Droplet VM, hệ thống cần một quy trình CI/CD hoàn toàn tự động, kiểm chứng được toàn bộ 6 tầng chất lượng của hệ thống AI (theo **CMU MLIP Lec 5 & Lec 6**) trước khi cho phép bản dựng chạm tới môi trường production, đồng thời phải có khả năng tự động quay lui (auto-rollback) nếu bất kỳ kiểm tra hậu triển khai (post-deploy smoke test) nào thất bại.

## 2. Quyết định

Thiết lập hệ thống 4 workflow GitHub Actions chuẩn hóa trong `learnguard-platform/.github/workflows/`:

1. **`ci-platform.yml` (Continuous Integration & 6-Layer System Quality Gate):**
   - Kích hoạt trên mọi `push` và `pull_request`.
   - **Job 1 — Static Analysis & Infrastructure Guardrails:** Kiểm tra cú pháp và bảo mật cho Shell scripts (`shellcheck`), Python (`ruff check`), Docker Compose (`docker compose config`), và Terraform (`terraform fmt -check`, `terraform validate`).
   - **Job 2 — App & ML Unit + Contract Tests:** Chạy bộ kiểm thử của `Data-ML-MLOPS` (`pytest`), `BE-MLOPS` (`unittest`), kiểm thử hợp đồng dữ liệu xuyên biên (`test_system_contracts.py`), và kiểm tra build `FE-MLOPS` (`npm ci && npm run build`).
   - **Job 3 — Behavioral Gate & Drift/Retraining Simulation Gate:** Chạy kiểm thử hành vi mô hình (`test_behavioral_gate.py`: MFT, Invariance, Directional Expectation) và kiểm thử mô phỏng phát hiện drift + tái huấn luyện (`test_drift_and_retraining.py`).

2. **`ci-build-and-scan.yml` (Immutable Container Build, Trivy Security Scan & GHCR Push):**
   - Build 3 Docker images (`learnguard-api`, `learnguard-ml`, `learnguard-fe`) từ commit SHA cố định.
   - Quét lỗ hổng bảo mật container bằng **Trivy** (chặn nếu có lỗ hổng CRITICAL/HIGH chưa được xử lý hoặc cấu hình sai Dockerfile).
   - Đẩy image lên **GitHub Container Registry (`ghcr.io`)** và xuất **immutable digest (`@sha256:...`)**.

3. **`cd-digitalocean-prod.yml` (Production Deployment to DigitalOcean VM with Smoke Test & Auto-Rollback):**
   - Yêu cầu GitHub Environment `production` (hỗ trợ approval gate và environment secrets: `DO_HOST`, `DO_USER`, `DO_SSH_KEY`, `DO_PORT`).
   - Đồng bộ cấu hình `deploy/` và `scripts/cd/` lên `/opt/learnguard` trên Droplet qua SSH/rsync.
   - Kích hoạt `scripts/cd/deploy-do.sh`:
     1. Ghi nhận trạng thái image hiện tại vào `last_good_release.env`.
     2. Chạy `backup-db.sh` tạo bản sao lưu PostgreSQL trước khi nâng cấp.
     3. Chạy container migration (`db-migrate`) đảm bảo schema và least-privilege roles (`lg_api`, `lg_ml_writer`).
     4. Cập nhật `api` và `frontend` theo digest mới, chờ Docker healthcheck báo `healthy`.
     5. Chạy `smoke-test.sh` kiểm tra toàn diện `/health`, `/predictions`, `/predictions/stats`, `/evaluations`, `/audit-logs`, SPA deep-link `/review` và security headers.
     6. **Auto-Rollback:** Nếu bất kỳ bước nào ở (4) hoặc (5) thất bại, `deploy-do.sh` tự động gọi `rollback-do.sh` khôi phục đúng bộ image trong `last_good_release.env` và kiểm tra lại sức khỏe hệ thống.

4. **`mlops-drift-retrain.yml` (Automated / Scheduled Drift Monitoring & Continual Retraining Pipeline):**
   - Chạy định kỳ theo lịch (`schedule` hàng tuần) hoặc kích hoạt thủ công (`workflow_dispatch` với tham số chọn kịch bản drift / force-retrain).
   - Thực thi `retrain_pipeline.py`, lưu trữ toàn bộ báo cáo `drift-report.v1` và `eval-report.v1` làm GitHub Actions Workflow Artifacts, và nếu chạy trên VM production thì tự động cập nhật `active_release.json` + bảng `ml_predictions` khi Challenger vượt qua toàn bộ cổng kiểm định.

## 3. Hệ quả

- Đảm bảo không một bản sửa đổi code hay model nào lên production mà chưa qua kiểm thử hợp đồng, kiểm thử hành vi và quét bảo mật.
- Thời gian khôi phục sự cố (MTTR) khi deploy lỗi giảm xuống dưới 60 giây nhờ cơ chế `last_good_release.env` + `rollback-do.sh`.
