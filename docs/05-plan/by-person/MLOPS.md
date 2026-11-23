# Kế hoạch Công việc Chi tiết: MLOPS — MLOps + DevOps + Solution Architect

> **Vai trò:** Chủ sở hữu `learnguard-platform`, Kiến trúc sư hệ thống (Solution Architect), Quản trị CI/CD & Động cơ Drift/Retraining.
> **Kho mã nguồn chính:** `learnguard-platform` (toàn quyền) + Quản trị nhánh `main` và PR Review trên cả 4 repo.
> **Chiến lược Cloud-Portable (Deploy-Where-Available):** `OPS-06` (DigitalOcean Droplet VM — Option B) và `OPS-08` (Azure PaaS — Option A) là **hai phương án hạ tầng thay thế tương đương**. Nhóm duy trì IaC & CI/CD sẵn sàng cho cả hai, và triển khai live lên **nhà cung cấp cloud nào hiện khả dụng** (không chạy hay trả phí song song cả hai cloud cùng lúc).

**Định nghĩa Hoàn thành (DoD):** Script pass `bash -n` & `--dry-run`, Python pass `ruff check` & `pytest`, YAML pass `yaml.safe_load`, Terraform pass `validate` & `check_plan.py`, không lộ secret, có runbook và bằng chứng ghi trong [dod-audit.md](../dod-audit.md).

Tổng cộng (**khớp 100% [backlog.csv](../backlog.csv)**): **23 tasks (84 giờ)**. Đã hoàn thành: **20 tasks (`☑`, 72 giờ)** · Đang làm: **0 tasks** · Cần làm tiếp: **3 tasks (`☐`, 12 giờ)**.

---

## Giai đoạn 1 — Kiến trúc, Quy chuẩn CMU MLIP & Chuẩn hóa Tài liệu (20 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `ARC-01` | Thiết lập Quy chuẩn SE, DevOps & MLOps theo giáo trình CMU MLIP (Lec 1–6) | [00-conventions.md](../../00-conventions.md) đầy đủ 4 Boundaries, `ASM ∧ SPEC => REQ`, Success Portfolio, 6-Clause Data Contract, 3 Control Points, Tháp test 6 tầng. | 4 | — | `ENABLER` / `CMU-MLIP` |
| ☑ | `ARC-02` | Thiết kế Kiến trúc Đích v3 trên DigitalOcean VM & ADR 0008–0010 | [digitalocean-target-architecture.md](../../03-architecture/digitalocean-target-architecture.md) + ADR `0008`–`0010` trạng thái `Accepted`; sơ đồ C4 & Sequence rõ ràng. | 4 | `ARC-01` | `ENABLER` / `ADR-0008..0010` |
| ☑ | `ARC-03` | Đặc tả Kỹ thuật Phát hiện Drift, Chẩn đoán Triage & Continual Retraining | [drift-and-retraining-specification.md](../../03-architecture/drift-and-retraining-specification.md) định nghĩa 5 loại drift, PSI/KS, Semantic Guard `10x`, `ASM-03`, Behavioral Gate & 5 kịch bản. | 4 | `ARC-02` | `US-14` / `NFR-MLO1` |
| ☑ | `ARC-04` | Chuẩn hóa Quy trình Giao nhận, Nhánh/PR, Ma trận Truy vết & Kế hoạch 4 Thành viên | [00-delivery-process.md](../../00-delivery-process.md), [00-workflow.md](../../00-workflow.md), [traceability.md](../../02-requirements/traceability.md), [project-plan.md](../project-plan.md), `by-person/*.md`, `backlog.csv`, `dod-audit.md`. | 4 | `ARC-02` | `ENABLER` / `GOV` |
| ☑ | `ARC-05` | Chuẩn hóa Bộ Tài liệu SHP `00-*..06-*`, Dual-Cloud Parity & Agent Harness Profile | Toàn bộ cấu trúc `docs/00-*..06-*` liên thông không gãy link, khóa parity Dual-Cloud Option A + Option B và profile `learnguard` trong `agent-harness`. | 4 | `ARC-04` | `ENABLER` / `GOV` |

---

## Giai đoạn 2 — Hạ tầng Cloud, Docker Production Stack & Bảo mật DB (22 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `OPS-01` | Xây dựng Multi-stage Dockerfiles (`Dockerfile.api`, `Dockerfile.ml`, `Dockerfile.fe`) & `nginx.fe.conf` | Cả 3 image chạy non-root (`UID 10001`), có `HEALTHCHECK`, Nginx rate-limit `20r/s`, SPA fallback và đủ 5 security headers ở mọi `location`. | 4 | `ARC-02` | `ENABLER` / `NFR-SEC1` |
| ☑ | `OPS-02` | Thiết lập `init-db.sh` & `roles.sql` phân tách 2 role PostgreSQL (`lg_api` vs `lg_ml_writer`) | `ml_predictions` có `features_json`; `lg_ml_writer` sở hữu `ml_predictions`; `lg_api` chỉ `SELECT` trên `ml_predictions` và nhận `ALTER DEFAULT PRIVILEGES`. | 4 | `ARC-02` | `US-12` / `FR-09` |
| ☑ | `OPS-03` | Cấu hình `docker-compose.prod.yml` & `docker-compose.staging.yml` với 2 mạng cô lập | `lg_frontend_net` tách biệt khỏi `lg_backend_net` (`internal: true`); PostgreSQL không mở cổng host; chia sẻ volume `evaluations` & `oulad`. | 4 | `OPS-01`, `OPS-02` | `ENABLER` / `NFR-SEC1` |
| ☑ | `OPS-04` | Viết Terraform DigitalOcean (`infra/digitalocean/`) & script `bootstrap-vm.sh` | Tạo VPC, Droplet Ubuntu 24.04, Cloud Firewall, tự động format/mount Block Storage Volume vào `/opt/learnguard/data`, cài systemd timer. | 4 | `ARC-02` | `ENABLER` / `NFR-OPS1` |
| ☑ | `OPS-05` | Xây dựng bộ script CD, Backup/Restore & Auto-Rollback | `deploy-do.sh`, `smoke-test.sh`, `rollback-do.sh`, `backup-db.sh`, `restore-db.sh` pass `bash -n` và `--dry-run`; auto-rollback khi smoke fail. | 6 | `OPS-03` | `ENABLER` / `NFR-OPS1` |

---

## Giai đoạn 3 — Động cơ Drift, Mô phỏng Dữ liệu & Continual Retraining (20 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `MLO-01` | Xây dựng `drift_monitor.py` (`drift-report.v1`) với Triage 4 chiều & `ASM-03` Guard | Đo PSI, KS (`0.15`), Semantic `10x`, Missingness, Volume, Slice PSI; chặn retrain khi dữ liệu lỗi ngữ nghĩa hoặc chưa có nhãn (`ASM-03`). | 5 | `ARC-03` | `US-14` / `NFR-MLO1` |
| ☑ | `MLO-02` | Xây dựng Cổng Kiểm thử Hành vi `behavioral_gate.py` (`eval_behavioral.json`) | Kiểm tra 6 tiêu chí: `MFT` (`>= 0.25`), `Row Permutation Invariance`, `Pseudonymous Key Invariance`, `Clicks/Score Directional`, `Abstention`. | 4 | `ARC-03` | `US-15` / `NFR-ML3` |
| ☑ | `MLO-03` | Xây dựng Bộ Mô phỏng Dữ liệu Mới & 5 Kịch bản Drift (`data_simulator.py`) | Sinh OULAD 7 bảng CSV deterministic (`>= 250` dòng/split) cho 5 kịch bản chuẩn. | 4 | `MLO-01` | `US-14` / `NFR-MLO1` |
| ☑ | `MLO-04` | Xây dựng Orchestrator `retrain_pipeline.py` (Champion vs Challenger + `--mode rollback`) | Điều phối `M1→M5` + 3 cổng gate + `active_release.json`; fail-closed khi lỗi so sánh Champion; hỗ trợ `--mode rollback`. | 4 | `MLO-01`, `MLO-02`, `MLO-03` | `US-14` / `NFR-MLO2` |
| ☑ | `MLO-05` | Viết bộ kiểm thử tự động nền tảng (`learnguard-platform/tests/`) | `pytest learnguard-platform/tests -v` pass 100% (kèm negative test broken model, `ASM-03`, `--mode rollback`, FastAPI integration). | 3 | `MLO-04` | `US-14` / `NFR-MLO2` |

---

## Giai đoạn 4 — CI/CD Verified, Dual-Cloud Deployment (Deploy-Where-Available) & GameDay (22 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `CICD-01` | Thiết lập `ci-platform.yml` | Pass `bash -n`, `ruff check`, YAML, `docker compose config` & toàn bộ `pytest`. | 2 | `MLO-05`, `OPS-05` | `ENABLER` / `NFR-OPS1` |
| ☑ | `CICD-02` | Thiết lập `ci-build-and-scan.yml` | Build `api`/`ml`/`fe` từ SHA cố định, Trivy `exit-code: 1`, push GHCR `@sha256`. | 2 | `OPS-01` | `ENABLER` / `NFR-OPS1` |
| ☑ | `CICD-03` | Thiết lập `cd-digitalocean-prod.yml` & `mlops-drift-retrain.yml` | Step `check_vm` hợp lệ, safe stdin docker login, simulation artifacts upload & SSH deploy. | 2 | `CICD-01`, `CICD-02` | `ENABLER` / `NFR-OPS1` |
| ☑ | `CICD-04` | Viết 3 Runbooks Vận hành Production | `deploy-digitalocean.md`, `incident-and-rollback.md`, `drift-and-retraining-runbook.md` khớp CLI & kiến trúc. | 2 | `CICD-03` | `ENABLER` / `NFR-OPS1` |
| ☑ | `CICD-05` | Push `learnguard-platform` & Xác minh Live GitHub Actions Workflows | Đã xác minh tại commit `e9f9c81`: **4/4 GitHub Actions workflows GREEN** & 3 digest `@sha256` GHCR ghim trong `prod.yaml`. | 2 | `CICD-04` | `ENABLER` / `NFR-OPS1` |
| ☐ | `OPS-06` | **Option B — DigitalOcean VM Live Deployment & Smoke Test (Deploy-Where-Available)** | Khi chọn track DigitalOcean: provision Droplet VM, nạp GitHub Environment `production` secrets (`DO_HOST`/`DO_SSH_KEY`), chạy `cd-digitalocean-prod.yml` và `smoke-test.sh` pass 100%. | 4 | `CICD-05` | `ENABLER` / `NFR-OPS1` |
| ☐ | `OPS-07` | **Diễn tập Safeguard, Fault-Injection, DB Restore & Model Rollback (GameDay Drills)** | Thực hiện trên môi trường cloud live đã chọn (DO VM hoặc Azure): kiểm chứng rollback container (`<= 60s`), `retrain_pipeline.py --mode rollback`, `restore-db.sh` và ghi biên bản vào `docs/06-testing/`. | 4 | `OPS-06` | `US-11` / `FR-08` |
| ☐ | `OPS-08` | **Option A — Azure PaaS Parity & Guardrail Verification (Deploy-Where-Available)** | Duy trì khả năng triển khai sang Azure Container Apps: `infra/env/dev` pass `terraform validate` / `terraform plan` + `check_plan.py` (tuân thủ [AZURE_CONSTRAINTS.md](../../memory/AZURE_CONSTRAINTS.md), **0 `azurerm_role_assignment`**) và đồng bộ `cd-dev-*.yml`. | 4 | `CICD-05` | `ENABLER` / `NFR-OPS1` |
