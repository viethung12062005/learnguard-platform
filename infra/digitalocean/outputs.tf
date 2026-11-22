output "droplet_id" {
  description = "DigitalOcean Droplet ID"
  value       = digitalocean_droplet.learnguard_vm.id
}

output "droplet_public_ipv4" {
  description = "Public IPv4 address of the LearnGuard Droplet (configure as DO_HOST in GitHub Secrets)"
  value       = digitalocean_droplet.learnguard_vm.ipv4_address
}

output "droplet_private_ipv4" {
  description = "Private VPC IPv4 address of the LearnGuard Droplet"
  value       = digitalocean_droplet.learnguard_vm.ipv4_address_private
}

output "vpc_id" {
  description = "DigitalOcean VPC UUID"
  value       = digitalocean_vpc.learnguard_vpc.id
}

output "data_volume_id" {
  description = "Persistent Block Storage Volume ID"
  value       = digitalocean_volume.learnguard_data.id
}

output "firewall_id" {
  description = "DigitalOcean Cloud Firewall ID"
  value       = digitalocean_firewall.learnguard_fw.id
}
