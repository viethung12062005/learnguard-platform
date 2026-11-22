# ---------------------------------------------------------------------------
# Container App (API) + Container App Job (ML batch).
#
# Chỉ tạo khi var.deploy_apps = true (tức là đã có image trong ACR).
# Lần apply đầu tiên: để false → dựng xong hạ tầng, xem output để biết login server,
# rồi build/push image và bật true với image theo digest.
# ---------------------------------------------------------------------------

# Gắn Azure Files vào Container Apps Environment để job ML mount được.
# Tên volume này được tham chiếu trong template.volume của job bên dưới.
resource "azurerm_container_app_environment_storage" "data" {
  count = var.deploy_apps ? 1 : 0

  name                         = local.cae_storage_name
  container_app_environment_id = module.compute.container_app_environment_id
  account_name                 = module.storage.name
  share_name                   = module.storage.share_name
  access_key                   = module.storage.primary_access_key
  access_mode                  = "ReadWrite"
}

resource "azurerm_container_app" "api" {
  count = var.deploy_apps ? 1 : 0

  name                         = local.api_app_name
  container_app_environment_id = module.compute.container_app_environment_id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Multiple" # cần cho blue/green
  tags                         = var.tags

  lifecycle {
    ignore_changes = [tags]
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [module.security.api_identity_id]
  }

  # Secret lấy từ Key Vault bằng managed identity (không hardcode, không qua biến).
  # Chú ý: secret được seed thủ công từ trong VNet (xem runbooks/seed) nên KHÔNG
  # còn resource azurerm_key_vault_secret trong Terraform; tham chiếu bằng ID dựng sẵn.
  secret {
    name                = "pg-dsn"
    key_vault_secret_id = "${module.security.key_vault_uri}secrets/pg-dsn"
    identity            = module.security.api_identity_id
  }

  secret {
    name                = "acr-admin-password"
    key_vault_secret_id = "${module.security.key_vault_uri}secrets/acr-admin-password"
    identity            = module.security.api_identity_id
  }

  registry {
    server               = module.registry.login_server
    username             = module.registry.admin_username
    password_secret_name = "acr-admin-password"
  }

  template {
    # Dev rẻ nhất: scale về 0 khi không có request.
    min_replicas = 0
    max_replicas = 2

    container {
      name   = "api"
      image  = var.api_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "APP_ENV"
        value = var.environment
      }

      env {
        name        = "DATABASE_URL"
        secret_name = "pg-dsn"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = module.observability.application_insights_connection_string
      }

      # Chỉ cho phép origin của Static Web App gọi API.
      env {
        name  = "CORS_ORIGINS"
        value = "https://${module.frontend.default_host_name}"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}

resource "azurerm_container_app_job" "ml_batch" {
  count = var.deploy_apps ? 1 : 0

  name                         = local.ml_job_name
  container_app_environment_id = module.compute.container_app_environment_id
  resource_group_name          = azurerm_resource_group.this.name
  location                     = azurerm_resource_group.this.location
  tags                         = var.tags

  lifecycle {
    ignore_changes = [tags]
  }

  # Job ML có thể chạy lâu (M2/M3/M4). 1 giờ cho dev; tăng nếu cần.
  replica_timeout_in_seconds = 3600
  replica_retry_limit        = 0

  # Dev: kích hoạt thủ công. Khi ổn định, đổi sang schedule_trigger_config
  # với cron cho bước scoring.
  manual_trigger_config {}

  identity {
    type         = "UserAssigned"
    identity_ids = [module.security.job_identity_id]
  }

  # Least privilege: job ML dùng role lg_ml_writer (chỉ ghi ml_predictions),
  # tách khỏi DSN của API (lg_api).
  secret {
    name                = "pg-dsn-ml"
    key_vault_secret_id = "${module.security.key_vault_uri}secrets/pg-dsn-ml"
    identity            = module.security.job_identity_id
  }

  secret {
    name                = "acr-admin-password"
    key_vault_secret_id = "${module.security.key_vault_uri}secrets/acr-admin-password"
    identity            = module.security.job_identity_id
  }

  registry {
    server               = module.registry.login_server
    username             = module.registry.admin_username
    password_secret_name = "acr-admin-password"
  }

  template {
    # Mount share lgdata vào /mnt/data cho data + artifacts.
    volume {
      name         = "data"
      storage_type = "AzureFile"
      storage_name = local.cae_storage_name
    }

    container {
      name   = "ml-batch"
      image  = var.job_image
      # M1 ingestion đọc studentVle.csv ~450MB vào pandas → cần RAM lớn.
      cpu    = 2.0
      memory = "4Gi"

      # Script orchestration nằm trên share (không rebuild image).
      command = ["python"]
      args    = ["/mnt/data/scripts/ml_pipeline.py"]

      volume_mounts {
        name = "data"
        path = "/mnt/data"
      }

      env {
        name  = "APP_ENV"
        value = var.environment
      }

      # app-facts.md §2.1: đường dẫn ML đang hardcode — override bằng biến môi trường.
      env {
        name  = "LEARNGUARD_DATA_DIR"
        value = "/mnt/data/oulad"
      }

      env {
        name  = "LEARNGUARD_ARTIFACTS_DIR"
        value = "/mnt/data/artifacts"
      }

      env {
        name        = "DATABASE_URL"
        secret_name = "pg-dsn-ml"
      }

      # Script pipeline đọc DSN qua biến này khi ghi ml_predictions.
      env {
        name        = "LEARNGUARD_PG_DSN"
        secret_name = "pg-dsn-ml"
      }
    }
  }
}
  