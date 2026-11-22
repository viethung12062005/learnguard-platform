output "public_ip_address" {
  value = azurerm_public_ip.this.ip_address
}

output "admin_username" {
  value = var.admin_username
}

output "principal_id" {
  description = "System-assigned identity principal_id — dùng cấp quyền data-plane (KV access policy)."
  value       = azurerm_linux_virtual_machine.this.identity[0].principal_id
}
