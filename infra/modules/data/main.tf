# Private DNS zone + vnet link chỉ chịu tối đa 15 tag. Policy "inherit_tags_to_*"
# (modify) tự thêm ~9 tag từ subscription → chỉ gửi 3 tag bắt buộc để không vượt 15.
locals {
  dns_tags = {
    ServiceOwner = var.tags["ServiceOwner"]
    Description  = var.tags["Description"]
    CreatedBy    = var.tags["CreatedBy"]
  }
}

# ---------------------------------------------------------------------------
# Private DNS cho PostgreSQL Flexible Server (VNet injection).
# Tên zone: private.postgres.database.azure.com
# Bản ghi: <server>.private.postgres.database.azure.com
# (Nếu Azure báo sai tên zone, xem ghi chú "cần xác minh" trong ADR-0003.)
# ---------------------------------------------------------------------------
resource "azurerm_private_dns_zone" "pg" {
  name                = "private.postgres.database.azure.com"
  resource_group_name = var.resource_group_name
  tags                = local.dns_tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "pg" {
  name                  = "link-postgres"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pg.name
  virtual_network_id    = var.vnet_id
  registration_enabled  = false
  tags                  = local.dns_tags

  lifecycle {
    ignore_changes = [tags]
  }
}

# ---------------------------------------------------------------------------
# PostgreSQL Flexible Server — SKU rẻ nhất phù hợp dev.
# B1ms: 1 vCPU / 2 GiB — KHÔNG hỗ trợ zone-redundant HA (chấp nhận ở dev).
# ---------------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server" "this" {
  name                = var.server_name
  resource_group_name = var.resource_group_name
  location            = var.location

  version    = "16"
  sku_name   = "B_Standard_B1ms"
  storage_mb = 32768

  administrator_login    = var.admin_login
  administrator_password = var.admin_password

  backup_retention_days        = 7
  geo_redundant_backup_enabled = false

  public_network_access_enabled = false
  delegated_subnet_id           = var.subnet_id
  private_dns_zone_id           = azurerm_private_dns_zone.pg.id

  tags = var.tags

  # Azure tự chọn AZ theo region; không ghim để tránh lỗi ở vùng không hỗ trợ.
  lifecycle {
    ignore_changes = [zone, tags]
  }
}

resource "azurerm_postgresql_flexible_server_database" "app" {
  name      = var.database_name
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}
