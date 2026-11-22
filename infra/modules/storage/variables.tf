variable "name" {
  description = "Tên storage account (3-24 ký tự, chỉ chữ thường + số)."
  type        = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "share_name" {
  description = "Tên file share chứa data + artifacts."
  type        = string
  default     = "lgdata"
}

variable "share_quota_gb" {
  description = "Dung lượng share (GB). Dataset ~0.5GB + artifacts."
  type        = number
  default     = 16
}

variable "vnet_id" {
  type = string
}

variable "pe_subnet_id" {
  type = string
}

variable "allowed_ip_cidrs" {
  description = "CIDR được phép upload/đọc trực tiếp (máy người vận hành)."
  type        = list(string)
}

variable "tags" {
  type = map(string)
}
