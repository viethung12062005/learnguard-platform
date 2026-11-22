resource "azurerm_virtual_network" "this" {
  name                = var.vnet_name
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = [var.address_space]
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

# ---------------------------------------------------------------------------
# NSG — snet-cae
# API cần nhận traffic 443 từ Internet (public ingress). Các cổng khác đóng.
# ---------------------------------------------------------------------------
resource "azurerm_network_security_group" "cae" {
  name                = "nsg-snet-cae"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }

  security_rule {
    name                       = "allow-https-internet"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-vnet-inbound"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-azure-lb"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "*"
  }
}

# ---------------------------------------------------------------------------
# NSG — snet-pg
# Chỉ nhận 5432 từ subnet CAE. Không mở outbound restriction ở đây:
# PostgreSQL Flexible cần ra ngoài cho backup/telemetry nội bộ của Azure.
# ---------------------------------------------------------------------------
resource "azurerm_network_security_group" "pg" {
  name                = "nsg-snet-pg"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }

  security_rule {
    name                       = "allow-postgres-from-cae"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "5432"
    source_address_prefix      = var.cae_subnet_prefix
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-vnet-inbound"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-azure-lb"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "deny-internet-inbound"
    priority                   = 4000
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }
}

# ---------------------------------------------------------------------------
# NSG — snet-pe
# ---------------------------------------------------------------------------
resource "azurerm_network_security_group" "pe" {
  name                = "nsg-snet-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }

  security_rule {
    name                       = "allow-vnet-inbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-azure-lb"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "*"
  }
}

# ---------------------------------------------------------------------------
# NSG — snet-jump
# Chỉ cho SSH (22) từ IP người vận hành. Dùng để vào VNet seed KV/PG/storage.
# ---------------------------------------------------------------------------
resource "azurerm_network_security_group" "jump" {
  name                = "nsg-snet-jump"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }

  security_rule {
    name                       = "allow-ssh-operator"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.jump_ssh_source_prefix
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-vnet-inbound"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "deny-internet-inbound"
    priority                   = 4000
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }
}

# ---------------------------------------------------------------------------
# Subnets — tạo qua ARM template (không dùng azurerm_subnet).
#
# LÝ DO: Azure Policy "Deny Subnet without NSG" (FSO) bắt mọi subnet PHẢI có
# `networkSecurityGroup.id` ngay trong PUT tạo subnet (chỉ miễn trừ Gateway/
# Firewall subnet). azurerm_subnet KHÔNG có argument gắn NSG lúc tạo — chỉ có
# `azurerm_subnet_network_security_group_association` gắn SAU khi tạo → luôn bị
# policy Deny. ARM template gắn NSG + delegation trong cùng một PUT nên thoả.
# ---------------------------------------------------------------------------
resource "azurerm_resource_group_template_deployment" "subnets" {
  name                = "subnets-${var.vnet_name}"
  resource_group_name = var.resource_group_name
  deployment_mode     = "Incremental"
  tags                = var.tags

  lifecycle {
    # ARM chuẩn hoá tag (Azure Policy modify) gây diff vô hạn → bỏ qua tag.
    # template_content KHÔNG ignore nữa: cần cập nhật khi thêm subnet mới.
    ignore_changes = [tags]
  }

  parameters_content = jsonencode({
    vnetName   = { value = azurerm_virtual_network.this.name }
    caePrefix  = { value = var.cae_subnet_prefix }
    pgPrefix   = { value = var.pg_subnet_prefix }
    pePrefix   = { value = var.pe_subnet_prefix }
    jumpPrefix = { value = var.jump_subnet_prefix }
    caeNsgId   = { value = azurerm_network_security_group.cae.id }
    pgNsgId    = { value = azurerm_network_security_group.pg.id }
    peNsgId    = { value = azurerm_network_security_group.pe.id }
    jumpNsgId  = { value = azurerm_network_security_group.jump.id }
  })

  template_content = jsonencode({
    "$schema"      = "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
    contentVersion = "1.0.0.0"
    parameters = {
      vnetName   = { type = "string" }
      caePrefix  = { type = "string" }
      pgPrefix   = { type = "string" }
      pePrefix   = { type = "string" }
      jumpPrefix = { type = "string" }
      caeNsgId   = { type = "string" }
      pgNsgId    = { type = "string" }
      peNsgId    = { type = "string" }
      jumpNsgId  = { type = "string" }
    }
    resources = [
      {
        type       = "Microsoft.Network/virtualNetworks/subnets"
        apiVersion = "2023-09-01"
        name       = "[format('{0}/snet-cae', parameters('vnetName'))]"
        properties = {
          addressPrefix        = "[parameters('caePrefix')]"
          networkSecurityGroup = { id = "[parameters('caeNsgId')]" }
          delegations = [
            {
              name       = "cae-delegation"
              properties = { serviceName = "Microsoft.App/environments" }
            }
          ]
        }
      },
      {
        type       = "Microsoft.Network/virtualNetworks/subnets"
        apiVersion = "2023-09-01"
        name       = "[format('{0}/snet-pg', parameters('vnetName'))]"
        properties = {
          addressPrefix        = "[parameters('pgPrefix')]"
          networkSecurityGroup = { id = "[parameters('pgNsgId')]" }
          delegations = [
            {
              name       = "pg-delegation"
              properties = { serviceName = "Microsoft.DBforPostgreSQL/flexibleServers" }
            }
          ]
        }
      },
      {
        type       = "Microsoft.Network/virtualNetworks/subnets"
        apiVersion = "2023-09-01"
        name       = "[format('{0}/snet-pe', parameters('vnetName'))]"
        properties = {
          addressPrefix        = "[parameters('pePrefix')]"
          networkSecurityGroup = { id = "[parameters('peNsgId')]" }
        }
      },
      {
        type       = "Microsoft.Network/virtualNetworks/subnets"
        apiVersion = "2023-09-01"
        name       = "[format('{0}/snet-jump', parameters('vnetName'))]"
        properties = {
          addressPrefix        = "[parameters('jumpPrefix')]"
          networkSecurityGroup = { id = "[parameters('jumpNsgId')]" }
        }
      }
    ]
  })
}
