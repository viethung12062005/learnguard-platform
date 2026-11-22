variable "name" {
  description = "Tên ACR (chỉ chữ và số, 5-50 ký tự, toàn cầu duy nhất)."
  type        = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "tags" {
  type = map(string)
}
