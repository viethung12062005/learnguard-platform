variable "law_name" {
  type = string
}

variable "appi_name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "retention_in_days" {
  description = "Số ngày lưu log. Dev dùng 30 để tiết kiệm."
  type        = number
  default     = 30
}

variable "daily_quota_gb" {
  description = "Hạn mức log/ngày (GB). 0 = không giới hạn."
  type        = number
  default     = 0.5
}

variable "tags" {
  type = map(string)
}
