variable "name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  description = "SWA chỉ hỗ trợ một số region (eastasia, westus2, centralus, eastus2, westeurope)."
  type        = string
}

variable "sku_tier" {
  description = "Free (dev) hoặc Standard (prod — có SLA, custom domain)."
  type        = string
  default     = "Free"
}

variable "tags" {
  type = map(string)
}
