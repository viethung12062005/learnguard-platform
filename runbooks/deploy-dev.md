# Runbook — Deploy môi trường dev (Windows / PowerShell)

> Region `eastasia`, SKU rẻ nhất. Toàn bộ lệnh dưới đây chạy trong **PowerShell**.
> Chạy đúng thứ tự. Không bỏ qua guardrail.

---

## 0. Chuẩn bị một lần

### 0.1 Đưa `terraform` vào PATH

winget cài Terraform nhưng phiên PowerShell hiện tại chưa thấy. Mở PowerShell **mới**, kiểm tra:

```powershell
terraform version
```

Nếu vẫn "not recognized":

```powershell
$tfDir = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Hashicorp.Terraform_Microsoft.Winget.Source_8wekyb3d8bbwe"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$tfDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$tfDir", "User")
}
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
terraform version
```

### 0.2 Cấu hình provider mirror (do mạng reset IPv6)

`registry.terraform.io` bị ngắt liên tục trên máy này. Tạo file `%APPDATA%\terraform.rc`
để Terraform ưu tiên mirror cục bộ, fallback sang mạng khi cần:

```powershell
$rc = "$env:APPDATA\terraform.rc"
$content = @"
provider_installation {
  filesystem_mirror {
    path    = "C:/Users/vieth/.lg-terraform-mirror"
    include = ["registry.terraform.io/*/*"]
  }
  direct {
  }
}
"@
[System.IO.File]::WriteAllText($rc, $content, (New-Object System.Text.UTF8Encoding($false)))
```

> Mirror hiện có: azurerm 4.81.0, random 3.9.1, http 3.4.5.
> Nếu sau này thêm provider mới mà tải lỗi, xoá `terraform.rc` tạm rồi init lại.

### 0.3 Kiểm tra Azure

```powershell
az account show --query "{sub:name, user:user.name}" -o table
az provider show -n Microsoft.App --query registrationState -o tsv   # phải: Registered
```

---

## 1. Bootstrap — tạo nơi lưu Terraform state

Root riêng, dùng local state (lý do: xem `infra/bootstrap/README.md`).

```powershell
cd D:\Learn-guard\learnguard-platform\infra\bootstrap

terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

⏱ ~1 phút. Kết quả mong đợi: 5 resource (RG, storage account, container, random).

Lấy cấu hình backend:

```powershell
terraform output backend_config
```

Ghi lại 3 giá trị: `resource_group_name`, `storage_account_name`, `container_name`.

> ❗ **Không bao giờ chạy `terraform destroy` trong thư mục này** — sẽ mất state của mọi môi trường.

---

## 2. Chuyển `env/dev` sang remote state

### 2.1 Tạo file `backend.hcl`

```powershell
cd D:\Learn-guard\learnguard-platform\infra\env\dev

@'
resource_group_name  = "learn-guard-tfstate"
storage_account_name = "<DAN_TU_OUTPUT>"
container_name       = "tfstate"
key                  = "dev.terraform.tfstate"
'@ | Set-Content -Path backend.hcl -Encoding ascii
```

Thay `<DAN_TU_OUTPUT>` bằng `storage_account_name` ở bước 1.

### 2.2 Bật backend

Mở `infra/env/dev/backend.tf`, bỏ comment 3 dòng cuối:

```hcl
terraform {
  backend "azurerm" {}
}
```

Rồi:

```powershell
terraform init -backend-config=backend.hcl -migrate-state
```

Nếu hỏi `Do you want to copy existing state?` → `yes`.

---

## 3. Plan + guardrail

```powershell
terraform plan -input=false -out=tfplan

terraform show -json tfplan > plan.json
python ..\..\..\scripts\guardrails\check_plan.py plan.json
```

Phải thấy:

```
Plan: 39 to add, 0 to change, 0 to destroy.
GUARDRAIL OK — 39 resource change, không có resource bị cấm.
```

Nếu guardrail fail → **dừng**, không apply.

---

## 4. Apply

```powershell
terraform apply tfplan
```

⏱ 10–20 phút (PostgreSQL và Container Apps Environment lâu nhất).

### Nếu lỗi giữa chừng

Chạy lại `terraform apply tfplan` hoặc `terraform plan -out=tfplan` rồi apply lại — Terraform idempotent.

| Lỗi | Nguyên nhân | Xử lý |
|---|---|---|
| `LocationNotAvailableForResourceType` | `eastasia` thiếu Container Apps/SWA | đổi `location = "southeastasia"` (hoặc `westus2` cho SWA) |
| `InvalidResourceNamespace` / private DNS zone | tên zone PG khác loại kết nối | đọc thông báo lỗi, sửa `infra/modules/data/main.tf` |
| `OperationNotAllowed` khi tạo PostgreSQL | NSG chặn traffic nội bộ | comment `azurerm_subnet_network_security_group_association.pg`, apply, rồi thêm rule đúng |
| `The request is blocked by network rules` (storage) | IP bạn không khớp ACL | kiểm tra `terraform output operator_ip_used` |
| Subnet delegation lỗi | prefix chưa đúng | CAE cần ≥ /27 (đang dùng /23) |

---

## 5. Kiểm tra sau apply

```powershell
terraform output
```

Cần thấy: `postgres_fqdn`, `key_vault_uri`, `acr_login_server`, `storage_account_name`,
`static_web_app_host`, `container_app_default_domain`.

### Xác nhận PostgreSQL KHÔNG public

```powershell
Test-NetConnection -ComputerName (terraform output -raw postgres_fqdn) -Port 5432
```

Kết quả mong đợi: **`TcpTestSucceeded : False`** (không resolve/không kết nối được từ ngoài VNet).
Nếu `True` → PostgreSQL đang public, dừng lại và kiểm tra.

### Xác nhận Key Vault chặn Internet

```powershell
az keyvault secret list --vault-name (terraform output -raw key_vault_name) --query "length(@)"
```

Phải trả về số (3) — vì máy bạn nằm trong ACL.

---

## 6. Nạp dataset lên Azure Files

```powershell
$sa   = terraform output -raw storage_account_name
$key  = az storage account keys list -n $sa -g learn-guard-dev --query "[0].value" -o tsv
$ctx  = az storage account show-connection-string -n $sa -g learn-guard-dev --query connectionString -o tsv

# Tạo thư mục
az storage directory create --name oulad --share-name lgdata --connection-string $ctx
az storage directory create --name artifacts --share-name lgdata --connection-string $ctx

# Upload CSV đã giải nén (điều chỉnh đường dẫn nguồn)
az storage file upload-batch --destination lgdata/oulad --source "D:\Learn-guard\Data-ML-MLOPS\data\oulad" --connection-string $ctx
```

> Không dán `$key`/`$ctx` vào chat, log, hay commit.

---

## 7. Build image + bật ứng dụng (bước sau)

1. Build & push image vào ACR (xem `build/`)
2. Lấy digest:
   ```powershell
   az acr repository show-manifests --name (terraform output -raw acr_name) --repository learnguard-api --query "[0].digest" -o tsv
   ```
3. Sửa `terraform.tfvars`:
   ```hcl
   deploy_apps = true
   api_image   = "<acr_login_server>/learnguard-api@sha256:..."
   job_image   = "<acr_login_server>/learnguard-ml@sha256:..."
   ```
4. `terraform plan -out=tfplan` → guardrail → `terraform apply tfplan`

---

## 8. Teardown

```powershell
cd D:\Learn-guard\learnguard-platform\infra\env\dev
terraform destroy
```

> Xoá toàn bộ dữ liệu dev (database, secret, file share). Chỉ dùng cho dev.
> **Không** destroy thư mục `infra/bootstrap`.

---

## Phụ lục — lệnh hay dùng

```powershell
# Xem log API
az containerapp logs show -n (terraform output -raw ml_job_name) -g learn-guard-dev --follow

# Chạy ML job thủ công
az containerapp job start -n (terraform output -raw ml_job_name) -g learn-guard-dev

# Danh sách revision (rollback blue/green)
az containerapp revision list -n lg-dev-api -g learn-guard-dev -o table

# Xem chi phí
az consumption usage list --start-date (Get-Date).AddDays(-7).ToString("yyyy-MM-dd") --query "[].{name:instanceName, cost:pretaxCost}" -o table
```
