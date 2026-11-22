# PROGRESS — Tiến độ LearnGuard Platform

> File "kiến thức" → không commit vào `learnguard-platform`. Cập nhật **2026-11-23**.

## Trạng thái tổng

| Giai đoạn | Hạng mục | Trạng thái |
|---|---|---|
| **Phase 0 (2026-11-04)** | App facts, Azure discovery, Requirements/NFR, Threat model, Production readiness gap register | ✅ Hoàn tất |
| **Phase 1 (2026-11-04)** | Kiến trúc v2 trên Azure (Terraform `infra/bootstrap`, `infra/env/dev`, guardrails, CD dev workflows) | 📦 Superseded cho mục tiêu prod mới bởi ADR-0008 & ADR-0009 |
| **Phase 2 (2026-11-23)** | Chuyển dịch Production sang DigitalOcean VM + Bộ quy chuẩn CMU MLIP + Pipeline Drift/Retraining | 🔄 Đang hoàn thiện kiến trúc, tài liệu & triển khai |

---

## Phase 2 — DigitalOcean Production Migration & CMU MLIP MLOps (2026-11-23)

### 1. Quy chuẩn Kỹ thuật & Kiến trúc (Docs & ADRs)

| Hạng mục | Trạng thái | Tài liệu tham chiếu |
|---|---|---|
| Bộ quy chuẩn Kỹ thuật Phần mềm, DevOps & MLOps (CMU MLIP Lec 1–6) | ✅ Hoàn tất | `docs/conventions/software-engineering-and-mlops-conventions.md` |
| ADR-0008: Chuyển dịch hạ tầng đích sang DigitalOcean Droplet VM | ✅ Accepted (`D-018`) | `docs/adr/0008-cloud-migration-digitalocean-vm.md` |
| ADR-0009: Pipeline CI/CD đa tầng GHCR `@sha256` + Auto-Rollback | ✅ Accepted (`D-020`) | `docs/adr/0009-cicd-pipeline-digitalocean-ghcr.md` |
| ADR-0010: Drift Detection, Triage & Continual Retraining (Champion vs. Challenger) | ✅ Accepted (`D-021`) | `docs/adr/0010-drift-detection-and-continual-retraining-pipeline.md` |
| Production Readiness Gap Register (v3 — nâng điểm like-production lên `9.2/10`) | ✅ Cập nhật | `docs/architecture/production-readiness-gap.md` |
| Memory & Context (`PROJECT_CONTEXT.md`, `DECISIONS.md`, `OPEN_QUESTIONS.md`, `SESSION_LOG.md`) | ✅ Cập nhật | `PROJECT_CONTEXT.md`, `docs/memory/` |

### 2. Kiến trúc Triển khai & Pipeline MLOps Đích (Phase 2 Scope)

| Hạng mục | Mô tả thiết kế đã chốt | Trạng thái theo dõi |
|---|---|---|
| **DigitalOcean IaC & Host Hardening** | Terraform `infra/digitalocean/` (Droplet Ubuntu 24.04 LTS, VPC, Cloud Firewall chỉ mở 80/443 & SSH giới hạn) | Thiết kế & triển khai theo ADR-0008 |
| **Docker Compose Production Stack** | `docker-compose.prod.yml` tách `lg_frontend_net` & `lg_backend_net` (`internal: true`), Nginx reverse proxy + rate limiting + security headers, `postgres:16-alpine` với 2 role (`lg_api`, `lg_ml_writer`), `db-migrate`, shared volume `/opt/learnguard/data`, Prometheus + Node Exporter + cAdvisor | Thiết kế & triển khai theo ADR-0008 |
| **GitHub Actions CI/CD + GHCR** | 4 workflows: `ci-platform.yml`, `ci-build-and-scan.yml` (Trivy + GHCR `@sha256`), `cd-digitalocean-prod.yml` (`backup-db.sh` → `db-migrate` → deploy → `smoke-test.sh` → `rollback-do.sh`), `mlops-drift-retrain.yml` | Thiết kế & triển khai theo ADR-0009 |
| **Drift Detection, Simulation & Retraining** | `deploy/ml/drift_monitor.py`, `data_simulator.py` (5 kịch bản), `behavioral_gate.py` (MFT, Invariance, Directional), `retrain_pipeline.py` (Champion vs. Challenger + `active_release.json`) | Thiết kế & triển khai theo ADR-0010 |

### 3. Đồng bộ Upstream App Repos (Snapshot 2026-11-23)

| Repo | Commit SHA | Thay đổi nổi bật |
|---|---|---|
| `ntk223/BE-MLOPS` | `a2bae92` | Bổ sung `/evaluations`, `/evaluations/run`, `/evaluations/run-status`, `/evaluations/{run_id}`, `/briefs/*`, `/briefs/chat/*`, `/audit-logs`, `/predictions/.../activity` |
| `ntk223/Data-ML-MLOPS` | `72c96cd` | Bổ sung `learnguard evaluate {data, ml, llm, all}` xuất `eval-report.v1`, `explain-shap`, `benchmark`, `create-release`, `verify-release` |
| `ntk223/FE-MLOPS` | `0f70e14` | Bổ sung trang `/evaluations`, `/audit`, `/overview`, brief chatbot, role-based guard (`admin`/`advisor`) và test runner `node tests/run.mjs` |

---

## Việc tiếp theo (Next Steps)

1. Provision hạ tầng DigitalOcean (`infra/digitalocean/`: `terraform init && terraform plan && terraform apply`) và lấy Droplet IP.
2. Tạo SSH deploy key riêng và cấu hình secrets trong GitHub Environment `production` (`DO_HOST`, `DO_USER`, `DO_SSH_KEY`, `DO_PORT`) cùng `GHCR` permissions.
3. Chạy kiểm chứng toàn bộ CI (`ci-platform.yml`, `ci-build-and-scan.yml`) và chạy thử CD đầu tiên (`cd-digitalocean-prod.yml`) kèm verify `smoke-test.sh`, `backup-db.sh` / `restore-db.sh` và `rollback-do.sh`.
4. Chạy `mlops-drift-retrain.yml` với 5 kịch bản mô phỏng để xác nhận scorecard `eval-report.v1` và `drift-report.v1` hiển thị đúng trên Dashboard `/evaluations`.

---

<details>
<summary>Lịch sử Phase 0–1 (Azure Container Apps — 2026-11-04, đã lưu trữ)</summary>

- User `HungTV88@fpt.com`, sub `FSO-SB-GHCHCS-OJT-DEV`, region `southeastasia`, Role `FSO-SandboxOps`.
- Đã viết `infra/bootstrap/`, `infra/modules/*`, `infra/env/dev/`, `scripts/guardrails/check_plan.py`, `cd-dev-*.yml`.
- `terraform validate` & `terraform plan` (39 resources) pass ngày 2026-11-04; chuyển hướng sang DigitalOcean VM từ 2026-11-23 (ADR-0008).

</details>
