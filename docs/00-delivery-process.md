# Quy trình Phát triển & Bàn giao Dự án LearnGuard (Delivery Process & Approval Gates)

> **Học tập & Chuẩn hóa từ:** Quy trình kỹ thuật của `smart-hospital-platform` kết hợp khung lý thuyết **CMU Machine Learning in Production (MLIP)** (Lectures 1–6) và đề bài **Chủ đề 4 — Student Success Early-Warning Assistant**.
> **Nguyên tắc cốt lõi:** Dự án đi qua 6 giai đoạn (Phases) nối tiếp nhau. **Mỗi giai đoạn có một cổng phê duyệt (Approval Gate `G1` → `G4`)**. Mọi quyết định kiến trúc, mô hình và vận hành đều phải truy vết hai chiều về yêu cầu (`FR`/`NFR`) và bằng chứng kiểm thử tự động ([02-requirements/traceability.md](02-requirements/traceability.md)).

```text
Phase 1: Problem Framing & Value/Risk --G1--> Phase 2: Requirements (ASM ∧ SPEC => REQ) --G2--> Phase 3: Architecture & Contracts
   --G3--> Phase 4: Platform, CI/CD & MLOps Drift/Retrain Engine --G4--> Phase 5: Sprint-based Development (4 Devs)
   --> Phase 6: System-Level Testing, Safeguard/Chaos Drills & Final Defense
```

---

## 1. Bản đồ Giai đoạn, Đầu ra và Cổng Phê duyệt (Phases & Gates)

| Giai đoạn (Phase) | Chủ sở hữu chính | Đầu ra bắt buộc (Outputs) | Điều kiện vượt cổng (Gate Pass Conditions) | Trạng thái hiện tại |
| :--- | :--- | :--- | :--- | :--- |
| **1. Problem Framing & Risk (CMU MLIP Lec 1–2)** | **MLOPS** + **AIE** | Tuyên bố giá trị sản phẩm (Product Claim), 4 Boundaries, FMEA & Risk Register, phân định In-Scope / Out-of-Scope theo đề bài Chủ đề 4. | **G1**: Cả nhóm thống nhất mục tiêu dự báo tại `cutoff_day=27`, ngân sách tải cố vấn Top-20%, và quy tắc 100% Human Oversight (không tự động gửi cảnh báo cho sinh viên). | ✅ **Approved (G1)** |
| **2. Requirements & Success Portfolio (Lec 2)** | **MLOPS** + **SWE1** | `FR-01`..`FR-09`, `NFR` có ngưỡng định lượng & phương pháp đo, khung `ASM ∧ SPEC => REQ`, Defensible Success Portfolio, [Ma trận truy vết](02-requirements/traceability.md). | **G2**: Mọi `FR` có Acceptance Criteria (AC); mọi `NFR` có con số đo được; mọi `ASM` (như `ASM-03` Delayed Ground Truth) có cơ chế kiểm soát. | ✅ **Approved (G2)** |
| **3. Architecture, ADRs & Contracts (Lec 3–4)** | **MLOPS** (Architect) | [Kiến trúc DigitalOcean v3](03-architecture/dual-cloud-strategy.md), [ADR 0001–0010](03-architecture/adr/), [DB Contract](../../BE-MLOPS/docs/DB_CONTRACT.md), [API Contract](../../FE-MLOPS/docs/API_CONTRACT.md), [Prediction Batch Contract](../../Data-ML-MLOPS/docs/M5_PREDICTION_BATCH.md), [Backlog 4 thành viên](05-plan/project-plan.md). | **G3**: Toàn bộ ADR ở trạng thái `Accepted`; ranh giới 4 repo (`learnguard-platform`, `Data-ML-MLOPS`, `BE-MLOPS`, `FE-MLOPS`) và hợp đồng schema đã khóa. | ✅ **Approved (G3)** |
| **4. Platform, CI/CD & Drift/Retrain Engine (Lec 4–6)** | **MLOPS** | Terraform DigitalOcean (`infra/env/dev/ (Azure Option A) và infra/digitalocean/ (DigitalOcean Option B)`), Docker Compose 2 mạng cô lập (`deploy/digitalocean/`), 4 GitHub Actions workflows, Drift Triage + Behavioral Gate + Retraining Pipeline (`deploy/ml/`). | **G4**: Pipeline CI/CD chạy xanh trên GitHub Actions; mô phỏng 5 kịch bản drift/retrain pass 100%; deploy + smoke test + auto-rollback hoạt động trong `<= 60s`. | ✅ **Implemented (G4 Ready)** |
| **5. Sprint-based Development & Hardening** | **MLOPS, SWE1, SWE2, AIE** | Đóng toàn bộ các hạng mục `◐ Partial` / `☐ Todo` theo [Backlog từng thành viên](05-plan/by-person/) (đặc biệt là M6 JWT Auth/RBAC, kết nối FE Auth thật, LLM Rubric Eval, E2E UI Tests). | **Definition of Done (DoD)**: 100% task Must/Should có test tự động xanh trên CI, không có lỗ hổng High/Critical, cập nhật DoD Audit. | 🚧 **In Progress** |
| **6. Production Engineering & Defense (Lec 6)** | Cả nhóm (4 thành viên) | Diễn tập Safeguard & Fault-Injection (LLM sập, dữ liệu lỗi ngữ nghĩa, rollback model/app), đo p50/p95 latency & chi phí LLM, báo cáo tổng kết & demo E2E trên DigitalOcean VM. | Toàn bộ `NFR` và tiêu chí đánh giá mục 4 đề bài Chủ đề 4 có số liệu thực nghiệm và biểu đồ minh chứng. | ⬜ **Planned (W9–W10)** |

---

## 2. Các Môi trường Vận hành (Environments)

| Môi trường | Mục đích | Ai triển khai | Dữ liệu & Cấu hình |
| :--- | :--- | :--- | :--- |
| **`local`** | Máy cá nhân của từng thành viên (Ubuntu/WSL2), chạy `.venv` + Docker Compose local hoặc FastAPI/Vite dev server. | Từng Dev (`MLOPS`, `SWE1`, `SWE2`, `AIE`) | OULAD (`archive.zip` / `db_seed_full.sql`) hoặc bộ dữ liệu mô phỏng từ `data_simulator.py`. Không dùng dữ liệu cá nhân thật. |
| **`ci-simulation`** | GitHub-hosted runner chạy tự động trên mỗi PR/push và lịch định kỳ (`ci-platform.yml`, `mlops-drift-retrain.yml`). | GitHub Actions tự động | Sinh dữ liệu mô phỏng deterministic 5 kịch bản drift, chạy đủ 6 tầng kiểm thử (Unit, Contract, Behavioral, Drift/Retrain, Safeguard, Build). |
| **`prod` (DigitalOcean VM)** | Droplet Ubuntu 24.04 LTS trên DigitalOcean VPC (`docker-compose.prod.yml`), phục vụ tích hợp E2E, đánh giá hiệu năng và bảo vệ đồ án. | Pipeline `cd-digitalocean-prod.yml` + **MLOPS** phê duyệt | OULAD chuẩn đã ẩn danh 100% qua `student_key` (SHA-256 16-hex); tách 2 role DB `lg_ml_writer` và `lg_api`. |

---

## 3. Định nghĩa Hoàn thành (Definition of Done — Áp dụng cho mọi Task)

Một task trong [backlog.csv](05-plan/backlog.csv) chỉ được chuyển sang trạng thái `☑ Done` khi thỏa mãn **đồng thời** điều kiện `Done when` riêng của task đó và 8 tiêu chí chung sau:

1. **Truy vết rõ ràng:** Task gắn với mã `US-xx` (hoặc `ENABLER`) và yêu cầu `FR-xx` / `NFR-xx` tương ứng.
2. **Tuân thủ hợp đồng (Contract-first):** Không phá vỡ hợp đồng `DB_CONTRACT.md`, `API_CONTRACT.md`, `M5_PREDICTION_BATCH.md`, `eval-report.v1`, hoặc `drift-report.v1`.
3. **Kiểm thử tự động xanh:** Unit test, contract test và behavioral test liên quan đều pass trong CI (`pytest`, `unittest`, `npm run build && npm test`).
4. **Chất lượng mã & Linter sạch:** `ruff check` (Python), `tsc --noEmit` (TypeScript), `bash -n` (Shell) không có lỗi.
5. **Bảo mật & Quyền riêng tư:** Không chứa `id_student` thô hay PII trong DB backend, logs, hoặc prompt LLM; không commit secret/token/password; image container chạy non-root (`UID 10001`) và pass Trivy scan.
6. **Không sửa nhầm phạm vi (Boundary discipline):** Dev ứng dụng không tự ý sửa Dockerfile, CI/CD workflow hoặc cấu hình hạ tầng trong `learnguard-platform` nếu không có task/issue được `MLOPS` duyệt.
7. **Không sửa migration hay release đã khóa:** Không sửa file Alembic migration đã merge (chỉ tạo migration mới); không ghi đè thư mục `model-releases/<release-id>` hoặc `evaluations/<run-id>` đã xuất.
8. **Bằng chứng thực nghiệm:** Ghi rõ lệnh kiểm chứng và kết quả đầu ra thật vào PR và [dod-audit.md](05-plan/dod-audit.md). Không bao giờ đánh dấu hoàn thành cho phần việc chưa chạy kiểm chứng.
