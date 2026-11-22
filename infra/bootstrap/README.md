# Bootstrap — Terraform state backend

Root Terraform **tách riêng**, chạy một lần cho mỗi subscription.

## Vì sao tách riêng

State của các môi trường (`env/dev`, `env/prod`) được lưu trong storage account.
Nếu storage account đó do chính môi trường tạo ra, ta có vòng lặp:

> muốn đọc state → cần storage account → muốn tạo storage account → cần đọc state

Nên bootstrap phải đứng trước và dùng **local state**. Đó là lý do duy nhất local state
được chấp nhận trong repo này.

## Chạy

```powershell
cd learnguard-platform\infra\bootstrap

terraform init
terraform plan -out=tfplan
terraform apply tfplan

terraform output backend_config
```

Copy giá trị `backend_config` vào `infra/env/dev/backend.hcl`, rồi:

```powershell
cd ..\env\dev
# bỏ comment block backend trong backend.tf
terraform init -backend-config=backend.hcl -migrate-state
```

## Lưu ý

| Điều | Ghi chú |
|---|---|
| `terraform.tfstate` của bootstrap | Nằm trong `.gitignore`. **Sao lưu thủ công** — mất file này thì vẫn dùng được storage account nhưng Terraform không quản lý nó nữa. |
| `terraform destroy` ở đây | ❌ **Không chạy.** Xoá storage account = mất state của mọi môi trường. |
| Soft delete + versioning | Đã bật cho blob (7 ngày) để cứu state bị ghi đè. |
| `shared_access_key_enabled` | Bật vì role hiện tại không có RBAC data-plane cho Storage. |
| `restrict_to_operator_ip` | Dev để `false` cho đơn giản; bật khi có IP cố định hoặc CI. |
