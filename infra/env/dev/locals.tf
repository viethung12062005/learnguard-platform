locals {
  # Tên resource group theo quy ước đã ghi trong tài liệu kiến trúc.
  # Region: eastasia (rẻ nhất cho dev) — var.location.
  resource_group_name = "learn-guard-${var.environment}"

  # Tiền tố ngắn, an toàn cho hầu hết loại resource.
  name_prefix = "lg-${var.environment}"

  # Hậu tố ngẫu nhiên cho resource yêu cầu tên toàn cầu duy nhất (Key Vault, ACR, PG).
  suffix = random_string.suffix.result

  # IP người vận hành: ưu tiên biến, nếu trống thì tự phát hiện.
  operator_ip = (
    var.operator_ip_cidr != "" ? var.operator_ip_cidr : "${chomp(data.http.my_ip.response_body)}/32"
  )

  # Azure Storage firewall KHÔNG chấp nhận prefix /32 (chỉ 0-30); Key Vault thì có.
  # Với storage, dùng IP trần (không mask).
  operator_ip_bare = replace(local.operator_ip, "/32", "")

  # Tên resource có ràng buộc ký tự riêng của Azure.
  key_vault_name = "kv-${local.name_prefix}-${local.suffix}"   # <= 24 ký tự, chỉ alnum + '-'
  acr_name       = "acr${var.environment}${local.suffix}"      # chỉ alnum
  pg_server_name = "psql-${local.name_prefix}-${local.suffix}" # lowercase alnum + '-'
  cae_name       = "cae-${local.name_prefix}"
  law_name       = "log-${local.name_prefix}"
  appi_name      = "appi-${local.name_prefix}"
  vnet_name      = "vnet-${local.name_prefix}"
  api_app_name   = "ca-${local.name_prefix}-api"
  ml_job_name    = "caj-${local.name_prefix}-ml"
  api_identity   = "id-${local.name_prefix}-api"
  job_identity   = "id-${local.name_prefix}-job"

  # Storage account: chỉ chữ thường + số, <= 24 ký tự.
  storage_name     = "stlg${var.environment}${local.suffix}"
  cae_storage_name = "lgfiles" # tên volume trong Container Apps Environment
  swa_name         = "swa-${local.name_prefix}"
}
