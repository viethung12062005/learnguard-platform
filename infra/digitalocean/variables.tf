variable "do_token" {
  description = "DigitalOcean API personal access token (read+write). Set via TF_VAR_do_token or DIGITALOCEAN_TOKEN."
  type        = string
  sensitive   = true
  default     = null
}

variable "project_name" {
  description = "DigitalOcean Project name for organizing LearnGuard resources."
  type        = string
  default     = "learnguard-mlops"
}

variable "environment" {
  description = "Deployment environment label (prod or staging)."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["prod", "staging", "dev"], var.environment)
    error_message = "environment must be one of: prod, staging, dev."
  }
}

variable "region" {
  description = "DigitalOcean datacenter region (e.g. sgp1 for Singapore)."
  type        = string
  default     = "sgp1"
}

variable "vpc_ip_range" {
  description = "Private RFC1918 CIDR block for the LearnGuard DigitalOcean VPC."
  type        = string
  default     = "10.116.0.0/20"
}

variable "droplet_size" {
  description = "DigitalOcean Droplet slug (s-4vcpu-8gb recommended for full OULAD M1-M5 + FastAPI + PG16)."
  type        = string
  default     = "s-4vcpu-8gb"
}

variable "droplet_image" {
  description = "Base OS image slug for the Droplet."
  type        = string
  default     = "ubuntu-24-04-x64"
}

variable "data_volume_size_gb" {
  description = "Size in GiB of the persistent DigitalOcean Block Storage volume mounted at /opt/learnguard/data."
  type        = number
  default     = 50
}

variable "ssh_key_fingerprints" {
  description = "List of SSH public key fingerprints or IDs registered in DigitalOcean for initial provisioning."
  type        = list(string)
  default     = []
}

variable "operator_ssh_public_key" {
  description = "SSH public key injected into cloud-init for the non-root lgops user. Must be configured explicitly in terraform.tfvars."
  type        = string

  validation {
    condition = (
      (startswith(var.operator_ssh_public_key, "ssh-ed25519 ") || startswith(var.operator_ssh_public_key, "ssh-rsa ")) &&
      !strcontains(var.operator_ssh_public_key, "Placeholder")
    )
    error_message = "operator_ssh_public_key must start with 'ssh-ed25519 ' or 'ssh-rsa ' and must not contain 'Placeholder'."
  }
}

variable "allowed_ssh_cidrs" {
  description = "List of CIDR blocks permitted to reach TCP port 22 (Operator IP + GitHub Actions deploy runners). Must be configured explicitly in terraform.tfvars."
  type        = list(string)

  validation {
    condition = (
      length(var.allowed_ssh_cidrs) > 0 &&
      alltrue([
        for cidr in var.allowed_ssh_cidrs :
        !contains(["0.0.0.0/0", "::/0"], trimspace(cidr))
      ])
    )
    error_message = "allowed_ssh_cidrs must contain at least one CIDR block and must not contain unrestricted 0.0.0.0/0 or ::/0."
  }
}

variable "allowed_web_cidrs" {
  description = "List of CIDR blocks permitted to reach HTTP (80) and HTTPS (443). Operators can restrict this to team/office/VPN CIDRs as a pre-auth perimeter control until BE-08/BE-09 JWT authentication ships."
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]

  validation {
    condition     = length(var.allowed_web_cidrs) > 0
    error_message = "allowed_web_cidrs must contain at least one CIDR block."
  }
}

variable "enable_backups" {
  description = "Enable DigitalOcean automated weekly Droplet disk backups."
  type        = bool
  default     = true
}
