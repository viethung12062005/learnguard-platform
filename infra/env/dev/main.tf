data "azurerm_client_config" "current" {}

# Hậu tố ngẫu nhiên cho resource cần tên toàn cầu duy nhất.
resource "random_string" "suffix" {
  length  = 5
  special = false
  upper   = false
}

# Mật khẩu admin PostgreSQL. Không dùng ký tự đặc biệt để DSN không phải URL-encode.
resource "random_password" "pg_admin" {
  length  = 32
  special = false
}

resource "azurerm_resource_group" "this" {
  name     = local.resource_group_name
  location = var.location
  tags     = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

module "network" {
  source = "../../modules/network"

  vnet_name              = local.vnet_name
  resource_group_name    = azurerm_resource_group.this.name
  location               = azurerm_resource_group.this.location
  address_space          = var.vnet_address_space
  cae_subnet_prefix      = var.cae_subnet_prefix
  pg_subnet_prefix       = var.pg_subnet_prefix
  pe_subnet_prefix       = var.pe_subnet_prefix
  jump_subnet_prefix     = var.jump_subnet_prefix
  jump_ssh_source_prefix = local.operator_ip
  tags                   = var.tags
}

# SSH key cho jump VM. Private key nằm trong state (sensitive) — đừng commit.
resource "tls_private_key" "jump" {
  algorithm = "ED25519"
}

module "jump" {
  source = "../../modules/jump"

  name                = "vm-${local.name_prefix}-jump"
  vm_name             = "vm-az-lg-jump"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  subnet_id           = module.network.jump_subnet_id
  ssh_public_key      = tls_private_key.jump.public_key_openssh
  tags                = var.tags
}

# Cấp quyền data-plane Key Vault cho jump VM identity (seed secret không cần MFA).
resource "azurerm_key_vault_access_policy" "jump" {
  key_vault_id = module.security.key_vault_id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = module.jump.principal_id

  secret_permissions = ["Get", "List", "Set"]
}

module "observability" {
  source = "../../modules/observability"

  law_name            = local.law_name
  appi_name           = local.appi_name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  retention_in_days   = 30
  daily_quota_gb      = 0.5
  tags                = var.tags
}

module "security" {
  source = "../../modules/security"

  key_vault_name      = local.key_vault_name
  api_identity_name   = local.api_identity
  job_identity_name   = local.job_identity
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  deployer_object_id  = data.azurerm_client_config.current.object_id
  vnet_id             = module.network.vnet_id
  pe_subnet_id        = module.network.pe_subnet_id
  allowed_ip_cidrs    = [local.operator_ip]
  tags                = var.tags
}

module "data" {
  source = "../../modules/data"

  server_name         = local.pg_server_name
  database_name       = var.pg_database_name
  admin_login         = var.pg_admin_login
  admin_password      = random_password.pg_admin.result
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  vnet_id             = module.network.vnet_id
  subnet_id           = module.network.pg_subnet_id
  tags                = var.tags
}

module "registry" {
  source = "../../modules/registry"

  name                = local.acr_name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = var.tags
}

module "storage" {
  source = "../../modules/storage"

  name                = local.storage_name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  share_name          = "lgdata"
  share_quota_gb      = 16
  vnet_id             = module.network.vnet_id
  pe_subnet_id        = module.network.pe_subnet_id
  allowed_ip_cidrs    = [local.operator_ip_bare]
  tags                = var.tags
}

module "frontend" {
  source = "../../modules/frontend"

  name                = local.swa_name
  resource_group_name = azurerm_resource_group.this.name
  # SWA chỉ có ở một số region. eastasia được hỗ trợ; nếu không, dùng westus2.
  location = var.location
  sku_tier = "Free"
  tags     = var.tags
}

module "compute" {
  source = "../../modules/compute"

  name                       = local.cae_name
  resource_group_name        = azurerm_resource_group.this.name
  location                   = azurerm_resource_group.this.location
  log_analytics_workspace_id = module.observability.log_analytics_workspace_id
  infrastructure_subnet_id   = module.network.cae_subnet_id
  tags                       = var.tags
}
