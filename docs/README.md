# LearnGuard Platform — Master Documentation Hub

> **Phiên bản:** 3.0 (2026-11-23)
> **Chiến lược Cloud:** **Cloud-Portable Dual-Option Deployment (Deploy-Where-Available)** — duy trì đồng thời **Option A (Azure PaaS)** và **Option B (DigitalOcean VM)** là 2 đích triển khai hạng nhất (first-class), dùng chung 100% container images, schema/roles PostgreSQL và động cơ MLOps. Tại thời điểm triển khai, đội vận hành chỉ cần deploy lên **một cloud đang có credit/tài khoản khả dụng** (không phải chạy hay trả phí cả hai cloud cùng lúc).

---

## 1. Bức tranh Hệ thống & Phân chia 4 Kho mã nguồn

**LearnGuard** (*Student Success Early-Warning Assistant* — Chủ đề 4) là nền tảng hỗ trợ cố vấn học tập phát hiện sớm sinh viên có nguy cơ `Fail/Withdrawn` tại **cuối tuần 4 (`cutoff_day = 27`)** trên bộ dữ liệu **OULAD**, kết hợp mô hình ML diễn giải được (`LogisticRegression` + `LinearSHAP` với ngân sách cảnh báo Top-20%) và dịch vụ LLM tạo **Advisor Brief** + **Advisor Copilot Chatbot** dưới sự phê duyệt **100% Human Oversight** của con người.

| Kho mã nguồn | Vai trò | Quyền sở hữu & Giao tiếp |
| :--- | :--- | :--- |
| **`learnguard-platform`** *(repo này)* | Hạ tầng Terraform (Option A Azure & Option B DigitalOcean), Dockerfiles dùng chung, Docker Compose, Nginx, CI/CD GitHub Actions, Động cơ Drift/Behavioral/Retraining (`deploy/ml/`), Runbooks & Docs. | **Toàn quyền đọc/ghi** — Repo điều phối trung tâm. |
| **`ntk223/Data-ML-MLOPS`** | Pipeline dữ liệu & ML batch (`learnguard` CLI: M1–M5, 3 cổng `learnguard evaluate {data,ml,llm}`). | **Upstream Read-Only** — Đọc CSV OULAD, xuất `eval-report.v1`, ghi bảng `ml_predictions` qua role `lg_ml_writer`. |
| **`ntk223/BE-MLOPS`** | FastAPI Modular Monolith (`learnguard_backend`: M6–M8, Predictions, Briefs, Chat, Evaluations, Audit). | **Upstream Read-Only** — Chỉ `SELECT` bảng `ml_predictions` qua role `lg_api`; sở hữu `users`, `briefs`, `decisions`, `llm_calls`, `audit_logs`, `chat_*`. |
| **`ntk223/FE-MLOPS`** | React 18 + TypeScript + Vite SPA (M9 Advisor & Admin Dashboard). | **Upstream Read-Only** — Chỉ giao tiếp REST API theo `FE-MLOPS/docs/API_CONTRACT.md`. |

---

## 2. Bản đồ Tài liệu Chuẩn hóa (`00-*` → `06-*` + `memory/`)

| Nhóm | Tài liệu | Nội dung Chính | Đối tượng Đọc |
| :--- | :--- | :--- | :--- |
| **`00-*` Quy chuẩn & Quy trình** | [`00-conventions.md`](00-conventions.md) | Quy chuẩn CMU MLIP Lec 1–6: 4 Boundaries, `ASM ∧ SPEC => REQ`, Success Portfolio, 6-Clause Data Contract, 3 Control Points, Dual-Cloud & Repo standards. | Cả 4 devs & Operators |
| | [`00-delivery-process.md`](00-delivery-process.md) | 6 giai đoạn SDLC, cổng phê duyệt `G1`–`G4`, các môi trường và Definition of Done (DoD) 8 điểm. | Cả 4 devs |
| | [`00-workflow.md`](00-workflow.md) | Bảo vệ nhánh `main`, quy ước Branch/Commit/PR, DoR/DoD 10 điểm, ma trận *Who Changes What*. | Cả 4 devs |
| **`01-business-analysis/`** | [`01-business-analysis/problem-and-scope.md`](01-business-analysis/problem-and-scope.md) | Phân tích bài toán Chủ đề 4, In-Scope / Out-of-Scope, ranh giới đạo đức & nhân sự. | PM, AIE, SWE1, SWE2 |
| | [`01-business-analysis/product-value-protocol.md`](01-business-analysis/product-value-protocol.md) | Quy trình thực nghiệm đo lường giá trị sản phẩm (thời gian rà soát & chất lượng can thiệp có vs không có AI). | AIE, SWE2, PM |
| **`02-requirements/`** | [`02-requirements/requirements.md`](02-requirements/requirements.md) | Đặc tả yêu cầu chức năng (`FR-01`..`FR-09`) và phi chức năng (`NFR`). | Cả 4 devs |
| | [`02-requirements/app-facts.md`](02-requirements/app-facts.md) | Sự thật kiểm chứng trực tiếp từ mã nguồn `BE-MLOPS`, `Data-ML-MLOPS`, `FE-MLOPS`. | MLOPS, SWE1, SWE2, AIE |
| | [`02-requirements/traceability.md`](02-requirements/traceability.md) | Ma trận truy vết hai chiều: `FR`/`NFR` ↔ `CMU MLIP` ↔ `ADR` ↔ `Task` ↔ `Test`. | Cả 4 devs & Reviewer |
| **`03-architecture/`** | [`03-architecture/dual-cloud-strategy.md`](03-architecture/dual-cloud-strategy.md) | **Chiến lược Cloud-Portable Dual-Option:** So sánh **Option A (Azure PaaS)** vs **Option B (DigitalOcean VM)**, lõi phi đám mây, parity matrix & cây quyết định. | MLOPS, Operators, PM |
| | [`03-architecture/azure-target-architecture.md`](03-architecture/azure-target-architecture.md) | Kiến trúc đích **Option A (Azure PaaS v2)**: VNet private data-plane, Container Apps + Job, SWA, PG Flexible, Key Vault, ACR. | MLOPS, Azure Operators |
| | [`03-architecture/digitalocean-target-architecture.md`](03-architecture/digitalocean-target-architecture.md) | Kiến trúc đích **Option B (DigitalOcean VM v3)**: Droplet VPC/Firewall, Docker Compose 2 mạng cô lập, Nginx, PG 16, Ollama, Prometheus. | MLOPS, DO Operators |
| | [`03-architecture/drift-and-retraining-specification.md`](03-architecture/drift-and-retraining-specification.md) | Đặc tả Drift Taxonomy (5 loại), PSI/KS, Semantic Guard `10x`, `ASM-03`, Behavioral Gate & 5 kịch bản mô phỏng. | MLOPS, AIE |
| | [`03-architecture/production-readiness-gap.md`](03-architecture/production-readiness-gap.md) | **Gap Register v4:** Đánh giá sẵn sàng production Dual-Cloud kèm audit toàn bộ khoảng trống thực tế trong code baseline. | Cả 4 devs & Reviewer |
| | [`03-architecture/threat-model.md`](03-architecture/threat-model.md) | Mô hình đe dọa hợp nhất **STRIDE + OWASP LLM Top 10** cho cả Option A (Azure) và Option B (DigitalOcean). | MLOPS, SWE1, AIE |
| | [`03-architecture/diagrams/cloud-architecture.html`](03-architecture/diagrams/cloud-architecture.html) | Sơ đồ kiến trúc tương tác SVG (Azure Option A private networking). | MLOPS, Operators |
| **`03-architecture/adr/`** | [`0001`](03-architecture/adr/0001-compute-container-apps.md) · [`0002`](03-architecture/adr/0002-frontend-static-web-apps.md) · [`0003`](03-architecture/adr/0003-data-postgresql-flexible.md) · [`0004`](03-architecture/adr/0004-secrets-dataplane-auth.md) · [`0005`](03-architecture/adr/0005-iac-terraform.md) · [`0006`](03-architecture/adr/0006-cicd-github-actions-oidc.md) · [`0007`](03-architecture/adr/0007-ml-storage-batch-observability.md) | Bộ 7 ADR cho **Active Cloud Option A (Azure PaaS)**. | MLOPS, Azure Operators |
| | [`0008`](03-architecture/adr/0008-cloud-migration-digitalocean-vm.md) · [`0009`](03-architecture/adr/0009-cicd-pipeline-digitalocean-ghcr.md) | Bộ 2 ADR cho **Active Cloud Option B (DigitalOcean VM + GHCR + Auto-Rollback)**. | MLOPS, DO Operators |
| | [`0010`](03-architecture/adr/0010-drift-detection-and-continual-retraining-pipeline.md) | ADR **Cloud-Agnostic MLOps**: Drift Detection, Triage & Champion-vs-Challenger Retraining. | MLOPS, AIE |
| **`04-devops/`** | [`04-devops/software-engineering-strategy.md`](04-devops/software-engineering-strategy.md) | Chiến lược SE & Delivery: Multi-Repo Modular Monolith, Contract-First, Critical-Path Unblock, 6-Layer CI/CD, GitOps & `agent-harness`. | Cả 4 devs |
| | [`04-devops/runbooks-index.md`](04-devops/runbooks-index.md) | Chỉ mục vận hành thống nhất trỏ tới runbooks Option A (Azure), Option B (DigitalOcean) & MLOps/Incident. | Operators & MLOPS |
| | [`04-devops/azure-permissions-report.md`](04-devops/azure-permissions-report.md) | Báo cáo kiểm tra quyền thực tế `FSO-SandboxOps` & các chính sách `FSO-SZ` trên Azure. | MLOPS, Azure Operators |
| | [`04-devops/legacy-runbooks/`](04-devops/legacy-runbooks/deploy-runbook.md) · [`04-devops/reports/`](04-devops/reports/resource-inventory-2026-11-10.tsv) | Nhật ký lệnh triển khai Azure v2 thực tế & kết quả chạy batch/tài nguyên tham khảo. | MLOPS |
| **`05-plan/`** | [`05-plan/project-plan.md`](05-plan/project-plan.md) · [`05-plan/backlog.csv`](05-plan/backlog.csv) · [`05-plan/dod-audit.md`](05-plan/dod-audit.md) | Kế hoạch tổng thể 4 thành viên, Backlog chuẩn hóa và báo cáo kiểm toán DoD. | Cả 4 devs |
| | [`05-plan/by-person/MLOPS.md`](05-plan/by-person/MLOPS.md) · [`SWE1.md`](05-plan/by-person/SWE1.md) · [`SWE2.md`](05-plan/by-person/SWE2.md) · [`AIE.md`](05-plan/by-person/AIE.md) | Checklist công việc chi tiết từng thành viên. | Theo vai trò |
| | [`05-plan/legacy-azure-phase1-8-plan.md`](05-plan/legacy-azure-phase1-8-plan.md) | Kế hoạch Phase 1–8 chi tiết của Option A (Azure PaaS). | MLOPS |
| **`06-testing/`** | [`06-testing/test-strategy-and-gates.md`](06-testing/test-strategy-and-gates.md) | Chiến lược kiểm thử 6 tầng (Unit, Contract, Behavioral MFT/INV/DIR, Drift/Retrain, Safeguard, E2E Smoke). | Cả 4 devs |
| **`memory/`** | [`memory/PROGRESS.md`](memory/PROGRESS.md) · [`memory/DECISIONS.md`](memory/DECISIONS.md) · [`memory/OPEN_QUESTIONS.md`](memory/OPEN_QUESTIONS.md) · [`memory/AZURE_CONSTRAINTS.md`](memory/AZURE_CONSTRAINTS.md) · [`memory/SESSION_LOG.md`](memory/SESSION_LOG.md) | Trí nhớ dài hạn của dự án: tiến độ, quyết định `D-001`..`D-023`, câu hỏi mở, ràng buộc Azure & nhật ký phiên. | Cả 4 devs & AI Agents |

---

## 3. Lộ trình Đọc nhanh theo Vai trò (Quick-Start Onboarding)

| Vai trò | Đọc Bắt buộc trước khi Làm việc | Trọng tâm Tiếp theo (Critical Path) |
| :--- | :--- | :--- |
| **`MLOPS` (Platform / Architect)** | `00-conventions.md` → `03-architecture/dual-cloud-strategy.md` → `04-devops/software-engineering-strategy.md` → `04-devops/runbooks-index.md` → `memory/PROGRESS.md` | Duy trì parity cả Azure Option A (`infra/env/dev/`) & DigitalOcean Option B (`infra/digitalocean/`), thực thi `OPS-06` & `OPS-07` trên cloud đang có credit, review PR xuyên repo. |
| **`SWE1` (Backend `BE-MLOPS`)** | `00-workflow.md` → `02-requirements/app-facts.md` → `03-architecture/production-readiness-gap.md` → `03-architecture/threat-model.md` → `05-plan/by-person/SWE1.md` | Đóng M6 JWT Auth & RBAC (`auth.py`, `BE-08`–`BE-10`), thêm `feedback` vào `BriefDecisionRequestBody`, thêm `GET /predictions/{m}/{p}/{s}/brief`, triển khai `observability.py` + `/metrics` (`BE-11`). |
| **`SWE2` (Frontend `FE-MLOPS`)** | `00-workflow.md` → `02-requirements/app-facts.md` → `03-architecture/production-readiness-gap.md` → `05-plan/by-person/SWE2.md` | Tích hợp JWT Auth thật (`FE-09`), bổ sung nút Accept/Reject + feedback vào `StudentDetailPage.tsx`, sửa dropdown `AdvisorDashboardPage.tsx` đủ 7 modules / 4 presentations, mở rộng `tests/run.mjs` (`FE-11`, `FE-12`). |
| **`AIE` (AI / ML `Data-ML-MLOPS` + LLM)** | `00-conventions.md` → `03-architecture/drift-and-retraining-specification.md` → `03-architecture/production-readiness-gap.md` → `05-plan/by-person/AIE.md` | Mở rộng `ml_gate.py` fairness ra 5 chiều (`ML-11`), nạp `advisor_guidelines.md` vào `AdvisorBriefService.generate`, hiệu chỉnh `llm_judge.py` (`AI-06`) & thực nghiệm Product Value (`AI-07`). |
| **Cloud Operator (Option A / B)** | `03-architecture/dual-cloud-strategy.md` → `04-devops/runbooks-index.md` → Runbook tương ứng của cloud đang chọn | Chọn Option A (Azure PaaS) hoặc Option B (DigitalOcean VM) tùy credit/tài khoản sẵn có; kiểm tra smoke test và quy trình rollback trước khi bàn giao. |

---

## 4. Hạ tầng Trợ lý Kỹ thuật (`agent-harness`) & Release Manifests

- **Active `agent-harness` setup (`profile: learnguard`):** Môi trường làm việc được gắn bộ công cụ kiểm chứng và điều phối `harness`:
  - Tra cứu sự thật trước khi mở file lớn: `harness q next-tasks`, `harness q task <ID>`, `harness ask "<câu hỏi>"`.
  - Chạy lệnh dài & kiểm tra trước PR: `harness run -- <cmd>`, `harness preflight`, `harness dod run --id <ID> --item "<mô tả>" -- <cmd>`.
- **Release Manifests đang ghim immutable digest (`@sha256`):**
  - Production manifest: [`../deploy/releases/prod.yaml`](../deploy/releases/prod.yaml) (`schema: release-manifest.v2`)
  - Dev/Staging manifest: [`../deploy/releases/dev.yaml`](../deploy/releases/dev.yaml) (`schema: release-manifest.v2`)
  - Tài liệu IaC: [`../infra/README.md`](../infra/README.md) (Option A — Azure) & [`../infra/digitalocean/README.md`](../infra/digitalocean/README.md) (Option B — DigitalOcean).
