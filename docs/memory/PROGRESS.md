# PROGRESS — Tiến độ LearnGuard Platform

> **Cập nhật:** 2026-11-23 | **Mô hình Cloud:** **Cloud-Portable Dual-Option Deployment (Option A: Azure PaaS + Option B: DigitalOcean VM)** — cả hai đích đều ở trạng thái **Active / Ready-to-Deploy** (deploy lên 1 cloud có credit/tài khoản tại thời điểm vận hành, không chạy đồng thời).

---

## 1. Trạng thái Tổng thể các Giai đoạn (Phases & Gates)

| Giai đoạn | Nội dung Chính | Đích Cloud | Trạng thái |
| :--- | :--- | :---: | :--- |
| **Phase 0 (2026-11-04)** | App facts, Azure discovery (`azure-permissions-report.md`), Requirements/NFR, Threat model | Option A (Azure) | ✅ **Hoàn tất** |
| **Phase 1 (2026-11-04)** | Hạ tầng Terraform Azure PaaS (`infra/bootstrap/`, `infra/modules/*`, `infra/env/dev/`), guardrail `check_plan.py`, CD dev workflows (`cd-dev-*.yml`), Jump VM & seed verified | **Option A (Azure PaaS)** | ✅ **Active — Ready to Deploy** |
| **Phase 2 (2026-11-23)** | Hạ tầng DigitalOcean VM (`infra/digitalocean/`, `deploy/digitalocean/`), Dockerfiles dùng chung, GHCR CI/CD + Trivy + Auto-Rollback (`CICD-05`), Động cơ Drift Triage + Behavioral Gate + Retraining (`deploy/ml/`), Chuẩn hóa Dual-Cloud Docs `00-*..06-*` (`ARC-05`) | **Option B (DO VM) + Shared Core** | ✅ **Implemented & CI Verified (`G4` Ready)** |
| **Phase 3 (Đang diễn ra)** | Đóng Critical Path ứng dụng (`BE-08..11`, `FE-09..12`, `ML-11`, `AI-06..07`, closed-loop oversight fixes) + Provision & GameDay Live trên Cloud đang chọn (`OPS-06`, `OPS-07`) | Cả 2 Option (App Core) + Active Target | 🔄 **In Progress** |

---

## 2. Thành tựu Đã Hoàn tất & Kiểm chứng (Verified Milestones)

### 2.1. Kiến trúc Dual-Cloud & Chuẩn hóa Tài liệu (`ARC-05` — ✅ Done)

| Hạng mục | Trạng thái | Đường dẫn Chuẩn |
| :--- | :---: | :--- |
| Master Documentation Hub (`00-*..06-*` + `memory/`) | ✅ **Done** | [`../README.md`](../README.md) |
| Quy chuẩn SE, DevOps & MLOps (CMU MLIP Lec 1–6 + Dual-Cloud) | ✅ **Done** | [`../00-conventions.md`](../00-conventions.md) |
| Chiến lược Cloud-Portable Dual-Option (Deploy-Where-Available) | ✅ **Done** | [`../03-architecture/dual-cloud-strategy.md`](../03-architecture/dual-cloud-strategy.md) |
| Active Cloud Option A Architecture & ADRs `0001..0007` | ✅ **Done** | [`../03-architecture/azure-target-architecture.md`](../03-architecture/azure-target-architecture.md) · [`../03-architecture/adr/`](../03-architecture/adr/0001-compute-container-apps.md) |
| Active Cloud Option B Architecture & ADRs `0008..0010` | ✅ **Done** | [`../03-architecture/digitalocean-target-architecture.md`](../03-architecture/digitalocean-target-architecture.md) · [`../03-architecture/adr/0008-cloud-migration-digitalocean-vm.md`](../03-architecture/adr/0008-cloud-migration-digitalocean-vm.md) |
| Production Readiness Gap Register v4 (Dual-Cloud + 10 Real Code Gaps) | ✅ **Done** | [`../03-architecture/production-readiness-gap.md`](../03-architecture/production-readiness-gap.md) |
| Unified Threat Model (STRIDE + OWASP LLM Top 10 cho Option A & B) | ✅ **Done** | [`../03-architecture/threat-model.md`](../03-architecture/threat-model.md) |
| Chiến lược SE & Delivery (Multi-Repo Modular Monolith, Critical-Path Unblock) | ✅ **Done** | [`../04-devops/software-engineering-strategy.md`](../04-devops/software-engineering-strategy.md) |
| Chỉ mục Runbooks Thống nhất (Option A Azure + Option B DO + MLOps) | ✅ **Done** | [`../04-devops/runbooks-index.md`](../04-devops/runbooks-index.md) |

### 2.2. CI/CD Live Verification & GHCR Immutable `@sha256` Digests (`CICD-05` — ✅ Done, commit `e9f9c81`)

Pipeline `ci-platform.yml`, `ci-build-and-scan.yml`, và `mlops-drift-retrain.yml` đã chạy thực tế trên GitHub Actions (0 CRITICAL/HIGH Trivy CVEs), khóa bộ digest bất biến trong [`../../deploy/releases/prod.yaml`](../../deploy/releases/prod.yaml) & [`../../deploy/releases/dev.yaml`](../../deploy/releases/dev.yaml):

| Thành phần | Source Repo & Commit SHA | Verified GHCR Immutable `@sha256` Digest |
| :--- | :--- | :--- |
| **`api`** (`Dockerfile.api`) | `ntk223/BE-MLOPS@a2bae92603aea5796de03267f32cc55589dfd9d0` | `ghcr.io/viethung12062005/learnguard-api@sha256:2d232c5ca2f1d72c2f3f38347561f4490b57d7ac9f579747149f372ce7cc8a8c` |
| **`ml_batch`** (`Dockerfile.ml`) | `ntk223/Data-ML-MLOPS@72c96cdfde4bbf084cc68ede500aa4f0c4e3decf` | `ghcr.io/viethung12062005/learnguard-ml@sha256:5bfab2cccd13387214929faf3c05d4b9ea2e3d5f11c04e06fbc0a4006d09833f` |
| **`frontend`** (`Dockerfile.fe`) | `ntk223/FE-MLOPS@0f70e1498cd05360876da361b347b48d1af31eda` | `ghcr.io/viethung12062005/learnguard-fe@sha256:1805e399bcadf79186e99545f0ebf0a353bd678e179ea4d503ac744efda6c63f` |

### 2.3. Hạ tầng Trợ lý Kỹ thuật (`agent-harness` — ✅ Active)

- `harness doctor learnguard`: `profile learnguard: ok` (`git`, `gh`, `python3`, `.venv` với `numpy` + `PyYAML` hoạt động; tìm kiếm semantic fallback sang BM25 khi chưa bật local Ollama warmup).
- Quy trình điều phối, tra cứu (`harness q`, `harness ask`), kiểm thử (`harness run`), preflight (`harness preflight`), và kiểm chứng DoD (`harness dod run`, `harness status`) đã kích hoạt cho cả 4 thành viên.

---

## 3. Đồng bộ Snapshot 3 Repo Ứng dụng (2026-11-23) & Các Gap Cần Đóng

| Repo | Commit SHA Đã kiểm | Phần Đã Chạy Tốt | Khoảng trống Real Baseline Cần Đóng Tiếp |
| :--- | :---: | :--- | :--- |
| **`ntk223/BE-MLOPS`** | `a2bae92` | `/health`, `/predictions*` (kèm `/stats`, `/activity`), `/briefs*`, `/briefs/chat/*`, `/evaluations*`, `/audit-logs` | `auth.py` & `observability.py` vẫn `NotImplementedError`; thiếu `/metrics`; `BriefDecisionRequestBody` thiếu `feedback`; thiếu `GET /predictions/{m}/{p}/{s}/brief`; `briefs.py` chưa nạp `advisor_guidelines.md`. |
| **`ntk223/Data-ML-MLOPS`** | `72c96cd` | M1–M5, Linear SHAP, Benchmark, Top-20% Release, `learnguard evaluate {data,ml,llm,all}` (`163 passed`) | `ml_gate.py` mới kiểm tra fairness trên `gender` (`ML-11`); `llm_judge.py` chưa calibrate với human annotations (`AI-06`); thiếu Product Value study (`AI-07`). |
| **`ntk223/FE-MLOPS`** | `0f70e14` | Dashboard, Student Detail (+ 4-week Activity), Brief Edit, Chat Drawer, `/evaluations`, `/audit`, role guards | Chưa nối Real JWT Auth (`FE-09`); `StudentDetailPage.tsx` thiếu nút Accept/Reject + feedback; `AdvisorDashboardPage.tsx` hardcode 5/7 modules & 3/4 presentations; cần mở rộng `tests/run.mjs` (`FE-11`, `FE-12`). |

---

## 4. Việc Tiếp theo (Next Steps — Theo Thứ tự Ưu tiên)

1. **Đóng App Critical Path (Cả 2 Cloud đều hưởng lợi):**
   - `SWE1`: Implement M6 JWT Auth + RBAC (`BE-08`, `BE-09`, `BE-10`), thêm `feedback` vào `BriefDecisionRequestBody`, thêm `GET /predictions/{m}/{p}/{s}/brief`, triển khai `observability.py` + `/metrics` (`BE-11`).
   - `SWE2`: Nối JWT Auth thật (`FE-09`), thêm nút Accept/Reject + ô feedback vào `StudentDetailPage.tsx`, sửa dropdown `AdvisorDashboardPage.tsx` đủ 7 modules / 4 presentations, hoàn thiện `FE-10`–`FE-12`.
   - `AIE`: Mở rộng fairness 5 chiều trong `ml_gate.py` (`ML-11`), nạp `advisor_guidelines.md` vào `briefs.py`, hiệu chỉnh `llm_judge.py` (`AI-06`) và thực nghiệm Product Value (`AI-07`).
2. **Triển khai Thực tế lên Cloud Đang Có Credit (`OPS-06`, `OPS-07`):**
   - *Nếu chọn Option B (DigitalOcean):* Chạy `infra/digitalocean/` Terraform → nạp GitHub Env `production` secrets → chạy `cd-digitalocean-prod.yml` → bật TLS `443` → thực thi 3 bài diễn tập GameDay (`OPS-07`).
   - *Nếu chọn Option A (Azure PaaS):* Chạy theo [`../../runbooks/deploy-dev.md`](../../runbooks/deploy-dev.md) → bổ sung mount Azure Files `lgdata` cho `ca-lg-dev-api` (`EVALUATIONS_DIR`, `OULAD_DATA_DIR`) → smoke test Blue/Green.
3. **Nâng cấp Release Manifest:** Sau khi các repo app merge PR đóng Critical Path, rebuild qua `ci-build-and-scan.yml` và cập nhật `@sha256` digests mới vào `deploy/releases/prod.yaml`.

---

<details>
<summary>Lịch sử Ghi nhận Azure Option A (2026-11-04 / 2026-11-05 — Vẫn Active như Option A)</summary>

- User `HungTV88@fpt.com`, subscription `FSO-SB-GHCHCS-OJT-DEV`, `Role: FSO-SandboxOps`.
- Đã triển khai & verify thực tế `infra/bootstrap/`, `infra/modules/*`, `infra/env/dev/` (39+ resources), Jump VM `vm-az-lg-jump`, `deploy/db/seed.sh`, `caj-lg-dev-ml` (`27,535` predictions batch), `ca-lg-dev-api`, và `swa-lg-dev` (xem nhật ký lệnh tại [`../04-devops/legacy-runbooks/deploy-runbook.md`](../04-devops/legacy-runbooks/deploy-runbook.md)).

</details>
