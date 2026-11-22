provider "azurerm" {
  subscription_id = var.subscription_id

  # Bỏ qua bước "populating Resource Provider cache" (liệt kê provider qua
  # management plane) — chậm + dễ lỗi network với token FPT ngắn hạn. Ta không
  # cần đăng ký provider ở đây (subscription đã có sẵn các RP).
  # azurerm 4.x: skip_provider_registration đã deprecated → dùng property mới.
  resource_provider_registrations = "none"

  features {
    key_vault {
      # Dev: cho phép xoá sạch khi teardown (tiết kiệm thời gian, tránh soft-delete rác).
      # PROD PHẢI đổi thành false và bật purge_protection.
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      # Dev: cho phép xoá RG kể cả khi còn resource bên trong.
      prevent_deletion_if_contains_resources = false
    }
  }
}

# Dùng để tự phát hiện IP người vận hành (chỉ dùng khi var.operator_ip_cidr để trống).
data "http" "my_ip" {
  url = "https://api.ipify.org"
}
