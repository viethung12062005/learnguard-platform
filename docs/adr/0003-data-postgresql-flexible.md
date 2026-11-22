# ADR-0003 — Data: PostgreSQL Flexible Server (private endpoint, 2 DB users)

- **Trạng thái:** Accepted
- **Ngày:** 2026-11-04 (sửa 2026-11-04: chuyển public → private)

## Bối cảnh
PostgreSQL dùng chung: ml-data GHI `ml_predictions`, backend chỉ SELECT + sở hữu các bảng riêng. Xác minh quyền cho thấy `Microsoft.Network/*` **có sẵn** → dùng được private endpoint/VNet integration (v1 ghi "không Network" là sai).

## Quyết định
- `azurerm_postgresql_flexible_server` với **`public_network_access=Disabled`** — không public endpoint, không firewall-rule công khai.
- Truy cập qua **delegated subnet** `snet-pg` (VNet injection, delegation `Microsoft.DBforPostgreSQL/flexibleServers`) + **private DNS zone** `privatelink.postgres.database.azure.com` (link vào VNet).
- **TLS bắt buộc** (`sslmode=require`) dù là private (defense-in-depth).
- **Tách 2 DB user** (least-privilege data-plane, làm ở tầng PG không cần Azure RBAC):
  - `lg_ml_writer`: INSERT/UPDATE/SELECT trên `ml_predictions`.
  - `lg_api`: SELECT trên `ml_predictions` + full trên bảng backend sở hữu.
- Schema `ml_predictions` do ml-data `ensure_schema()`; bảng backend do Alembic.

## Hệ quả
- Container Apps (API + Job) phải **VNet-integrated** để outbound tới PG (delegated subnet, private).
- Không còn phụ thuộc dải egress IP động → **khép kín** firewall, tốt hơn v1.
- DSN là secret trong Key Vault (cũng private); không hardcode.
- Thêm phần Terraform dễ sót: private DNS zone + `virtual_network_link`.

## Cần xác minh
- SKU nhỏ nhất đủ dùng (Burstable) + chi phí (P0.6).
- Quyền tạo `Microsoft.DBforPostgreSQL/flexibleServers` + private endpoint + private DNS zone.
