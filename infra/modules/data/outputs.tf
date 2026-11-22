output "server_id" {
  value = azurerm_postgresql_flexible_server.this.id
}

output "server_fqdn" {
  value = azurerm_postgresql_flexible_server.this.fqdn
}

output "database_name" {
  value = azurerm_postgresql_flexible_server_database.app.name
}

output "private_dns_zone_id" {
  value = azurerm_private_dns_zone.pg.id
}
