output "container_app_environment_id" {
  value = azurerm_container_app_environment.this.id
}

output "container_app_environment_name" {
  value = azurerm_container_app_environment.this.name
}

output "default_domain" {
  value = azurerm_container_app_environment.this.default_domain
}

output "static_ip_address" {
  value = azurerm_container_app_environment.this.static_ip_address
}
