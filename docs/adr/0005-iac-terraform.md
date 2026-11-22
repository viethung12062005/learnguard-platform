# ADR-0005 — IaC: Terraform (hashicorp/azurerm), thay Bicep

- **Trạng thái:** Accepted
- **Ngày:** 2026-11-04 (duyệt 2026-11-04)

## Bối cảnh
Đề xuất ban đầu dùng Bicep. Người dùng yêu cầu chuyển sang **Terraform**.

## Quyết định
- IaC = **Terraform** (`hashicorp/azurerm ~> 4.0`), khai báo toàn bộ hạ tầng trong `infra/`.
- Cấu trúc: `env/{dev,prod}/` + `modules/{network,observability,security,data,registry,compute}`.
- State backend: **remote (Azure Storage)** với lease lock — `scripts/bootstrap/state-backend.sh`. Mặc định tắt để init chạy được ngay; bật theo runbook.
- Guardrail: `scripts/guardrails/check_plan.py` chặn `azurerm_role_*`, `azurerm_policy_*`, `azurerm_management_lock` trong plan.

## Hệ quả
- Một nguồn sự thật IaC; `terraform plan` + guardrail là bước duyệt trước apply.
- State chứa secret (mật khẩu PG) → bắt buộc chuyển remote trước khi có người thứ hai.

## Cần xác minh
- azurerm 4.x có thay đổi schema nào ảnh hưởng resource đã viết (chạy `terraform validate` khi cài xong Terraform).
