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
# Storage account cho dữ liệu ML (data/oulad + artifacts).
#
# Bảo vệ: ACL mặc định Deny
#   - Private endpoint (snet-pe) cho Container Apps Job mount qua SMB
#   - ip_rules cho máy người vận hành upload dataset ban đầu
# ---------------------------------------------------------------------------
resource "azurerm_storage_account" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location

  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false

  # Container Apps mount Azure Files bằng account key → phải bật.
  # (Role hiện tại không có Storage Blob Data Contributor để dùng Entra auth.)
  shared_access_key_enabled = true

  # Policy "Storage accounts should disable public network access" (Deny) bắt public=Disabled.
  # ML job truy cập qua private endpoint (CAE nằm trong VNet). Việc upload dataset ban đầu
  # từ máy ngoài VNet sẽ xử lý riêng (xem runbooks — gap dữ liệu).
  public_network_access_enabled = false

  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices"]
    ip_rules       = var.allowed_ip_cidrs
  }

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = 7
    }
  }

  tags = var.tags

  lifecycle {
    # tags: policy modify của tenant tự gắn tag.
    # network_rules: public_network_access_enabled = false nên ip_rules không còn tác dụng;
    # IP người vận hành đổi liên tục (CGNAT) → bỏ qua để tránh drift mỗi lần apply.
    ignore_changes = [tags, network_rules]
  }
}

resource "azurerm_storage_share" "data" {
  name               = var.share_name
  storage_account_id = azurerm_storage_account.this.id
  quota              = var.share_quota_gb
}

# ---------------------------------------------------------------------------
# Private endpoint cho Azure Files (SMB)
# ---------------------------------------------------------------------------
resource "azurerm_private_dns_zone" "file" {
  name                = "privatelink.file.core.windows.net"
  resource_group_name = var.resource_group_name
  tags                = local.dns_tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "file" {
  name                  = "link-files"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.file.name
  virtual_network_id    = var.vnet_id
  registration_enabled  = false
  tags                  = local.dns_tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_private_endpoint" "file" {
  name                = "pe-${var.name}-file"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.pe_subnet_id
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }

  private_service_connection {
    name                           = "psc-files"
    private_connection_resource_id = azurerm_storage_account.this.id
    subresource_names              = ["file"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.file.id]
  }
}
