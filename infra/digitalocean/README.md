# LearnGuard — DigitalOcean Infrastructure-as-Code (Terraform)

Thư mục này định nghĩa toàn bộ hạ tầng đích trên **DigitalOcean** cho hệ thống **LearnGuard** theo quyết định kiến trúc [ADR-0008](../../../docs/adr/0008-cloud-migration-digitalocean-vm.md) và [DigitalOcean Target Architecture v3](../../../docs/architecture/digitalocean-target-architecture.md).

## 1. Tài nguyên được Khởi tạo

| Tài nguyên Terraform | Vai trò trong Kiến trúc LearnGuard |
| :--- | :--- |
| `digitalocean_vpc.learnguard_vpc` | Mạng riêng ảo (`10.116.0.0/20`) tại region `sgp1` cô lập lưu lượng nội bộ. |
| `digitalocean_droplet.learnguard_vm` | Máy chủ Ubuntu 24.04 LTS (`s-4vcpu-8gb`), bật giám sát (`monitoring = true`) và sao lưu tự động (`backups = true`), gắn `cloud-init.yaml`. |
| `digitalocean_volume.learnguard_data` | Ổ đĩa Block Storage `ext4` bền vững (50 GiB) lưu trữ dữ liệu OULAD, model releases (`active_release.json`), scorecards (`eval-report.v1`, `drift-report.v1`) và bản sao lưu PostgreSQL. |
| `digitalocean_firewall.learnguard_fw` | Cloud Firewall chặn hoàn toàn các cổng nội bộ (`5432` PostgreSQL, `8000` FastAPI, `11434` Ollama, `9090` Prometheus) khỏi Internet; chỉ mở `80/443` cho Nginx và `22` cho `allowed_ssh_cidrs`. |
| `digitalocean_project.learnguard_project` | Gom nhóm tài nguyên theo môi trường (`prod` / `staging`) trên DigitalOcean Control Panel. |

## 2. Hướng dẫn Sử dụng

```bash
cd learnguard-platform/infra/digitalocean

# 1. Sao chép file cấu hình mẫu và điền thông số
cp terraform.tfvars.example terraform.tfvars

# 2. Xuất DigitalOcean Personal Access Token
export DIGITALOCEAN_TOKEN="dop_v1_..."

# 3. Khởi tạo provider và kiểm tra cú pháp
terraform init
terraform fmt -check
terraform validate

# 4. Xem kế hoạch thay đổi và áp dụng
terraform plan -out=tfplan
terraform apply tfplan
```

## 3. Khởi tạo VM Thủ công (Không dùng Terraform)

Nếu bạn đã tạo sẵn một Droplet Ubuntu 22.04/24.04 trên giao diện DigitalOcean, bạn có thể chạy trực tiếp script bootstrap idempotent:

```bash
scp learnguard-platform/scripts/do/bootstrap-vm.sh root@<DROPLET_IP>:/tmp/
ssh root@<DROPLET_IP> "bash /tmp/bootstrap-vm.sh"
```
