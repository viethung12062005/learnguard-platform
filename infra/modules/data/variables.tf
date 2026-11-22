variable "server_name" {
  type = string
}

variable "database_name" {
  type = string
}

variable "admin_login" {
  type = string
}

variable "admin_password" {
  type      = string
  sensitive = true
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "vnet_id" {
  type = string
}

variable "subnet_id" {
  description = "Subnet đã delegate cho Microsoft.DBforPostgreSQL/flexibleServers."
  type        = string
}

variable "tags" {
  type = map(string)
}
