# DECISIONS — Quyết định đã chốt

> File này là "kiến thức LLM" → nằm NGOÀI repo hạ tầng (`D:\Learn-guard\docs\`), không commit.

## 2026-11-04 (Phiên Phase 0)

| ID | Quyết định | Lý do | Trạng thái |
|---|---|---|---|
| D-001 | IaC dùng **Terraform** (`hashicorp/azurerm`), KHÔNG dùng Bicep | Người dùng yêu cầu (thay thế đề xuất Bicep ban đầu) | Đã chốt |
| D-002 | Repo hạ tầng = subfolder mới `learnguard-platform/` (git repo riêng); 3 app repo giữ nguyên vị trí, chỉ-đọc | "Chia repo mỗi cái 1 loại"; không đụng repo app | Đã chốt |
| D-003 | Phạm vi COMMIT vào repo hạ tầng = `infra/` + `build/` + `deploy/` + `runbooks/` + `templates/` + `scripts/` + `.github/` | "Kiến thức LLM" không commit | Đã chốt |
| D-004 | Kiến thức/planning (memory, requirements, architecture, ADR, threat model, discovery report) nằm NGOÀI repo, tại `D:\Learn-guard\docs\` (local, không commit) | Người dùng yêu cầu | Đã chốt |
| D-005 | Trình tự làm việc: **requirement → architecture → implement** (không viết script/Terraform trước khi có requirement + architecture) | Người dùng yêu cầu | Đã chốt |
| D-006 | ADR 0001–0007 giữ trạng thái **Proposed** cho tới khi người dùng trả lời "duyệt" | Quy trình P0.4 | Đã chốt |
| D-007 | Đăng ký provider `Microsoft.App` (đã chạy `az rest` POST register; state `Registering`) | Container Apps cần provider này | Đã chốt (đang register) |
| D-008 | Chọn **private networking (prod-like)**: PG + Key Vault private endpoint, CAE VNet-integrated; API/SWA giữ **public ingress** | Có quyền Network; data plane private, app ingress public | Đã chốt |
| D-009 | CI/CD: **CI (GitHub-hosted) + CD (self-hosted runner tái dùng `az login`) là đường chính**; OIDC+UAMI cần Admin (ticket); **Key Vault chỉ cất secret, không cấp quyền** | Không tự tạo SP + không gán role; vẫn có CI/CD không cần Admin | Đã chốt |
| D-010 | **Hoãn App Gateway** tới Phase 2 (đắt ~$180–320/tháng, không fix auth); hiện dùng public ingress + IP restriction + CORS | Chi phí + không thay thế auth ứng dụng | Đã chốt |
| D-011 | **Không dùng VM/AKS**; giữ Container Apps + Container Apps Job (PaaS). Lý do: workload theo sự kiện, VM trả tiền 24/7 kể cả khi rảnh → đắt hơn cho dev | "Rẻ nhất có thể cho dev" + workload shape | Đã chốt |
| D-012 | **Môi trường dev = SKU rẻ nhất**: CA consumption min_replicas=0, PG Burstable B1ms, ACR Basic, SWA Free, **chấp nhận không HA / không geo-backup** ở dev. Prod sẽ khác (G-04/G-05) | "Rẻ nhất có thể cho môi trường dev thôi" | Đã chốt |
| D-013 | **Giảm chi phí private endpoint ở dev**: Key Vault giữ private endpoint; Azure Files dùng storage firewall + service endpoint (miễn phí); PostgreSQL dùng delegated subnet (không tốn phí PE) | Private endpoint ~$7/tháng/cái, đắt hơn cả PG B1ms | Đã chốt |
| D-014 | **Region = `eastasia`** cho dev (rẻ hơn `southeastasia`); fallback `southeastasia` nếu thiếu dịch vụ | Người dùng: "east asia mới có resource rẻ nhất" | Đã chốt — **cần xác minh** Container Apps có ở eastasia |
| D-015 | **Dev dùng ACR admin user** (mật khẩu trong Key Vault) thay repo-scoped token; prod chuyển UAMI+AcrPull/token | Giảm thành phần, thuộc tính provider chắc chắn tồn tại | Đã chốt (dev) |
| D-016 | **Bootstrap tách thành root Terraform riêng** `infra/bootstrap/` (local state). Không để chung với `env/dev` | Chicken-and-egg: state của env nằm trong storage do chính env tạo | Đã chốt |
| D-017 | **Người dùng DUYỆT kiến trúc v2** → ADR 0001–0007 chuyển **Accepted**; bắt đầu Phase 1 (viết code, chưa apply) | "Oke rẻ nhất cho dev giúp tôi nhé. Hãy triển khai luôn" | Đã chốt |

## 2026-11-23 (Phiên Phase 2 — DigitalOcean Production Migration & CMU MLIP Drift/Retraining)

| ID | Quyết định | Lý do | Trạng thái |
|---|---|---|---|
| D-018 | Chuyển dịch hạ tầng đích từ Azure Container Apps sang **DigitalOcean Droplet VM** (Ubuntu 24.04 LTS + VPC + Cloud Firewall + Docker Compose Production Stack 2 mạng cô lập `lg_frontend_net` & `lg_backend_net`) theo [ADR-0008](../adr/0008-cloud-migration-digitalocean-vm.md) | Loại bỏ giới hạn quyền Azure RBAC/AAD, giữ mô hình mạng DMZ vs Internal Data Plane, phân quyền DB 2 role (`lg_api`, `lg_ml_writer`) và chia sẻ volume `eval-report.v1` hiệu quả | Đã chốt |
| D-019 | Áp dụng bộ quy chuẩn kỹ thuật phần mềm, DevOps và MLOps dựa trên giáo trình **CMU MLIP** (Lectures 1–6): 4 Boundaries, `ASM ∧ SPEC => REQ`, Defensible Success Portfolio, 6-Clause Data Contract, 3 Control Points và Tháp kiểm thử 6 tầng (`docs/conventions/software-engineering-and-mlops-conventions.md`) | Chuẩn hóa thiết kế hệ thống AI production-like, phòng ngừa Proxy Trap, Data Cascades và Silent Success | Đã chốt |
| D-020 | Xây dựng hệ thống CI/CD đa tầng trên GitHub Actions (`ci-platform.yml`, `ci-build-and-scan.yml`, `cd-digitalocean-prod.yml`, `mlops-drift-retrain.yml`) đẩy immutable images (`@sha256`) lên GHCR, tự động backup DB trước khi deploy, chạy E2E smoke test và auto-rollback khi lỗi theo [ADR-0009](../adr/0009-cicd-pipeline-digitalocean-ghcr.md) | Kiểm chứng tự động cả 6 tầng kiểm thử, quét lỗ hổng Trivy, và đảm bảo MTTR < 60s khi deploy lỗi | Đã chốt |
| D-021 | Xây dựng pipeline phát hiện Data Drift, chẩn đoán Triage (phân biệt lỗi dữ liệu/ngữ nghĩa với dịch chuyển phân bố thật theo Lec 4 Q19–Q22), cổng kiểm thử hành vi (`Behavioral Gate`: MFT, Invariance, Directional Expectation theo Lec 5), mô phỏng 5 kịch bản dữ liệu mới và tái huấn luyện Champion vs. Challenger theo [ADR-0010](../adr/0010-drift-detection-and-continual-retraining-pipeline.md) | Tự động hóa continual retraining khi có drift hợp lệ nhưng chặn retrain trên dữ liệu hỏng và ngăn model suy thoái lên production | Đã chốt |

## Các quyết định kế thừa (từ AGENT.md / PROJECT_CONTEXT, chưa mở lại)

| ID | Quyết định | Trạng thái |
|---|---|---|
| ADR-0001 | Không dùng AKS (đã loại) | Chốt từ trước — giữ |
| — | 3 repo app CHỈ ĐỌC; build/deploy nằm ở platform repo | Chốt từ trước — giữ |
| — | ML là batch (job), không phải service; không mở port | Chốt từ trước — giữ |
| — | PostgreSQL dùng chung; ml-data GHI `ml_predictions`, backend chỉ SELECT | Chốt từ trước — giữ |
