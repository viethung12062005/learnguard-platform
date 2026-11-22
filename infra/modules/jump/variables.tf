variable "name" {
  type = string
}

# Tên VM phải tuân thủ Azure Policy của tenant: bắt đầu "vm-az-" và <= 15 ký tự.
# Tách riêng khỏi `name` (dùng cho NIC/PIP) để không phải recreate NIC/PIP.
variable "vm_name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "ssh_public_key" {
  type = string
}

variable "admin_username" {
  type    = string
  default = "lgops"
}

variable "tags" {
  type = map(string)
}
