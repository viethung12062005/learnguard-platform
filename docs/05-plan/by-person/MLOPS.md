# Kế hoạch Công việc Chi tiết: MLOPS — MLOps + DevOps + Solution Architect (Bạn)

> **Vai trò:** Chủ sở hữu hạ tầng `learnguard-platform`, Kiến trúc sư hệ thống (Solution Architect), Quản trị CI/CD & Động cơ Drift/Retraining.
> **Kho mã nguồn chính:** `learnguard-platform` (toàn quyền) + Quản trị nhánh `main` và PR Review trên cả 4 repo.
> **Quy ước nhánh & PR:** `<TASK-ID>-short-description` (ví dụ: `CICD-05-github-live-verification`).

**Định nghĩa Hoàn thành (DoD) cho mọi Task:** Script pass `bash -n` & `--dry-run`, Python pass `ruff check` & `pytest`, YAML pass `yaml.safe_load`, không lộ secret, có runbook và bằng chứng ghi trong [dod-audit.md](../dod-audit.md).

Tổng cộng: **21 tasks (80 giờ)**. Đã hoàn thành: **18 tasks (`☑`)**, Cần làm tiếp: **3 tasks (`☐`, ~10 giờ)**.

---

## Giai đoạn 1 — Kiến trúc, Quy chuẩn CMU MLIP & Hợp đồng Hệ thống (16 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `ARC-01` | Thiết lập Quy chuẩn SE, DevOps & MLOps theo giáo trình CMU MLIP (Lec 1–6) | Tài liệu `docs/conventions/software-engineering-and-mlops-conventions.md` đầy đủ 4 Boundaries, `ASM ∧ SPEC => REQ`, Success Portfolio, 6-Clause Data Contract, 3 Control Points, Tháp test 6 tầng. | 4 | — | `ENABLER` |
| ☑ | `ARC-02` | Thiết kế Kiến trúc Đích v3 trên DigitalOcean VM & ADR 0008–0010 | `digitalocean-target-architecture.md` + `ADR-0008`, `ADR-0009`, `ADR-0010` trạng thái `Accepted`; sơ đồ C4 & Sequence rõ ràng. | 4 | `ARC-01` | `ENABLER` |
| ☑ | `ARC-03` | Đặc tả Kỹ thuật Phát hiện Drift, Chẩn đoán Triage & Continual Retraining | `drift-and-retraining-specification.md` định nghĩa rõ 5 loại drift, công thức PSI/KS, ngưỡng Semantic Guard `10x`, `ASM-03` Delayed Label, Behavioral Gate & 5 kịch bản mô phỏng. | 4 | `ARC-02` | `FR-08`, `NFR-MLO1` |
| ☑ | `ARC-04` | Chuẩn hóa Quy trình Giao nhận, Nhánh/PR, Ma trận Truy vết & Kế hoạch 4 Thành viên | `00-delivery-process.md`, `00-workflow.md`, `02-requirements/traceability.md`, `05-plan/project-plan.md`, `by-person/*.md`, `backlog.csv`, `dod-audit.md` hoàn chỉnh theo chuẩn SHP. | 4 | `ARC-02` | `ENABLER` |

---

## Giai đoạn 2 — Hạ tầng DigitalOcean, Docker Production Stack & Bảo mật DB (22 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `OPS-01` | Xây dựng Multi-stage Dockerfiles (`Dockerfile.api`, `Dockerfile.ml`, `Dockerfile.fe`) & `nginx.fe.conf` | Cả 3 image chạy non-root (`UID 10001`), có `HEALTHCHECK`, Nginx cấu hình rate-limit `20r/s`, SPA fallback và giữ nguyên 5 security headers ở mọi location block. | 4 | `ARC-02` | `NFR-SEC1` |
| ☑ | `OPS-02` | Thiết lập `init-db.sh` & `roles.sql` phân tách 2 role PostgreSQL (`lg_api` vs `lg_ml_writer`) | `ml_predictions` có đủ 17 cột (kèm `features_json`); `lg_ml_writer` sở hữu `ml_predictions`; `lg_api` chỉ `SELECT` trên `ml_predictions` và nhận `ALTER DEFAULT PRIVILEGES` cho bảng Alembic tạo. | 4 | `ARC-02` | `FR-09`, `NFR-SEC1` |
| ☑ | `OPS-03` | Cấu hình `docker-compose.prod.yml` & `docker-compose.staging.yml` với 2 mạng cô lập | `lg_frontend_net` (DMZ) tách biệt khỏi `lg_backend_net` (`internal: true`); PostgreSQL không mở cổng ra host; chia sẻ volume `evaluations` và `oulad` đúng quyền RW/RO. | 4 | `OPS-01`, `OPS-02` | `NFR-SEC1` |
| ☑ | `OPS-04` | Viết Terraform DigitalOcean (`infra/digitalocean/`) & script `bootstrap-vm.sh` | Tạo VPC, Droplet Ubuntu 24.04, Cloud Firewall (chặn 5432/8000 public), tự động format & mount Block Storage Volume vào `/opt/learnguard/data`, cài systemd timer. | 4 | `ARC-02` | `NFR-OPS1` |
| ☑ | `OPS-05` | Xây dựng bộ script CD, Backup/Restore & Auto-Rollback (`deploy-do.sh`, `smoke-test.sh`, `rollback-do.sh`, `backup-db.sh`, `restore-db.sh`) | Tất cả script pass `bash -n` và `--dry-run`; `backup-db.sh` ghi atomic `.tmp`; `deploy-do.sh` tự động gọi `rollback-do.sh` khi healthcheck hoặc smoke test lỗi. | 6 | `OPS-03` | `FR-08`, `NFR-OPS1` |

---

## Giai đoạn 3 — Động cơ Phát hiện Drift, Mô phỏng Dữ liệu & Continual Retraining (20 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `MLO-01` | Xây dựng `drift_monitor.py` (`drift-report.v1`) với Triage 4 chiều & `ASM-03` Delayed Label Guard | Đo PSI, KS-test (`0.15`), Semantic Scale (`10x`), Missingness, Volume, Slice PSI; chặn retrain khi dữ liệu lỗi ngữ nghĩa hoặc chưa có nhãn cuối kỳ (`ASM-03`). | 5 | `ARC-03` | `NFR-MLO1` |
| ☑ | `MLO-02` | Xây dựng Cổng Kiểm thử Hành vi `behavioral_gate.py` (`eval_behavioral.json` theo Lec 5) | Kiểm tra 6 tiêu chí: `MFT` (gap `>= 0.25`), `Row Permutation Invariance`, `Pseudonymous Key Invariance`, `Clicks Directional`, `Score Directional`, `Abstention Routing`. | 4 | `ARC-03` | `NFR-ML3` |
| ☑ | `MLO-03` | Xây dựng Bộ Mô phỏng Dữ liệu Mới & 5 Kịch bản Drift (`data_simulator.py`) | Sinh dữ liệu OULAD 7 bảng CSV deterministic (`>= 250` dòng/split) cho 5 kịch bản: `baseline_no_drift`, `gradual_covariate_drift`, `new_semester_cohort`, `corrupted_feed_quarantine`, `rejected_challenger_guard`. | 4 | `MLO-01` | `NFR-MLO1` |
| ☑ | `MLO-04` | Xây dựng Orchestrator `retrain_pipeline.py` (Champion vs. Challenger + `--mode rollback`) | Điều phối `M1→M3 → DriftMonitor → M4 → 3-Layer Gates → Immutable Release → active_release.json → M5`; fail-closed khi lỗi so sánh Champion; hỗ trợ `--mode rollback`. | 4 | `MLO-01`, `MLO-02`, `MLO-03` | `NFR-MLO2` |
| ☑ | `MLO-05` | Viết bộ kiểm thử tự động `tests/test_drift_and_retraining.py`, `test_behavioral_gate.py`, `test_system_contracts.py` | `pytest learnguard-platform/tests -v` pass 100% (gồm cả negative test cho broken model, test `ASM-03`, test `--mode rollback` và FastAPI `/evaluations` integration). | 3 | `MLO-04` | `NFR-ML3`, `NFR-MLO2` |

---

## Giai đoạn 4 — GitHub Actions CI/CD, Runbooks & Triển khai Thực tế lên Cloud (18 giờ)

| ✓ | ID | Công việc (Work) | Điều kiện hoàn thành (Done when) | Giờ | Phụ thuộc | Story / Req |
| :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| ☑ | `CICD-01` | Thiết lập workflow `ci-platform.yml` (Lint, Compose Validate, 6-Layer System & Drift Tests) | Chạy tự động trên mọi push/PR; kiểm tra `bash -n`, `ruff check`, YAML, `docker compose config` và toàn bộ `pytest`. | 2 | `MLO-05`, `OPS-05` | `NFR-OPS1` |
| ☑ | `CICD-02` | Thiết lập workflow `ci-build-and-scan.yml` (Build 3 Images, Trivy `exit-code: 1`, Push GHCR `@sha256`) | Build `api`, `ml`, `fe` từ commit SHA cố định (`a2bae92`, `72c96cd`, `0f70e14`), quét Trivy chặn lỗ hổng High/Critical, xuất digest. | 2 | `OPS-01` | `NFR-OPS1` |
| ☑ | `CICD-03` | Thiết lập workflow `cd-digitalocean-prod.yml` & `mlops-drift-retrain.yml` | Sử dụng step `check_vm` hợp lệ (`steps.check_vm.outputs.has_host`); hỗ trợ chạy simulation trên CI và deploy/retrain qua SSH trên DigitalOcean VM. | 2 | `CICD-01`, `CICD-02` | `NFR-OPS1`, `NFR-MLO2` |
| ☑ | `CICD-04` | Viết 3 Runbooks Vận hành Production (`deploy-digitalocean.md`, `incident-and-rollback.md`, `drift-and-retraining-runbook.md`) | Hướng dẫn chi tiết từng lệnh khởi tạo Droplet, cấu hình GitHub Secrets, quy trình Triage Drift theo Lec 4 Q20 và quy trình Rollback App/Model/DB. | 2 | `CICD-03` | `NFR-OPS1` |
| ☐ | `CICD-05` | Đẩy `learnguard-platform` lên GitHub (`viethung12062005/learnguard-platform`) & kích hoạt chạy thật các workflows CI/CD | Repo GitHub được khởi tạo, code được push lên `main`, workflow `ci-platform.yml` và `mlops-drift-retrain.yml` chạy thực tế trên GitHub Actions đạt trạng thái **XANH (Success)**. | 2 | `CICD-04` | `NFR-OPS1` |
| ☐ | `OPS-06` | Provision DigitalOcean Droplet VM thật, cấu hình GitHub Environment `production` secrets & chạy CD E2E | Droplet hoạt động, `DO_HOST`/`DO_SSH_KEY` được nạp vào GitHub Secrets, `cd-digitalocean-prod.yml` deploy thành công và `smoke-test.sh` pass 100% trên IP/domain thật. | 4 | `CICD-05` | `NFR-OPS1` |
| ☐ | `OPS-07` | Diễn tập Safeguard, Fault-Injection & Rollback trên Cloud (GameDay Drill — Lec 6) | Chạy thực nghiệm 3 bài diễn tập trên VM: (1) Rollback container lỗi bằng `rollback-do.sh`, (2) Rollback model bằng `--mode rollback`, (3) Restore DB bằng `restore-db.sh`; ghi log vào báo cáo bảo vệ. | 4 | `OPS-06` | `FR-08`, `NFR-OPS1` |
