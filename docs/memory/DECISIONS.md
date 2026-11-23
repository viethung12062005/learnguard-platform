# DECISIONS — Quyết định Kiến trúc & Kỹ thuật đã Chốt

> Tài liệu trí nhớ dài hạn của dự án **LearnGuard** (`learnguard-platform/docs/memory/DECISIONS.md`).
> Mọi quyết định có tác động kiến trúc phải gắn kèm ADR trong `docs/03-architecture/adr/`. Không ghi giá trị secret vào file này.

---

## 2026-11-04 (Phase 0–1 — Option A: Azure PaaS)

| ID | Quyết định | Lý do | Trạng thái |
|---|---|---|---|
| **D-001** | IaC dùng **Terraform** (`hashicorp/azurerm`), KHÔNG dùng Bicep | Người dùng yêu cầu (thay thế đề xuất Bicep ban đầu) | Đã chốt (Option A) |
| **D-002** | Repo hạ tầng = `learnguard-platform/` (git repo riêng); 3 app repo giữ nguyên vị trí, chỉ-đọc | "Chia repo mỗi cái 1 loại"; không đụng trực tiếp repo app | Đã chốt |
| **D-003** | Phạm vi repo hạ tầng gồm `infra/`, `deploy/`, `runbooks/`, `templates/`, `scripts/`, `tests/`, `.github/`, `docs/` | Chuẩn hóa quản trị tài liệu và hạ tầng tập trung | Đã chốt |
| **D-004** | Tổ chức tri thức & quy chuẩn chính thức trong `learnguard-platform/docs/` theo cấu trúc `00-*`..`06-*` + `memory/` | Thay cho thư mục rời bên ngoài, đồng bộ chuẩn kỹ thuật | Đã chốt |
| **D-005** | Trình tự làm việc: **requirement → architecture → implement** | Không viết script/Terraform trước khi có requirement + architecture | Đã chốt |
| **D-006** | ADR 0001–0007 giữ `Proposed` cho tới khi người dùng duyệt | Quy trình P0.4 | Đã chốt |
| **D-007** | Đăng ký provider `Microsoft.App` (`az rest` POST register) | Container Apps (Option A) cần provider này | Đã chốt (`Registered`) |
| **D-008** | Option A chọn **private networking (prod-like)**: PG + Key Vault private endpoint, CAE VNet-integrated; API/SWA giữ **public ingress** | Có quyền Network; data plane private, app ingress public | Đã chốt (Option A) |
| **D-009** | Option A CI/CD: **CI (GitHub-hosted) + CD (self-hosted runner tái dùng `az login`) là đường chính**; OIDC+UAMI cần Admin (ticket); Key Vault chỉ cất secret | Không tự tạo SP + không gán role trong `FSO-SandboxOps` | Đã chốt (Option A) |
| **D-010** | Option A **hoãn App Gateway** tới Phase 2 (~`$180–320/tháng`, không fix auth); dùng public ingress + IP restriction + CORS | Chi phí + không thay thế auth ứng dụng | Đã chốt (Option A) |
| **D-011** | **Không dùng AKS**; Option A giữ Container Apps + Container Apps Job (PaaS) | Workload theo sự kiện, scale-to-zero rẻ cho dev | Đã chốt (Option A) |
| **D-012** | **Môi trường dev Option A = SKU rẻ nhất**: CA consumption `min_replicas=0`, PG Burstable `B1ms`, ACR Basic, SWA Free | Tiết kiệm chi phí dev; tách rõ gap HA/backup cho prod | Đã chốt (Option A) |
| **D-013** | **Giảm chi phí PE ở dev Option A**: Key Vault giữ private endpoint; PG dùng delegated subnet (`snet-pg`); Storage hỗ trợ PE/firewall | Tối ưu chi phí PE mà vẫn giữ data plane private | Đã chốt (Option A) |
| **D-014** | **Option A Region = `eastasia`** (hoặc `southeastasia` nếu dịch vụ thiếu) | Chi phí thấp hơn cho dev | Đã chốt (Option A) |
| **D-015** | **Option A Dev dùng ACR admin user** (mật khẩu trong KV) thay repo-scoped token | Giảm thành phần khi bootstrap | Đã chốt (Option A) |
| **D-016** | **Bootstrap tách thành root Terraform riêng** `infra/bootstrap/` (local state) | Tránh chicken-and-egg với remote state | Đã chốt (Option A) |
| **D-017** | **Người dùng DUYỆT kiến trúc Azure v2** → ADR 0001–0007 chuyển **Accepted** | Triển khai & kiểm chứng thực tế Option A dev ngày 2026-11-05 | Đã chốt (Option A) |

---

## 2026-11-23 (Phase 2 — Dual-Cloud Portable Option B, CMU MLIP & Release Digests)

| ID | Quyết định | Lý do | Trạng thái |
|---|---|---|---|
| **D-018** | Áp dụng chiến lược **Cloud-Portable Dual-Option Deployment (Deploy-Where-Available)**: giữ **Option A (Azure PaaS — `ADR-0001..0007`)** là đích hoạt động song song, đồng thời bổ sung **Option B (DigitalOcean Droplet VM + VPC + Cloud Firewall + Docker Compose 2 mạng `lg_frontend_net` & `lg_backend_net`)** theo [ADR-0008](../03-architecture/adr/0008-cloud-migration-digitalocean-vm.md) & [`dual-cloud-strategy.md`](../03-architecture/dual-cloud-strategy.md) | Triển khai linh hoạt lên **một cloud đang có credit/tài khoản khả dụng** (Azure **hoặc** DigitalOcean) với 100% cùng container images, DB roles (`lg_api`, `lg_ml_writer`) và MLOps engine; không phải chạy hay trả phí hai cloud đồng thời | Đã chốt (Dual-Cloud) |
| **D-019** | Áp dụng bộ quy chuẩn kỹ thuật phần mềm, DevOps và MLOps dựa trên giáo trình **CMU MLIP** (Lectures 1–6): 4 Boundaries, `ASM ∧ SPEC => REQ`, Defensible Success Portfolio, 6-Clause Data Contract, 3 Control Points và Tháp kiểm thử 6 tầng ([`00-conventions.md`](../00-conventions.md)) | Chuẩn hóa thiết kế hệ thống AI production-like, phòng ngừa Proxy Trap, Data Cascades và Silent Success | Đã chốt |
| **D-020** | Xây dựng hệ thống CI/CD đa tầng trên GitHub Actions (`ci-platform.yml`, `ci-build-and-scan.yml`, `cd-digitalocean-prod.yml`, `mlops-drift-retrain.yml`) đẩy immutable images (`@sha256`) lên GHCR, quét Trivy (`exit-code: 1`), tự động backup DB trước khi deploy, chạy E2E smoke test và auto-rollback khi lỗi theo [ADR-0009](../03-architecture/adr/0009-cicd-pipeline-digitalocean-ghcr.md) | Kiểm chứng tự động cả 6 tầng kiểm thử, bảo mật supply chain và đảm bảo MTTR `< 60s` trên Option B | Đã chốt |
| **D-021** | Xây dựng pipeline phát hiện Data Drift, chẩn đoán Triage (phân biệt lỗi dữ liệu/ngữ nghĩa & `ASM-03` delayed ground truth với dịch chuyển phân bố thật theo Lec 4 Q19–Q22), cổng kiểm thử hành vi (`Behavioral Gate`: MFT, Invariance, Directional Expectation theo Lec 5), mô phỏng 5 kịch bản dữ liệu mới và tái huấn luyện Champion vs. Challenger theo [ADR-0010](../03-architecture/adr/0010-drift-detection-and-continual-retraining-pipeline.md) | Tự động hóa continual retraining khi có drift hợp lệ nhưng chặn retrain trên dữ liệu hỏng và ngăn model suy thoái lên production (Cloud-Agnostic cho cả Option A & Option B) | Đã chốt |
| **D-022** | Chuẩn hóa hệ thống tài liệu theo cấu trúc `docs/00-*`..`06-*` + `memory/`, bổ sung `dual-cloud-strategy.md`, `software-engineering-strategy.md`, `runbooks-index.md`, `production-readiness-gap.md` v4 (phản ánh đủ các khoảng trống baseline thực tế trong code) và kích hoạt `agent-harness` (`profile: learnguard`) (`ARC-05`) | Đảm bảo toàn bộ 4 kỹ sư và operators điều hướng nhất quán, có chiến lược gỡ nghẽn đường găng rõ ràng và kiểm chứng DoD bằng công cụ tự động | Đã chốt (`ARC-05` Done) |
| **D-023** | Khóa bộ **GHCR Immutable `@sha256` Digests** đã build & pass Trivy scan (`0` HIGH/CRITICAL CVEs) trong [`../../deploy/releases/prod.yaml`](../../deploy/releases/prod.yaml) và [`../../deploy/releases/dev.yaml`](../../deploy/releases/dev.yaml) (commit `e9f9c81`, hoàn tất `CICD-05`) | Đảm bảo triển khai lặp lại 100% từ commit nguồn cố định (`a2bae92`, `72c96cd`, `0f70e14`) | Đã chốt (`CICD-05` Done) |

---

## Các Quyết định Kiến trúc Kế thừa (Bất biến Xuyên suốt Dual-Cloud)

| Tham chiếu | Quyết định Cốt lõi | Trạng thái |
|---|---|---|
| **ADR-0001** | Không dùng AKS | Giữ nguyên |
| **Boundary Rule** | 3 repo app (`BE-MLOPS`, `Data-ML-MLOPS`, `FE-MLOPS`) **CHỈ ĐỌC** từ góc độ `learnguard-platform`; build/deploy nằm tại platform repo | Giữ nguyên |
| **ML Execution** | ML là batch/CLI job, không mở port HTTP công khai | Giữ nguyên |
| **DB Ownership** | PostgreSQL dùng chung; `lg_ml_writer` sở hữu & upsert `ml_predictions`, backend (`lg_api`) chỉ `SELECT` `ml_predictions` | Giữ nguyên |
