# ---------------------------------------------------------------------------
# Static Web App — frontend SPA (React/Vite).
# Free tier cho dev (không có SLA — prod dùng Standard).
# SWA chỉ có ở một số region; eastasia được hỗ trợ.
# ---------------------------------------------------------------------------
resource "azurerm_static_web_app" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_tier            = var.sku_tier
  sku_size            = var.sku_tier

  tags = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}
