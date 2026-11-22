variable "subscription_id" {
  description = "Subscription ID. Để null để dùng ARM_SUBSCRIPTION_ID / az login hiện tại."
  type        = string
  default     = null
}

variable "location" {
  description = "Region cho storage account chứa state."
  type        = string
  default     = "eastasia"
}

variable "resource_group_name" {
  description = "RG riêng cho state (không dùng chung với RG ứng dụng)."
  type        = string
  default     = "learn-guard-tfstate"
}

variable "container_name" {
  description = "Blob container chứa state."
  type        = string
  default     = "tfstate"
}

variable "restrict_to_operator_ip" {
  description = "Chặn truy cập state ngoài IP người vận hành. Prod/CI nên bật và quản lý IP tường minh."
  type        = bool
  default     = false
}

variable "allowed_ip_cidrs" {
  description = "CIDR được phép khi restrict_to_operator_ip = true."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tag chung. Gồm tag bắt buộc bởi Azure Policy tag_governance (FSO)."
  type        = map(string)
  default = {
    project    = "learnguard"
    purpose    = "terraform-state"
    managed_by = "terraform"

    # Azure Policy tag_governance (FSO-SZ) — bắt buộc, không xoá.
    Environment  = "DEV"
    Region       = "East Asia"
    ServiceOwner = "HungTV88@fpt.com"
    Description  = "LearnGuard Terraform state"
    CreatedBy    = "terraform"
  }
}
