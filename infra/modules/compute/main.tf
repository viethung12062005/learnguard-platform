resource "azurerm_container_app_environment" "this" {
  name                       = var.name
  location                   = var.location
  resource_group_name        = var.resource_group_name
  log_analytics_workspace_id = var.log_analytics_workspace_id
  infrastructure_subnet_id   = var.infrastructure_subnet_id
  tags                       = var.tags

  # Khai báo tường minh profile Consumption (Azure luôn tự tạo). Nếu không,
  # mỗi lần plan azurerm lại muốn XOÁ profile này → drift vô hạn.
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
    minimum_count         = 0
    maximum_count         = 0
  }

  lifecycle {
    ignore_changes = [tags]
  }
}
