# SESSION_LOG — Nhật ký Phiên làm việc

> File "kiến thức" → không commit vào `learnguard-platform`.

---

## 2026-11-23 — Phase 2: DigitalOcean Production Migration, CMU MLIP Conventions & Drift/Retraining Pipeline

### Mục tiêu phiên
1. Chuẩn hóa bộ quy chuẩn Kỹ thuật Phần mềm, DevOps và MLOps dựa trên giáo trình **CMU MLIP (Lectures 1–6)** cho toàn bộ hệ thống LearnGuard.
2. Chốt kiến trúc chuyển dịch hạ tầng đích từ Azure Container Apps sang **DigitalOcean Droplet VM** (Docker Compose Production Stack, 2-network isolation, least-privilege DB roles, Nginx rate-limiting & security headers, Prometheus monitoring).
3. Thiết kế hệ thống **CI/CD đa tầng** trên GitHub Actions với GHCR immutable digests (`@sha256`), Trivy scan, pre-deploy DB backup, smoke test và auto-rollback.
4. Thiết kế kiến trúc **Data Drift Detection, Triage, Behavioral Gate, Simulation (5 kịch bản) và Continual Retraining (Champion vs. Challenger)**.
5. Cập nhật đồng bộ memory docs, ADR 0008–0010, Production Readiness Gap Register (v3) và snapshot `PROJECT_CONTEXT.md` theo các commit mới nhất từ 3 repo app (`BE-MLOPS` `a2bae92`, `Data-ML-MLOPS` `72c96cd`, `FE-MLOPS` `0f70e14`).

### Việc đã làm (Tài liệu, Kiến trúc & Memory)
- **Quy chuẩn CMU MLIP:** Tạo `docs/conventions/software-engineering-and-mlops-conventions.md` (phiên bản 2.0) định nghĩa 4 Boundaries, khung `ASM ∧ SPEC => REQ`, Defensible Success Portfolio, 6-Clause Data Contract, Three Control Points và Tháp kiểm thử 6 tầng (`L1`–`L6`).
- **Quyết định Kiến trúc (ADRs):**
  - `docs/adr/0008-cloud-migration-digitalocean-vm.md` (`D-018`): Chuyển dịch sang DigitalOcean Droplet VM + VPC + Cloud Firewall + Docker Compose Production Stack (`lg_frontend_net`, `lg_backend_net`).
  - `docs/adr/0009-cicd-pipeline-digitalocean-ghcr.md` (`D-020`): Pipeline CI/CD 4 workflows (`ci-platform.yml`, `ci-build-and-scan.yml`, `cd-digitalocean-prod.yml`, `mlops-drift-retrain.yml`) với `@sha256` immutable images và auto-rollback.
  - `docs/adr/0010-drift-detection-and-continual-retraining-pipeline.md` (`D-021`): Kiến trúc phát hiện Drift đa tầng + Triage + Behavioral Gate + 5 kịch bản mô phỏng + Champion vs. Challenger release pointer (`active_release.json`).
- **Cập nhật Memory & Đánh giá hệ thống:**
  - Cập nhật `docs/memory/DECISIONS.md` bổ sung `D-018` đến `D-021`.
  - Cập nhật `docs/memory/PROGRESS.md` phản ánh tiến độ Phase 2 và các commit mới của 3 repo app.
  - Cập nhật `docs/memory/OPEN_QUESTIONS.md` đóng/supersede các câu hỏi Azure (`Q-CI-IDENTITY`, `Q-RBAC`, `Q-POLICY`, `Q-ACR-PE`) và ghi nhận các đầu việc vận hành DigitalOcean (`Q-DO-PROVISION`, `Q-DO-SECRETS`).
  - Cập nhật `docs/architecture/production-readiness-gap.md` bổ sung mục §4 (Kiến trúc v3), đóng các gap `G-02`, `G-03`, `G-05`, `G-10`, `G-11`, `G-12`, `G-19`, nâng điểm like-production từ `~7.0/10` lên **`9.2/10`**.
  - Cập nhật `PROJECT_CONTEXT.md` theo snapshot `2026-11-23` của `BE-MLOPS` (`a2bae92`), `Data-ML-MLOPS` (`72c96cd`), `FE-MLOPS` (`0f70e14`).
  - Tạo `docs/memory/SESSION_LOG.md`.

### Quyết định kiến trúc đã chốt
- `D-018` (ADR-0008): DigitalOcean Droplet VM + Docker Compose 2 mạng cô lập.
- `D-019`: Bộ quy chuẩn CMU MLIP Lectures 1–6.
- `D-020` (ADR-0009): GitHub Actions + GHCR `@sha256` + Trivy + pre-deploy backup + auto-rollback.
- `D-021` (ADR-0010): Drift Triage + Behavioral Gate + Champion vs. Challenger continual retraining.

### Vấn đề còn lại / Bước kế tiếp
- Provision DigitalOcean Droplet VM qua Terraform (`infra/digitalocean/`) và cấu hình IP/domain (`Q-DO-PROVISION`).
- Nạp secrets (`DO_HOST`, `DO_USER`, `DO_SSH_KEY`, `DO_PORT`) vào GitHub Environment `production` (`Q-DO-SECRETS`).
- Xác minh enforcement JWT/RBAC trên các endpoint backend trước khi mở truy cập public (`Q-AUTH`).
