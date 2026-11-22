variable "key_vault_name" {
  description = "Tên Key Vault (<= 24 ký tự, chỉ alnum và dấu gạch ngang)."
  type        = string
}

variable "api_identity_name" {
  type = string
}

variable "job_identity_name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "tenant_id" {
  type = string
}

variable "deployer_object_id" {
  description = "Object ID của principal chạy Terraform (để seed secret qua access policy)."
  type        = string
}

variable "vnet_id" {
  type = string
}

variable "pe_subnet_id" {
  type = string
}

variable "allowed_ip_cidrs" {
  description = "Danh sách CIDR được phép truy cập data plane Key Vault."
  type        = list(string)
}

variable "tags" {
  type = map(string)
}
