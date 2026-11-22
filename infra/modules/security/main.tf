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
# Managed identities
# Ta TỰ TẠO UAMI được (Microsoft.ManagedIdentity/* nằm trong actions:*).
# Ta KHÔNG gán RBAC role được → quyền data-plane đi qua Key Vault access policy.
# ---------------------------------------------------------------------------
resource "azurerm_user_assigned_identity" "api" {
  name                = var.api_identity_name
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_user_assigned_identity" "job" {
  name                = var.job_identity_name
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

# ---------------------------------------------------------------------------
# Key Vault
# Model uỷ quyền: ACCESS POLICY (không phải RBAC) — vì ta không gán được role.
# ---------------------------------------------------------------------------
resource "azurerm_key_vault" "this" {
  name                = var.key_vault_name
  location            = var.location
  resource_group_name = var.resource_group_name
  tenant_id           = var.tenant_id
  sku_name            = "standard"

  # Dev: tắt purge protection để teardown nhanh. PROD: bật true.
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  # Policy "Azure Key Vault should disable public network access" (Deny) bắt public=Disabled.
  # => chỉ vào được qua private endpoint (VNet). Việc seed secret từ máy ngoài VNet
  #    phải đi qua cơ chế khác (jump VM / runner trong VNet / ARM control-plane).
  public_network_access_enabled = false
  rbac_authorization_enabled    = false

  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_key_vault_access_policy" "api" {
  key_vault_id = azurerm_key_vault.this.id
  tenant_id    = var.tenant_id
  object_id    = azurerm_user_assigned_identity.api.principal_id

  secret_permissions = ["Get", "List"]
}

# Người vận hành (chính bạn) cần quyền data-plane để Terraform/CLI seed secret.
# Trong mô hình access policy, quyền management-plane KHÔNG tự đủ cho data-plane.
resource "azurerm_key_vault_access_policy" "deployer" {
  key_vault_id = azurerm_key_vault.this.id
  tenant_id    = var.tenant_id
  object_id    = var.deployer_object_id

  secret_permissions = ["Get", "List", "Set", "Delete", "Purge", "Recover"]
}

resource "azurerm_key_vault_access_policy" "job" {
  key_vault_id = azurerm_key_vault.this.id
  tenant_id    = var.tenant_id
  object_id    = azurerm_user_assigned_identity.job.principal_id

  secret_permissions = ["Get", "List"]
}

# ---------------------------------------------------------------------------
# Private endpoint cho Key Vault
# ---------------------------------------------------------------------------
resource "azurerm_private_dns_zone" "keyvault" {
  name                = "privatelink.vaultcore.azure.net"
  resource_group_name = var.resource_group_name
  tags                = local.dns_tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "keyvault" {
  name                  = "link-keyvault"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.keyvault.name
  virtual_network_id    = var.vnet_id
  registration_enabled  = false
  tags                  = local.dns_tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_private_endpoint" "keyvault" {
  name                = "pe-${var.key_vault_name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.pe_subnet_id
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }

  private_service_connection {
    name                           = "psc-keyvault"
    private_connection_resource_id = azurerm_key_vault.this.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.keyvault.id]
  }
}
