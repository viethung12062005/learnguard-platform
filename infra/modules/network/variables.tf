variable "vnet_name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "address_space" {
  type = string
}

variable "cae_subnet_prefix" {
  type = string
}

variable "pg_subnet_prefix" {
  type = string
}

variable "pe_subnet_prefix" {
  type = string
}

variable "jump_subnet_prefix" {
  type    = string
  default = "10.20.4.0/24"
}

# IP (CIDR) được phép SSH vào jump VM. Chỉ mở 22 từ IP người vận hành.
variable "jump_ssh_source_prefix" {
  type = string
}

variable "tags" {
  type = map(string)
}
