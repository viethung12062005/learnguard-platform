# LearnGuard — Unified Operator Runbooks Index (Dual-Cloud: Option A & Option B)

> **Phiên bản:** 2.0 (2026-11-23)
> **Mục đích:** Điểm điều hướng duy nhất cho mọi quy trình triển khai, cấu hình CI/CD, giám sát Drift/Retraining và ứng phó sự cố trên **cả Option A (Azure PaaS)** và **Option B (DigitalOcean VM)**.
> **Lưu ý Dual-Cloud:** Theo chiến lược **Deploy-Where-Available** ([`../03-architecture/dual-cloud-strategy.md`](../03-architecture/dual-cloud-strategy.md)), operator chỉ chạy runbook của **cloud đang sử dụng tại thời điểm triển khai** (Azure **hoặc** DigitalOcean).

---

## 1. Bảng Tra cứu Nhanh theo Tình huống Vận hành (Operator Quick-Lookup)

| Bạn muốn làm gì? | Cloud / Phạm vi | Runbook Cần mở | Thành phần / Lệnh Chính |
| :--- | :---: | :--- | :--- |
| **Triển khai mới lên DigitalOcean Droplet VM** | Option B (DO) | [`../../runbooks/deploy-digitalocean.md`](../../runbooks/deploy-digitalocean.md) | `infra/digitalocean/` Terraform hoặc `scripts/do/bootstrap-vm.sh` → `.env` → `scripts/cd/deploy-do.sh` → `smoke-test.sh` |
| **Triển khai mới lên Azure PaaS (dev sandbox)** | Option A (Azure) | [`../../runbooks/deploy-dev.md`](../../runbooks/deploy-dev.md) | `infra/bootstrap/` → `infra/env/dev/` + `check_plan.py` → `deploy/docker/build-push.ps1` → SWA deploy |
| **Thiết lập CD GitHub Actions cho Azure** | Option A (Azure) | [`../../runbooks/cd-setup.md`](../../runbooks/cd-setup.md) | Self-hosted Windows runner (`az login`) hoặc OIDC/UAMI (`cd-dev-infra.yml`, `cd-dev-app.yml`, `cd-dev-frontend.yml`) |
| **Gửi yêu cầu quyền/policy cho Azure Tenant Admin** | Option A (Azure) | [`../../runbooks/admin-requests.md`](../../runbooks/admin-requests.md) | Ticket cấp UAMI + Contributor(RG), kiểm tra policy `FSO-SZ`, ACR Premium (nếu cần PE) |
| **Kiểm tra Data Drift, Chẩn đoán Triage & Retrain** | Cả Option A & B | [`../../runbooks/drift-and-retraining-runbook.md`](../../runbooks/drift-and-retraining-runbook.md) | `deploy/ml/retrain_pipeline.py` (`--mode auto` / `--mode simulate --scenario ...`), `mlops-drift-retrain.yml` |
| **Rollback App/Model, Backup/Restore DB, Sự cố LLM** | Option B & Lõi | [`../../runbooks/incident-and-rollback.md`](../../runbooks/incident-and-rollback.md) | `rollback-do.sh` (`< 60s`), `retrain_pipeline.py --mode rollback`, `backup-db.sh`, `restore-db.sh`, `ollama` fallback |

---

## 2. Chi tiết Các Runbook Option A — Azure PaaS

1. **[`runbooks/deploy-dev.md`](../../runbooks/deploy-dev.md)** *(Triển khai Azure Dev từ đầu đến cuối bằng PowerShell & Terraform)*
   - Khởi tạo `infra/bootstrap/` (storage state) và chuyển `infra/env/dev/` sang remote state (lưu ý ngoại lệ policy `FSO-SZ` tại [`../memory/AZURE_CONSTRAINTS.md`](../memory/AZURE_CONSTRAINTS.md)).
   - Chạy bắt buộc guardrail `scripts/guardrails/check_plan.py` trước mọi `terraform apply`.
   - Upload dataset OULAD lên Azure Files `lgdata`, build/push digest `@sha256` qua `deploy/docker/build-push.ps1`, triển khai `ca-lg-dev-api` / `caj-lg-dev-ml` và Static Web App `swa-lg-dev`.
2. **[`runbooks/cd-setup.md`](../../runbooks/cd-setup.md)** *(Cấu hình Pipeline CD cho Azure)*
   - Hướng dẫn cài đặt Windows self-hosted runner (`--labels learnguard`) tái dùng phiên `az login` (không cần Admin), khai báo GitHub Variables/Secrets (`SWA_API_TOKEN`, `APPS_READ_TOKEN`), và lộ trình chuyển sang OIDC (`cd-dev-infra-hosted.yml`) khi có UAMI.
3. **[`runbooks/admin-requests.md`](../../runbooks/admin-requests.md)** *(Mẫu Ticket Gửi Azure Tenant Admin)*
   - Danh sách các tác vụ bị chặn bởi `FSO-SandboxOps` (`notActions`: `Microsoft.Authorization/*/Write`, `microsoft.aadiam/*/write`) đã xác minh tại [`azure-permissions-report.md`](azure-permissions-report.md).
4. **Tài liệu Tham khảo Lịch sử Azure v2 (Đã kiểm chứng thực tế ngày 2026-11-05):**
   - [`legacy-runbooks/deploy-runbook.md`](legacy-runbooks/deploy-runbook.md) — Toàn bộ bước thao tác qua Jump VM `vm-az-lg-jump`, `deploy/db/seed.sh`, và Proxy SOCKS.
   - [`legacy-runbooks/commands-only.md`](legacy-runbooks/commands-only.md) — Bản rút gọn chỉ chứa lệnh copy-paste.

---

## 3. Chi tiết Các Runbook Option B — DigitalOcean VM & MLOps Chung

1. **[`runbooks/deploy-digitalocean.md`](../../runbooks/deploy-digitalocean.md)** *(Triển khai Production trên DigitalOcean Droplet VM)*
   - **Bước 1:** Provision VPC, Droplet Ubuntu 24.04 (`s-4vcpu-8gb`), Block Storage 50 GiB (`/opt/learnguard/data`) và Cloud Firewall bằng `infra/digitalocean/` Terraform (hoặc `scripts/do/bootstrap-vm.sh` trên Droplet có sẵn).
   - **Bước 2:** Sinh mật khẩu ngẫu nhiên cho `lgadmin`, `lg_api`, `lg_ml_writer`, `JWT_SECRET` vào `/opt/learnguard/deploy/digitalocean/.env` (`chmod 600`) và cấu hình secrets trong GitHub Environment `production` (`DO_HOST`, `DO_USER`, `DO_PORT`, `DO_SSH_KEY`, `GHCR_READ_TOKEN`).
   - **Bước 3–5:** Đồng bộ 7 OULAD CSVs, chạy `ml-worker --mode force-retrain` lần đầu, kích hoạt `cd-digitalocean-prod.yml` hoặc `scripts/cd/deploy-do.sh` và xác minh qua `smoke-test.sh`.
2. **[`runbooks/drift-and-retraining-runbook.md`](../../runbooks/drift-and-retraining-runbook.md)** *(Giám sát Data Drift, Triage & Retraining — Cloud-Agnostic)*
   - Thực thi **4-State Drift Triage Protocol** theo CMU MLIP Lec 4 Q20 (`DATA_QUALITY_OR_SEMANTIC_FAILURE`, `NO_DRIFT`, `WARN_MONITOR` kèm `ASM-03`, `DRIFT_RETRAIN_RECOMMENDED`).
   - Hướng dẫn đọc `drift-report.v1`, kiểm định 3 cổng Champion-vs-Challenger (Data + ML + Behavioral `MFT`/`INV`/`DIR`) và chạy 5 kịch bản mô phỏng cô lập với `data_simulator.py`.
3. **[`runbooks/incident-and-rollback.md`](../../runbooks/incident-and-rollback.md)** *(Ứng phó Sự cố, Rollback & Khôi phục Dữ liệu)*
   - **Container App Rollback (`RTO < 60s`):** `scripts/cd/rollback-do.sh` khôi phục từ `last_good_release.env`.
   - **ML Model Rollback (`RTO < 3m`):** `retrain_pipeline.py --mode rollback --target-release-id <PREVIOUS_RELEASE_ID>` xác thực `verify-release`, cập nhật nguyên tử `active_release.json` và chấm lại `ml_predictions`.
   - **Database Backup & Restore (`RTO < 5m`):** `scripts/cd/backup-db.sh` (`.sql.gz` + `.sha256`) và `scripts/cd/restore-db.sh` tự động chạy lại `init-db.sh` để giữ nguyên quyền `lg_api` / `lg_ml_writer`.
   - **LLM Failover (`RTO = 0s`):** Bật profile `llm-fallback` (`ollama/qwen2.5:3b`) hoặc tự động degrade sang template `fallback_review`.

---

## 4. Quy tắc An toàn Vận hành Chung (Cả 2 Cloud)

- **Không tự ý xóa dữ liệu hoặc state:** Nghiêm cấm `terraform destroy` trong `infra/bootstrap/` (Option A) hoặc xóa Block Storage Volume chứa `pg_data` / `model-releases` / `evaluations` (Option B) khi chưa có bản sao lưu đã verify `sha256sum --check`.
- **Luôn sao lưu trước khi nâng cấp DB/Schema:** Chạy `backup-db.sh` (Option B) hoặc kiểm tra snapshot PG Flexible (Option A) trước khi chạy `alembic upgrade head`.
- **Ghim phiên bản bất biến:** Mọi image triển khai trên production phải dùng `@sha256:...` đã qua Trivy scan (tham chiếu [`../../deploy/releases/prod.yaml`](../../deploy/releases/prod.yaml)).
- **Không lộ bí mật:** Không ghi `.env`, `terraform.tfvars`, `*.tfstate`, SSH keys, hay connection strings vào log CI hoặc tài liệu Markdown.
