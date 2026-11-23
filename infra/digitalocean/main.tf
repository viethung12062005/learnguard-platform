locals {
  name_prefix = "learnguard-${var.environment}"
  common_tags = [
    "learnguard",
    "env:${var.environment}",
    "managed-by:terraform"
  ]
}

# -----------------------------------------------------------------------------
# 1. DigitalOcean Private VPC Network
# -----------------------------------------------------------------------------
resource "digitalocean_vpc" "learnguard_vpc" {
  name        = "${local.name_prefix}-vpc"
  region      = var.region
  ip_range    = var.vpc_ip_range
  description = "Isolated VPC network for LearnGuard ${var.environment} MLOps platform"
}

# -----------------------------------------------------------------------------
# 2. Persistent Block Storage Volume for OULAD Dataset, Artifacts & DB Backups
# -----------------------------------------------------------------------------
resource "digitalocean_volume" "learnguard_data" {
  region                  = var.region
  name                    = "${local.name_prefix}-data-vol"
  size                    = var.data_volume_size_gb
  initial_filesystem_type = "ext4"
  description             = "Persistent volume for LearnGuard OULAD CSVs, ML model releases, eval scorecards, and PG backups"
  tags                    = local.common_tags
}

# -----------------------------------------------------------------------------
# 3. Production Ubuntu 24.04 LTS Droplet VM
# -----------------------------------------------------------------------------
resource "digitalocean_droplet" "learnguard_vm" {
  name       = "${local.name_prefix}-vm"
  region     = var.region
  size       = var.droplet_size
  image      = var.droplet_image
  vpc_uuid   = digitalocean_vpc.learnguard_vpc.id
  ssh_keys   = var.ssh_key_fingerprints
  monitoring = true
  backups    = var.enable_backups
  ipv6       = true
  tags       = local.common_tags

  user_data = templatefile("${path.module}/cloud-init.yaml", {
    operator_ssh_public_key = var.operator_ssh_public_key
    environment             = var.environment
  })

  lifecycle {
    ignore_changes = [user_data]
  }
}

resource "digitalocean_volume_attachment" "learnguard_data_attach" {
  droplet_id = digitalocean_droplet.learnguard_vm.id
  volume_id  = digitalocean_volume.learnguard_data.id
}

# -----------------------------------------------------------------------------
# 4. DigitalOcean Cloud Firewall (Defense-in-Depth Perimeter)
#    - Allow HTTP (80) & HTTPS (443) to Nginx reverse proxy from allowed_web_cidrs
#      (restrictable to team/office/VPN CIDRs until BE-08/BE-09 JWT auth ships)
#    - Allow SSH (22) strictly from operator & CI runner CIDRs
#    - Block all direct external access to 5432 (Postgres), 8000 (FastAPI),
#      11434 (Ollama), and 9090 (Prometheus)
# -----------------------------------------------------------------------------
resource "digitalocean_firewall" "learnguard_fw" {
  name        = "${local.name_prefix}-firewall"
  droplet_ids = [digitalocean_droplet.learnguard_vm.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = var.allowed_web_cidrs
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = var.allowed_web_cidrs
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = var.allowed_ssh_cidrs
  }

  inbound_rule {
    protocol         = "icmp"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

# -----------------------------------------------------------------------------
# 5. DigitalOcean Project Assignment
# -----------------------------------------------------------------------------
resource "digitalocean_project" "learnguard_project" {
  name        = "${var.project_name}-${var.environment}"
  description = "LearnGuard Early-Risk Student Advisory & MLOps Platform (${var.environment})"
  purpose     = "Web Application"
  environment = var.environment == "prod" ? "Production" : "Development"
  resources = [
    digitalocean_droplet.learnguard_vm.urn,
    digitalocean_volume.learnguard_data.urn
  ]
}
