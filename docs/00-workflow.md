# Quy trình Làm việc Nhóm: Nhánh, Pull Request, DoR/DoD và Phân quyền Sở hữu (Team Workflow)

> **Áp dụng cho:** Cả 4 thành viên (`MLOPS`, `SWE1`, `SWE2`, `AIE`) trên 4 kho mã nguồn của hệ thống LearnGuard (`learnguard-platform`, `BE-MLOPS`, `Data-ML-MLOPS`, `FE-MLOPS`).
> **Tham chiếu:** Học tập cấu trúc quản trị của `smart-hospital-platform/docs/00-workflow.md` và `00-git-github.md`.

---

## 1. Bảo vệ Nhánh `main` (Branch Protection Rules)

Không ai được phép commit hoặc push trực tiếp vào `main` khi phát triển tính năng:

| Quy tắc | Giá trị áp dụng |
| :--- | :--- |
| **Bắt buộc đi qua Pull Request (PR)** | Có (1 task = 1 branch = 1 PR) |
| **Số lượt Review tối thiểu** | 1 lượt review từ thành viên khác + Code Owner của repo (hoặc `MLOPS` đối với thay đổi liên quan tới Contract / Infra / CI/CD) |
| **Kiểm tra CI bắt buộc (Required Status Checks)** | Toàn bộ job trong `ci-platform.yml` (Lint, Unit Tests, Contract Tests, Behavioral Gate, Drift/Retrain Simulation, Web Typecheck/Build) phải **XANH** |
| **Chiến lược Merge** | **Squash and merge** (giữ lịch sử `main` tuyến tính, sạch sẽ; tự động xóa nhánh sau khi merge) |
| **Force-push hoặc xóa nhánh `main`** | Cấm tuyệt đối |

---

## 2. Định danh Công việc, Nhánh và Commit

### 2.1. Cấu trúc Mã Công việc (Task ID)

Mỗi đầu việc trong [05-plan/backlog.csv](05-plan/backlog.csv) có định danh duy nhất theo nhóm:
- **`OPS-xx (Option A Azure PaaS infra/env/dev/ + Option B DigitalOcean VM infra/digitalocean/)`**: Hạ tầng DigitalOcean, Docker Compose, Nginx, PostgreSQL Roles, Backup/Restore, Observability (do **MLOPS** phụ trách).
- **`CICD-xx`**: GitHub Actions CI/CD, GHCR Immutable Digest, Trivy Security Scan, Smoke Test & Auto-Rollback (do **MLOPS** phụ trách).
- **`MLO-xx`**: Drift Monitor, Data Simulator, Behavioral Gate, Continual Retraining Champion-vs-Challenger (do **MLOPS** phụ trách).
- **`BE-xx`**: FastAPI Backend Core, M6 JWT Auth & RBAC, M7 Persistence, Audit Logs, Student Activity, Metrics API (do **SWE1** phụ trách).
- **`FE-xx`**: React/TypeScript Advisor Dashboard, Auth Session Flow, Priority Queue, Student Profile, Human Review UI, Evaluations & Audit UI, E2E Tests (do **SWE2** phụ trách).
- **`ML-xx`**: M1–M3 Data Pipeline & Leakage Audit, M4 Logistic Baseline + Linear SHAP + Alternative Models Benchmark, M5 Batch Scoring, Fairness Slices (do **AIE** phụ trách).
- **`AI-xx`**: M8 LLM Advisor Brief Generation, Interactive Advisor Chatbot, Grounding/Citation Validator, Ollama Fallback, Gate 3 LLM-as-a-Judge Rubric Evaluation (do **AIE** phụ trách).

### 2.2. Quy ước Đặt tên Nhánh và Tiêu đề Commit / PR

1. **Tên nhánh (Branch name):**
   ```text
   <TASK-ID>-<short-description-in-kebab-case>
   ```
   - Ví dụ: `BE-08-jwt-auth-rbac`, `FE-09-real-auth-integration`, `MLO-05-drift-triage-engine`, `AI-07-llm-judge-calibration`.
   - Luôn tách nhánh từ `origin/main` mới nhất: `git fetch origin && git switch -c <branch> origin/main`.
2. **Tiêu đề Commit và Pull Request:**
   ```text
   <story-or-type> (<TASK-ID>): <imperative summary in English>
   ```
   - Ví dụ theo chuẩn Task-traceable:
     - `US-06 (BE-08): implement JWT login and advisor/admin RBAC middleware`
     - `US-14 (MLO-05, MLO-06): add drift triage engine and champion-challenger retraining gate`
     - `ENABLER (CICD-04): add digitalocean production deployment workflow with auto-rollback`
   - Hoặc Conventional Commits kèm Task ID: `feat(auth) [BE-08]: implement JWT login and role guards`.
   - **Không** thêm dòng `Co-Authored-By: ...` của công cụ AI; tác giả commit là kỹ sư chịu trách nhiệm kiểm chứng mã nguồn đó.

---

## 3. Definition of Ready (DoR — Điều kiện để Bắt đầu 1 Task)

Một thành viên chỉ bắt đầu code một task khi:
1. Task đã có trong [backlog.csv](05-plan/backlog.csv) với tiêu chí **`Done when`** rõ ràng, ước lượng `<= 8 giờ`.
2. Các task phụ thuộc (`Depends on`) đã hoàn thành hoặc **Hợp đồng giao tiếp (Contract)** (`DB_CONTRACT.md`, `API_CONTRACT.md`, `M5_PREDICTION_BATCH.md`, `eval-report.v1`) đã được chốt để các bên có thể code song song bằng mock/fixture chuẩn.
3. Đã xác định rõ tài liệu thiết kế cần đọc trước khi code (xem bảng điều hướng trong `AGENT.md`).
4. Đã rõ nguồn dữ liệu kiểm thử (OULAD `archive.zip`, `db_seed_full.sql`, hoặc `data_simulator.py`).

---

## 4. Definition of Done (DoD — Checklist Bắt buộc trước khi Merge PR)

Mọi PR phải điền đầy đủ kết quả kiểm chứng thực tế theo danh sách 10 mục sau:

- [ ] **1. Self-review & Boundary check:** Đã tự đọc lại diff; không có code thừa/debug; không sửa file ngoài phạm vi sở hữu của vai trò (xem Mục 5).
- [ ] **2. Linter & Type-check sạch:**
  - Python: `ruff check .` pass 100%.
  - Frontend: `npm run build` (`tsc --noEmit && vite build`) pass 100%.
  - Shell/Infra: `bash -n` và `yaml.safe_load` / `terraform validate` pass 100%.
- [ ] **3. Unit & Contract Tests xanh:** Toàn bộ test hiện có + test mới cho tính năng/bugfix đều pass (`pytest`, `unittest`, `npm test`).
- [ ] **4. Hợp đồng (Contracts) đồng bộ:** Nếu thay đổi API hoặc cấu trúc Scorecard/Batch, đã cập nhật tài liệu Contract và chạy `pytest tests/test_system_contracts.py` xanh.
- [ ] **5. Kiểm soát Rò rỉ & Hành vi AI/ML (nếu chạm ML/LLM):**
  - ML: Pass `LeakageAuditor` (`0 violations`), `DataGate`, `MLGate`, và `BehavioralGate` (`MFT`, `Invariance`, `Directional`, `Abstention`).
  - LLM: Đảm bảo 100% trích dẫn thuộc `evidence_features`, không suy diễn nhân quả/tâm lý, có fallback khi LLM lỗi.
- [ ] **6. Bảo mật, Quyền riêng tư & Audit:** Không lộ `id_student` thô hay secret trong DB/log/response; mọi thao tác xem dự đoán hoặc duyệt brief đều ghi `audit_logs`.
- [ ] **7. Container & Supply Chain (nếu chạm Docker/CI):** Image build thành công, chạy bằng non-root user (`UID 10001`), pass Trivy scan (`exit-code: 1` cho CRITICAL/HIGH).
- [ ] **8. Cập nhật Tài liệu & Runbook:** Mọi thay đổi về lệnh chạy, biến môi trường (`.env.example`), hoặc quy trình vận hành đã được cập nhật vào `docs/` và `runbooks/`.
- [ ] **9. Cập nhật Trạng thái Backlog:** Đánh dấu tiến độ và ghi nhận bằng chứng vào `docs/05-plan/dod-audit.md` hoặc `docs/memory/PROGRESS.md`.
- [ ] **10. Cross-Review:** Đã được ít nhất 1 thành viên khác review và giải quyết hết các comment trước khi squash merge.

---

## 5. Phân quyền Sở hữu Mã nguồn (Who Changes What — 4 Thành viên)

| Khu vực / Thư mục | Chủ sở hữu chính (Owner) | Người Review chéo (Reviewer) | Quy tắc Phối hợp |
| :--- | :--- | :--- | :--- |
| **`learnguard-platform/infra/`**, **`deploy/digitalocean/`**, **`deploy/docker/`**, **`scripts/`**, **`.github/workflows/`**, **`runbooks/`** | **MLOPS** (Bạn — MLOps + DevOps) | **SWE1** hoặc **AIE** | Các Dev ứng dụng không tự ý sửa Dockerfile, Compose, Terraform hay workflow CI/CD; nếu cần thêm biến môi trường hoặc dependency hệ thống → mở issue/yêu cầu cho **MLOPS**. |
| **`learnguard-platform/deploy/ml/`**, **`learnguard-platform/tests/`** (Drift Monitor, Simulator, Behavioral Gate, Retrain Orchestrator) | **MLOPS** (phối hợp cùng **AIE**) | **AIE** | **MLOPS** sở hữu khung điều phối tự động & cổng release; **AIE** phối hợp tinh chỉnh ngưỡng đánh giá model/data. |
| **`BE-MLOPS/src/learnguard_backend/api/`**, **`db/`**, **`migrations/`**, **`observability.py`**, **`settings.py`** | **SWE1** (Backend Engineer) | **MLOPS** (kiểm tra DB/Security contract) & **SWE2** (kiểm tra API contract) | **SWE1** sở hữu M6 Auth/RBAC, M7 Persistence, Audit Logs, Student Activity API và Alembic migrations. Không bao giờ ghi vào bảng `ml_predictions`. |
| **`FE-MLOPS/src/`**, **`FE-MLOPS/tests/`**, **`FE-MLOPS/docs/API_CONTRACT.md`** | **SWE2** (Frontend Engineer) | **SWE1** (đối chiếu API) & **AIE** (đối chiếu hiển thị SHAP/Brief/Eval) | **SWE2** sở hữu toàn bộ giao diện React/TS, luồng đăng nhập, hàng đợi ưu tiên, hồ sơ sinh viên, chỉnh sửa/duyệt Brief, Chatbot UI, trang Đánh giá tự động & Nhật ký hệ thống. |
| **`Data-ML-MLOPS/src/learnguard/`** (`data/`, `ml/`, `evaluation/`) & **`BE-MLOPS/src/learnguard_backend/services/{llm,briefs,chat,chat_context}.py`** | **AIE** (AI / ML Engineer) | **MLOPS** (kiểm tra MLOps gates) & **SWE1** (kiểm tra tích hợp service backend) | **AIE** sở hữu pipeline dữ liệu M1–M3, huấn luyện/giải thích SHAP/benchmark M4, chấm điểm M5, dịch vụ LLM Brief/Chat M8 và 3 cổng đánh giá `learnguard evaluate {data,ml,llm}`. |
