# Kế hoạch Tổng thể Dự án & Phân công Công việc cho 4 Thành viên (Master Project Plan)

> **Phiên bản:** 3.0 (2026-11-23)
> **Phương pháp lập kế hoạch:** Chuẩn hóa theo `smart-hospital-platform` (phân rã theo vai trò chuyên trách, cổng phê duyệt `G1`–`G4`, mỗi task `2–6 giờ`, tiêu chí `Done when` kiểm chứng bằng lệnh thật, và danh sách ưu tiên cắt giảm MoSCoW).
> **Nguồn sự thật duy nhất (Single Source of Truth):** [backlog.csv](backlog.csv) — mọi bảng tổng hợp ở file này, [by-person/*.md](by-person/MLOPS.md) và [dod-audit.md](dod-audit.md) khớp **100%** với `backlog.csv`.

---

## 1. Chiến lược Triển khai Cloud-Portable Dual-Option (**Deploy-Where-Available**)

> [!IMPORTANT]
> **Nguyên tắc "2 Cloud" — Không chạy song song để tránh tốn chi phí kép:**
> Dự án duy trì **tính khả chuyển đa đám mây (Cloud-Portable Dual-Option Deployment)**:
> - **Option A — Azure PaaS** (`infra/env/dev/` + `.github/workflows/cd-dev-*.yml` + [azure-target-architecture.md](../03-architecture/azure-target-architecture.md) + [AZURE_CONSTRAINTS.md](../memory/AZURE_CONSTRAINTS.md) cấm `azurerm_role_assignment`).
> - **Option B — DigitalOcean Droplet VM** (`infra/digitalocean/` + `deploy/digitalocean/` + `.github/workflows/cd-digitalocean-prod.yml` + [digitalocean-target-architecture.md](../03-architecture/digitalocean-target-architecture.md)).
>
> `OPS-06` (DigitalOcean VM) và `OPS-08` (Azure PaaS parity) là **hai phương án triển khai thay thế (alternative target tracks)** — **KHÔNG yêu cầu vận hành hoặc trả phí đồng thời cả 2 cloud**. Nhóm giữ IaC + CI/CD sẵn sàng cho cả hai phương án và triển khai live trên **nhà cung cấp nào hiện khả dụng** với **0 thay đổi mã nguồn ứng dụng**.

---

## 2. Tài liệu Đầu vào & Liên kết Chuẩn

| Nội dung cần nắm | Đường dẫn Tài liệu |
| :--- | :--- |
| Bài toán, Dữ liệu OULAD & Phạm vi Cấm (Scope) | [01-business-analysis/problem-and-scope.md](../01-business-analysis/problem-and-scope.md) |
| Giao thức Đo lường Giá trị Sản phẩm (`AI-07`) | [01-business-analysis/product-value-protocol.md](../01-business-analysis/product-value-protocol.md) |
| Quy chuẩn SE, DevOps & MLOps (CMU MLIP Lec 1–6) | [00-conventions.md](../00-conventions.md) · [00-delivery-process.md](../00-delivery-process.md) · [00-workflow.md](../00-workflow.md) |
| Hiện trạng Mã nguồn 4 Kho & Yêu cầu `FR`/`NFR` | [02-requirements/app-facts.md](../02-requirements/app-facts.md) · [02-requirements/requirements.md](../02-requirements/requirements.md) · [02-requirements/traceability.md](../02-requirements/traceability.md) |
| Kiến trúc Đích, ADRs (0001–0010) & Drift Spec | [03-architecture/digitalocean-target-architecture.md](../03-architecture/digitalocean-target-architecture.md) · [03-architecture/azure-target-architecture.md](../03-architecture/azure-target-architecture.md) · [03-architecture/drift-and-retraining-specification.md](../03-architecture/drift-and-retraining-specification.md) |
| Hợp đồng Giao tiếp (DB, API, Prediction Batch) | [DB_CONTRACT.md](../../../BE-MLOPS/docs/DB_CONTRACT.md) · [API_CONTRACT.md](../../../FE-MLOPS/docs/API_CONTRACT.md) · [M5_PREDICTION_BATCH.md](../../../Data-ML-MLOPS/docs/M5_PREDICTION_BATCH.md) |
| Chiến lược Kiểm thử 6 Tầng & 4 Cổng Chất lượng | [06-testing/test-strategy-and-gates.md](../06-testing/test-strategy-and-gates.md) |
| **Kế hoạch Chi tiết 4 Thành viên & Kiểm toán DoD** | **[MLOPS](by-person/MLOPS.md)** · **[SWE1](by-person/SWE1.md)** · **[SWE2](by-person/SWE2.md)** · **[AIE](by-person/AIE.md)** · [backlog.csv](backlog.csv) · [dod-audit.md](dod-audit.md) |

---

## 3. Phân vai & Lỗ hổng Thực tế Đang Đóng của 4 Thành viên

| Mã Vai trò | Kho Sở hữu Chính | Baseline Đã Xong | Lỗ hổng Thực tế (In-Scope Gaps) Cần Hoàn tất |
| :--- | :--- | :--- | :--- |
| **`MLOPS`** | `learnguard-platform` (`e9f9c81`) | Quy chuẩn CMU MLIP, ADRs 0008–0010, Dockerfiles/Compose/Nginx, Postgres 2 roles, Drift Monitor + Behavioral Gate + Simulator + Retrain Pipeline, 4/4 GitHub Actions GREEN + GHCR `@sha256` (`CICD-05`), chuẩn hóa docs `00-*..06-*` (`ARC-05`). | Triển khai live trên **cloud khả dụng** (`OPS-06` DO VM **hoặc** `OPS-08` Azure PaaS parity), chạy diễn tập GameDay Safeguard & Rollback (`OPS-07`). |
| **`SWE1`** | `BE-MLOPS` (`a2bae92`) | App factory, `/health`, Alembic, `/predictions*`, `/activity`, `/briefs*`, `/briefs/chat/*`, `/evaluations*`, `/audit-logs`. | • `BE-08`–`BE-10`: Thực thi JWT Auth (`api/auth.py` đang `NotImplementedError`), RBAC, thay `system@learnguard.local`.<br>• `BE-11`: Thực thi `observability.py` (JSON logs + Prometheus `/metrics`).<br>• `BE-12`–`BE-13`: Cache `/activity`, expose `eval_behavioral.json` / `drift-report.v1` / `active_release.json`, DB `503` & `lg_api` read-only tests.<br>• **`BE-14`**: Thêm `feedback` vào `BriefDecisionRequestBody`, thêm `GET /predictions/{m}/{p}/{s}/brief`, nạp `advisor_guidelines.md` + deterministic guardrails vào one-shot `AdvisorBriefService.generate()`. |
| **`SWE2`** | `FE-MLOPS` (`0f70e14`) | API client + Mock, AppShell, Overview, Advisor Queue, StudentDetail (SHAP + 4-week activity + Edit Brief), Chat Drawer, Evaluations & Audit UI. | • `FE-09`: Thay mock `login()` (`src/api/index.ts:82`) bằng Real JWT Auth.<br>• `FE-10`: Surface `eval_behavioral.json`, `drift-report.v1`, `active_release.json`, LLM latency/cost trên `EvaluationsPage.tsx`.<br>• `FE-11`–`FE-12`: Component/contract tests (`run.mjs`/Vitest), a11y + Playwright E2E Human Oversight.<br>• **`FE-13`**: Nối nút **Accept / Reject + Feedback** (`saveBriefDecision`) & tải lại active brief trên `StudentDetailPage.tsx`; bỏ hardcode 5/7 học phần & 3/4 kỳ ở `AdvisorDashboardPage.tsx:51-65` sang đọc động từ `/predictions/stats`; thêm badge triage. |
| **`AIE`** | `Data-ML-MLOPS` (`72c96cd`) & `BE-MLOPS/services/{llm,briefs,chat*}` | M1–M3 (`27,535` cohort, `LeakageAuditor` 16 probes), M4 Logistic v2 + Linear SHAP (`0.810348`), M5 batch upsert, LiteLLM + Ollama failover, `llm_gate.py` (`163 passed`). | • **`ML-11`**: Mở rộng `ml_gate.py` từ `gender` sang **6 fairness slices** (`gender`, `code_module`, `age_band`, `disability`, `imd_band`, `highest_education`) + `ECE`/`Brier` calibration + FPR & multi-K (`10%/20%/30%`) curves.<br>• **`ML-12`**: Phân tích FN tuần 4 + đánh giá `HistGradientBoostingClassifier` có hiệu chỉnh + TreeSHAP/permutation **chỉ trên `validation` `2014B`** (không dùng lại `2014J`).<br>• **`AI-06`**: Hiệu chỉnh `llm_judge.py` trên 30 dual-human golden briefs + chấm tuân thủ `advisor_guidelines` + red-team prompt-injection trên Chat Copilot.<br>• **`AI-07`**: Thực thi [product-value-protocol.md](../01-business-analysis/product-value-protocol.md) trên 10 case studies. |

---

## 4. Phân bổ Khối lượng Công việc (Workload Summary — 100% Parity với `backlog.csv`)

| Thành viên | Vai trò | Tổng Task | `Done` | `In Progress` | `Todo` | Tổng Giờ | Giờ Đã xong | Giờ Còn lại |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`MLOPS`** | MLOps + DevOps + Architect | **23** | **20** | **0** | **3** | **84h** | 72h | **12h** |
| **`SWE1`** | Backend SWE (`BE-MLOPS`) | **14** | **7** | **1** | **6** | **50h** | 26h | **24h** |
| **`SWE2`** | Frontend SWE (`FE-MLOPS`) | **13** | **8** | **1** | **4** | **46h** | 26h | **20h** |
| **`AIE`** | AI / ML Engineer (`Data-ML-MLOPS` + LLM) | **14** | **10** | **1** | **3** | **50h** | 34h | **16h** |
| **Tổng cộng** | **4 Thành viên** | **64** | **45** | **3** | **16** | **230h** | **158h** | **72h** |

---

## 5. Thứ tự Ưu tiên & Cắt giảm Phạm vi (MoSCoW Cut Order)

1. **MUST (Không bao giờ cắt):**
   - M1–M3 chống rò rỉ thời gian (`cutoff_day=27`, 16 probes = 100%) & khóa single-use `2014J`.
   - Logistic v2 + Linear SHAP + Top-20% Alert Budget + `ML-11` (6-slice fairness & calibration).
   - `BE-08`..`BE-10` (JWT Auth + RBAC + thay `system@learnguard.local`), `BE-14` (one-shot `advisor_guidelines.md` + guardrails + `feedback` + reload brief), `FE-09`, `FE-13` (Accept/Reject/Feedback UI + động 7 học phần/4 kỳ).
   - Triển khai live trên **1 trong 2 cloud khả dụng** (`OPS-06` DO VM hoặc `OPS-08` Azure PaaS) + CI/CD & Drift/Retrain Simulator.
2. **SHOULD (Hoàn thành để đạt điểm tối đa Chủ đề 4 & CMU MLIP):**
   - `BE-11` (`observability.py` + Prometheus `/metrics`), `BE-12`, `BE-13`, `FE-10` (`behavioral` + Drift + Telemetry UI), `FE-11`, `FE-12` (Playwright E2E + a11y).
   - `ML-12` (FN cohort + HistGB/TreeSHAP trên `2014B`), `AI-06` (30 dual-human golden briefs + Chat red-team), `AI-07` (Product Value Benchmark), `OPS-07` (GameDay Drills).
3. **COULD (Có thể giản lược nếu tài nguyên hạn chế):**
   - Chạy Ollama `qwen2.5:3b` 24/7 trên VM RAM nhỏ (giữ deterministic `fallback_review` + OpenRouter API để tiết kiệm RAM).
   - Vận hành song song cả 2 cloud cùng lúc (không cần thiết theo nguyên tắc **Deploy-Where-Available**).
