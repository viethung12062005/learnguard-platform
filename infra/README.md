# LearnGuard — Infrastructure (Terraform)

Hạ tầng Azure cho LearnGuard, môi trường **dev** (SKU rẻ nhất, region `eastasia`).

## Kiến trúc tóm tắt

```
RG learn-guard-dev (eastasia)
├── VNet 10.20.0.0/16
│   ├── snet-cae  10.20.0.0/23  delegated Microsoft.App/environments
│   ├── snet-pg   10.20.2.0/24  delegated Microsoft.DBforPostgreSQL/flexibleServers
│   └── snet-pe   10.20.3.0/24  private endpoints
├── Log Analytics + Application Insights
├── Key Vault (+ private endpoint, access policy)
├── PostgreSQL Flexible B1ms (private, no public), DB `learnguard`
├── ACR Basic
└── Container Apps Environment (VNet-integrated)
    ├── Container App  API      (khi deploy_apps = true)
    └── Container App Job ml-batch (khi deploy_apps = true)
```

Data plane private (PG/Vault), app ingress public — xem `docs/architecture/target-architecture.md`.

## Yêu cầu

| Công cụ | Phiên bản | Ghi chú |
|---|---|---|
| Terraform | >= 1.9 | **Chưa cài trên máy này** |
| Azure CLI | >= 2.60 | đã có, đã `az login` |
| Python | >= 3.10 | cho guardrail script |

Cài Terraform trên Windows (chọn 1):

```powershell
winget install --id Hashicorp.Terraform -e
# hoặc: choco install terraform
```

Kiểm tra:

```powershell
terraform version
az account show --query "{sub:name, user:user.name}" -o table
```

## Chạy lần đầu

> Hướng dẫn chi tiết từng lệnh (gồm xử lý PATH, provider mirror do mạng reset IPv6,
> kiểm tra sau apply): [`runbooks/deploy-dev.md`](../runbooks/deploy-dev.md).
> Phần dưới chỉ là bản tóm tắt.

```powershell
cd learnguard-platform\infra\env\dev

# 1. Cấu hình
Copy-Item terraform.tfvars.example terraform.tfvars
#    -> sửa nếu cần (location, subscription_id, operator_ip_cidr)

# 2. Init
terraform init

# 3. Xem plan + chạy guardrail (KHÔNG apply nếu guardrail fail)
bash ../../../scripts/guardrails/plan-and-check.sh .

# 4. Apply
terraform apply tfplan
```

`deploy_apps = false` ở lần đầu → chỉ dựng hạ tầng. Xem output:

```powershell
terraform output
```

## Bật ứng dụng (sau khi có image)

```powershell
# login ACR
az acr login --name $(terraform output -raw acr_name)

# build & push (xem build/ — làm ở bước sau)
# rồi đặt image theo DIGEST vào terraform.tfvars:
#   deploy_apps = true
#   api_image   = "<acr>.azurecr.io/learnguard-api@sha256:..."
#   job_image   = "<acr>.azurecr.io/learnguard-ml@sha256:..."

terraform plan -out=tfplan
terraform apply tfplan
```

## Bootstrap + remote state (khuyến nghị)

Bootstrap là **root Terraform riêng** tại [`infra/bootstrap/`](bootstrap/README.md) — dùng
local state theo thiết kế, vì state của các env được lưu trong storage account do chính
nó tạo ra (chicken-and-egg).

```powershell
cd infra\bootstrap
terraform init
terraform apply
terraform output backend_config
```

Copy output vào `infra/env/dev/backend.hcl`, bỏ comment block `backend` trong
`infra/env/dev/backend.tf`, rồi `terraform init -backend-config=backend.hcl -migrate-state`.

Lý do: state chứa mật khẩu PostgreSQL. Không được commit, không nên chỉ nằm trên 1 máy.

## Guardrail

`scripts/guardrails/check_plan.py` fail nếu plan chứa:
`azurerm_role_assignment`, `azurerm_role_definition`, `azurerm_policy_assignment`,
`azurerm_management_lock`, hoặc bất kỳ `azurerm_role_*` / `azurerm_policy_*`.

Vì role `FSO-SandboxOps` chặn `Microsoft.Authorization/*/Write`.

## Ước lượng chi phí dev

| Thành phần | ~ USD/tháng |
|---|---|
| PostgreSQL Flexible B1ms + 32 GiB | 13–15 |
| Container Apps (min 0) + Job | 1–5 |
| ACR Basic | 5 |
| Key Vault + private endpoint | 8 |
| Storage (state + Files sau này) | 1–2 |
| Log Analytics (quota 0.5 GB/ngày) | 2–4 |
| **Tổng** | **~30–39** |

> Số liệu để tham khảo, **cần xác minh** bằng Azure Pricing Calculator + `az consumption usage list` sau vài ngày.
> Container Apps/PostgreSQL ở `eastasia` rẻ hơn `southeastasia` nhưng **cần xác minh dịch vụ có sẵn** ở region này.

## Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `LocationNotAvailableForResourceType` (Microsoft.App) | Container Apps chưa có ở `eastasia` | đổi `location = "southeastasia"` |
| Tạo secret KV lỗi 403 `ForbiddenByConnection` | IP hiện tại không nằm trong ACL | đặt `operator_ip_cidr` đúng, hoặc kiểm tra `terraform output operator_ip_used` |
| PostgreSQL tạo lỗi do NSG | NSG chặn traffic nội bộ của dịch vụ | bỏ `azurerm_subnet_network_security_group_association.pg`, apply lại, rồi thêm rule chính xác |
| Container Apps Environment tạo lỗi | Subnet chưa delegate / NSG chặn | kiểm tra delegation `Microsoft.App/environments` và NSG `snet-cae` |
| `private_dns_zone` tên sai | Tên zone PG khác theo loại kết nối | xem thông báo lỗi của Azure; zone đúng thường là `private.postgres.database.azure.com` |

## Chưa làm (biết trước để không tưởng là xong)

- Frontend Static Web App
- Azure Files + mount vào ML job
- Tạo 2 DB user (`lg_api`, `lg_ml_writer`) — phải chạy từ trong VNet
- Alert rules / SLO / dashboard
- CI/CD pipeline (build + push)
- Prod environment

Chi tiết: `docs/architecture/production-readiness-gap.md` (file kiến thức, ngoài repo).
