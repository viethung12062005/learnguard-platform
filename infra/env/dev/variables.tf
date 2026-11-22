variable "subscription_id" {
  description = "Subscription ID. Để null để dùng ARM_SUBSCRIPTION_ID / az login hiện tại."
  type        = string
  default     = null
}

variable "project" {
  description = "Tên dự án dùng cho tiền tố resource."
  type        = string
  default     = "learnguard"
}

variable "environment" {
  description = "Tên môi trường (dev)."
  type        = string
  default     = "dev"
}

variable "location" {
  description = "Region Azure. East Asia rẻ nhất cho dev; nếu Container Apps không khả dụng ở đây thì đổi sang southeastasia."
  type        = string
  default     = "eastasia"
}

variable "tags" {
  description = "Tag chung cho mọi resource. Gồm tag bắt buộc bởi Azure Policy tag_governance (FSO)."
  type        = map(string)
  default = {
    project     = "learnguard"
    managed_by  = "terraform"
    cost_center = "ojt"

    # Azure Policy tag_governance (FSO-SZ) — bắt buộc, không xoá.
    # LƯU Ý: policy đánh giá tag KHÔNG phân biệt hoa/thường → không được để cả
    # `environment` (thường) lẫn `Environment` (hoa), sẽ lỗi AmbiguousPolicyEvaluationPaths.
    Environment  = "DEV"
    Region       = "East Asia"
    ServiceOwner = "HungTV88@fpt.com"
    Description  = "LearnGuard Student Success Early-Warning Assistant"
    CreatedBy    = "terraform"
  }
}

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
variable "vnet_address_space" {
  description = "CIDR của VNet."
  type        = string
  default     = "10.20.0.0/16"
}

variable "cae_subnet_prefix" {
  description = "Subnet cho Container Apps Environment (delegated). Khuyến nghị /23."
  type        = string
  default     = "10.20.0.0/23"
}

variable "pg_subnet_prefix" {
  description = "Subnet cho PostgreSQL Flexible (delegated, không dùng chung)."
  type        = string
  default     = "10.20.2.0/24"
}

variable "pe_subnet_prefix" {
  description = "Subnet cho private endpoints."
  type        = string
  default     = "10.20.3.0/24"
}

variable "jump_subnet_prefix" {
  description = "Subnet cho jump VM (seed KV/PG/storage từ trong VNet)."
  type        = string
  default     = "10.20.4.0/24"
}

# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------
variable "operator_ip_cidr" {
  description = "IP người vận hành (dạng x.x.x.x/32) được phép vào Key Vault. Để trống = tự phát hiện."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
variable "pg_admin_login" {
  description = "Admin login của PostgreSQL."
  type        = string
  default     = "lgadmin"
}

variable "pg_database_name" {
  description = "Tên database ứng dụng."
  type        = string
  default     = "learnguard"
}

# ---------------------------------------------------------------------------
# Apps (bật khi đã có image trong ACR)
# ---------------------------------------------------------------------------
variable "deploy_apps" {
  description = "Bật để tạo Container App API + Job. Để false khi chưa build image."
  type        = bool
  default     = false
}

variable "seed_kv_secrets" {
  description = "Ghi secret vào Key Vault bằng data-plane. Cần reach được KV (public access đã bị policy tắt → phải chạy từ trong VNet). Để false khi apply từ máy ngoài VNet."
  type        = bool
  default     = false
}

variable "api_image" {
  description = "Image API đã push, theo digest (khuyến nghị) hoặc tag. VD: <acr>.azurecr.io/api@sha256:..."
  type        = string
  default     = ""
}

variable "job_image" {
  description = "Image ML job đã push. VD: <acr>.azurecr.io/ml-batch@sha256:..."
  type        = string
  default     = ""
}
