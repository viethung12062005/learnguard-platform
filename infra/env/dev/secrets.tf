# ---------------------------------------------------------------------------
# Seed secret vào Key Vault.
#
# QUAN TRỌNG: file này KHÔNG chứa giá trị secret nào — mọi giá trị đều sinh ra
# lúc apply (random_password) hoặc đọc từ output của module. Không commit secret.
#
# GATE: azurerm_key_vault_secret ghi qua DATA-PLANE. Key Vault bị policy
# "disable public network access" ép tắt public → từ máy ngoài VNet không ghi
# được. Chỉ bật seed_kv_secrets=true khi chạy Terraform từ trong VNet
# (jump VM / self-hosted runner trong VNet), hoặc chuyển sang ARM control-plane.
# ---------------------------------------------------------------------------

resource "azurerm_key_vault_secret" "pg_admin_password" {
  count = var.seed_kv_secrets ? 1 : 0

  name         = "pg-admin-password"
  value        = random_password.pg_admin.result
  key_vault_id = module.security.key_vault_id
  tags         = var.tags

  depends_on = [module.security]
}

resource "azurerm_key_vault_secret" "pg_dsn" {
  count = var.seed_kv_secrets ? 1 : 0

  name = "pg-dsn"
  value = format(
    "postgresql://%s:%s@%s:5432/%s?sslmode=require",
    var.pg_admin_login,
    random_password.pg_admin.result,
    module.data.server_fqdn,
    var.pg_database_name,
  )
  key_vault_id = module.security.key_vault_id
  tags         = var.tags

  depends_on = [module.security]
}

resource "azurerm_key_vault_secret" "acr_admin_password" {
  count = var.seed_kv_secrets ? 1 : 0

  name         = "acr-admin-password"
  value        = module.registry.admin_password
  key_vault_id = module.security.key_vault_id
  tags         = var.tags

  depends_on = [module.security]
}
