# ---------------------------------------------------------------------------
# BOOTSTRAP — chạy MỘT LẦN cho mỗi subscription.
#
# Tạo nơi lưu Terraform state cho các môi trường (dev, prod...).
# Root này CỐ TÌNH dùng local state: nó không thể lưu state của chính nó
# vào storage account mà nó đang tạo.
#
# Chạy lại root này là an toàn (idempotent). Destroy root này = xoá toàn bộ
# state của mọi môi trường → mất khả năng quản lý bằng Terraform.
# ---------------------------------------------------------------------------

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
  numeric = true
}

resource "azurerm_resource_group" "tfstate" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags

  # Azure Policy inherit_tags_to_resource_groups (modify) tự thêm tag → ignore để khỏi drift.
  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_storage_account" "tfstate" {
  name                = "lgstate${random_string.suffix.result}" # <= 24 ký tự, chỉ chữ thường + số
  resource_group_name = azurerm_resource_group.tfstate.name
  location            = azurerm_resource_group.tfstate.location

  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false

  # Bắt buộc bật: Terraform provider dùng account key để tạo container,
  # vì role hiện tại không có Storage Blob Data Contributor (RBAC data plane).
  shared_access_key_enabled = true

  # Azure Policy (FSO-SZ) "Storage accounts should disable public network access" = Deny
  # => mọi storage account PHẢI tắt public access. Do đó remote backend không dùng được
  #    từ máy ngoài VNet (dev); env/dev dùng local state. Storage này giữ lại cho trường
  #    hợp sau này chạy Terraform bên trong VNet (jump VM / runner trong VNet).
  public_network_access_enabled = false
  network_rules {
    default_action = var.restrict_to_operator_ip ? "Deny" : "Allow"
    bypass         = ["AzureServices"]
    ip_rules       = var.restrict_to_operator_ip ? var.allowed_ip_cidrs : []
  }

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = 7
    }

    container_delete_retention_policy {
      days = 7
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_storage_container" "tfstate" {
  name                  = var.container_name
  storage_account_id    = azurerm_storage_account.tfstate.id
  container_access_type = "private"
}
