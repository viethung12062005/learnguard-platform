output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "location" {
  value = azurerm_resource_group.this.location
}

output "vnet_id" {
  value = module.network.vnet_id
}

output "cae_subnet_id" {
  value = module.network.cae_subnet_id
}

output "pg_subnet_id" {
  value = module.network.pg_subnet_id
}

output "postgres_fqdn" {
  description = "FQDN private của PostgreSQL (chỉ resolve trong VNet)."
  value       = module.data.server_fqdn
}

output "postgres_database" {
  value = module.data.database_name
}

output "key_vault_uri" {
  value = module.security.key_vault_uri
}

output "key_vault_name" {
  value = module.security.key_vault_name
}

output "container_app_environment_id" {
  value = module.compute.container_app_environment_id
}

output "container_app_default_domain" {
  value = module.compute.default_domain
}

output "acr_login_server" {
  value = module.registry.login_server
}

output "acr_name" {
  value = local.acr_name
}

output "storage_account_name" {
  value = module.storage.name
}

output "storage_share_name" {
  value = module.storage.share_name
}

output "static_web_app_host" {
  value = "https://${module.frontend.default_host_name}"
}

output "log_analytics_workspace_id" {
  value = module.observability.log_analytics_workspace_id
}

output "api_fqdn" {
  description = "URL công khai ỔN ĐỊNH của API (rỗng nếu deploy_apps = false). Không dùng latest_revision_fqdn vì URL đó gắn chết vào một revision."
  value       = var.deploy_apps ? "${local.api_app_name}.${module.compute.default_domain}" : ""
}

output "ml_job_name" {
  description = "Tên Container App Job (rỗng nếu deploy_apps = false)."
  value       = var.deploy_apps ? azurerm_container_app_job.ml_batch[0].name : ""
}

output "operator_ip_used" {
  description = "IP được thêm vào ACL Key Vault."
  value       = local.operator_ip
}

# ---------------------------------------------------------------------------
# Jump VM + giá trị seed (sensitive — chỉ đọc bằng terraform output -raw,
# KHÔNG commit, KHÔNG in ra chat/log).
# ---------------------------------------------------------------------------
output "jump_public_ip" {
  description = "Public IP của jump VM (SSH vào đây)."
  value       = module.jump.public_ip_address
}

output "jump_admin_username" {
  value = module.jump.admin_username
}

output "jump_ssh_private_key" {
  description = "Private key SSH cho jump VM (ED25519). Lưu local, chmod 600."
  value       = tls_private_key.jump.private_key_openssh
  sensitive   = true
}

output "pg_admin_password" {
  description = "Mật khẩu admin PostgreSQL (để seed KV)."
  value       = random_password.pg_admin.result
  sensitive   = true
}

output "acr_admin_password" {
  description = "Mật khẩu admin ACR (để seed KV)."
  value       = module.registry.admin_password
  sensitive   = true
}
