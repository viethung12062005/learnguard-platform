terraform {
  required_version = ">= 1.9.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # KHÔNG khai báo backend: bootstrap dùng LOCAL state theo thiết kế.
  # Lý do (chicken-and-egg): state của các env được lưu trong storage account
  # do chính root này tạo ra — không thể lưu state của bootstrap ở đó.
  # File terraform.tfstate ở đây đã nằm trong .gitignore.
}
