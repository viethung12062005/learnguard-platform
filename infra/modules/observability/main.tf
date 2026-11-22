resource "azurerm_log_analytics_workspace" "this" {
  name                = var.law_name
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = var.retention_in_days

  # Giới hạn chi phí cho dev. Vượt hạn mức thì log bị drop trong ngày (chấp nhận ở dev).
  # PROD: đặt 0 (không giới hạn) và dùng alert thay vì cắt log.
  daily_quota_gb = var.daily_quota_gb

  tags = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_application_insights" "this" {
  name                = var.appi_name
  location            = var.location
  resource_group_name = var.resource_group_name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.this.id
  retention_in_days   = var.retention_in_days

  tags = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}
