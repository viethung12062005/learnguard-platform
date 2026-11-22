# ---------------------------------------------------------------------------
# Azure Container Registry — Basic là SKU rẻ nhất.
#
# DEV dùng admin user (bật/tắt được, mật khẩu lưu Key Vault) để giảm số thành phần.
# PROD nên chuyển sang managed identity + role AcrPull (cần Admin gán role),
# hoặc repo-scoped token — xem ADR-0004.
# ---------------------------------------------------------------------------
resource "azurerm_container_registry" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "Basic"
  admin_enabled       = true

  # Public vì private endpoint của ACR cần SKU Premium.
  public_network_access_enabled = true

  tags = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}
