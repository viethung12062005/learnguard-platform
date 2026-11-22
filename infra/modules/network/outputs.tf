output "vnet_id" {
  value = azurerm_virtual_network.this.id
}

output "vnet_name" {
  value = azurerm_virtual_network.this.name
}

# Subnets được tạo qua ARM template (xem main.tf) nên không có azurerm_subnet
# resource để đọc .id. ID subnet có dạng cố định: <vnet_id>/subnets/<name>.
#
# QUAN TRỌNG: depends_on bên dưới bắt buộc consumer (CAE/PG/private endpoint)
# CHỜ ARM template deployment tạo xong subnet. Không có nó, Terraform chỉ thấy
# subnet id là string → consumer chạy song song với deployment → lỗi
# "subnet not found" + "AnotherOperationInProgress" trên VNet.
output "cae_subnet_id" {
  value      = "${azurerm_virtual_network.this.id}/subnets/snet-cae"
  depends_on = [azurerm_resource_group_template_deployment.subnets]
}

output "cae_subnet_prefix" {
  value = var.cae_subnet_prefix
}

output "pg_subnet_id" {
  value      = "${azurerm_virtual_network.this.id}/subnets/snet-pg"
  depends_on = [azurerm_resource_group_template_deployment.subnets]
}

output "pe_subnet_id" {
  value      = "${azurerm_virtual_network.this.id}/subnets/snet-pe"
  depends_on = [azurerm_resource_group_template_deployment.subnets]
}

output "jump_subnet_id" {
  value      = "${azurerm_virtual_network.this.id}/subnets/snet-jump"
  depends_on = [azurerm_resource_group_template_deployment.subnets]
}
