variable "name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "log_analytics_workspace_id" {
  type = string
}

variable "infrastructure_subnet_id" {
  description = "Subnet đã delegate cho Microsoft.App/environments."
  type        = string
}

variable "tags" {
  type = map(string)
}
