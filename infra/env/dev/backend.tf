# ---------------------------------------------------------------------------
# Remote state (khuyến nghị). Mặc định ĐỂ TẮT để `terraform init` chạy được ngay.
#
# Bật remote state (bootstrap là ROOT RIÊNG, xem ../../bootstrap/README.md):
#   1) cd ../../bootstrap && terraform init && terraform apply
#   2) terraform output backend_config  -> tạo backend.hcl ở đây
#   3) bỏ comment block dưới đây, rồi: terraform init -backend-config=backend.hcl -migrate-state
#
# Lý do: state chứa secret (mật khẩu PG, connection string) → không được nằm trên máy
#        và không được commit. Storage backend có encryption-at-rest + lease lock.
# ---------------------------------------------------------------------------
#
# terraform {
#   backend "azurerm" {}
# }
