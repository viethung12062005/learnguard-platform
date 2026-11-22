# AZURE_CONSTRAINTS — Ràng buộc quyền Azure (ĐÃ XÁC MINH 2026-11-04)

> Trí nhớ dài hạn (không commit). Bản đầy đủ: `docs/discovery/azure-permissions-report.md`.
> Bản gốc ngắn: `AZURE_CONSTRAINTS.md` (root).

| Mục | Giá trị |
|---|---|
| Tenant | FPT Corporation (`fpt.com`) |
| Subscription | `FSO-SB-GHCHCS-OJT-DEV` (`c4a86d00-6328-4d7b-8c75-6293553cd19c`) |
| User | `HungTV88@fpt.com` |
| Region | `eastasia` (deploy dev; fallback `southeastasia`) |
| Role | `FSO-SandboxOps` (CustomRole, scope subscription) |

## Quyền (đã xác minh)

- ✅ **Cho phép:** `actions: ["*"]` → mọi resource, **bao gồm `Microsoft.Network/*`** + `*/register/action`.
- ❌ **Cấm (`notActions`):** `Microsoft.Authorization/*/Write` + `*/Delete` (role/role-def/policy/lock); `elevateAccess`; `microsoft.aadiam/*/write`; `Microsoft.Billing/*/write`; Blueprint/Purview-consents/galleries-share/Subscription-cancel+enable/deploymentStacks-manageDenySetting.

## Provider

- **`Microsoft.App` = đang Registering** (đã POST register 2026-11-04; chờ chuyển `Registered`).
- Registered: DBforPostgreSQL, KeyVault, ContainerRegistry, Storage, Web, OperationalInsights, Insights, ManagedIdentity, Authorization, Network.

## Hệ quả cho IaC

- CẤM: `azurerm_role_assignment`/`role_definition`/`policy_assignment`/`management_lock`.
- CHO PHÉP (mới): `Microsoft.Network/*` — dùng được VNet/private endpoint.
- Còn chặn: tự tạo identity+role cho CI → cần Admin hoặc deploy tay.

## Azure Policy (FSO-SZ) — đã xác minh qua deploy 2026-11-04

Sub chịu policy của management group **FSO-SZ**. Các policy ảnh hưởng trực tiếp:

### 1. Tag governance (`tag_governance` — Deny + modify)
- **RG bắt buộc**: `Environment` ∈ {PRD, PREPRD, DEV}, `Region` ∈ {…, "East Asia", …}.
- **Resource khác bắt buộc**: `ServiceOwner`, `Description`, `CreatedBy` (chỉ cần tồn tại).
- **Policy đánh giá tag KHÔNG phân biệt hoa/thường**: nếu có cả `environment` lẫn `Environment` → lỗi `AmbiguousPolicyEvaluationPaths`. Chỉ giữ đúng 1 key theo chữ hoa policy cần.
- `inherit_tags_to_resource_groups` / `inherit_tags_to_resources` (modify) tự thêm ~9 tag từ sub (BU, Budget, BusinessCriticality, DataClassification, Expiration, MonitoringEnable, OwnerAccount, ProjectKey, TicketID) → drift vô hạn → mọi resource có `tags` phải `lifecycle { ignore_changes = [tags] }`.
- `deny-modify-expiration-and-renewal-tags` (sub scope): cấm đặt/sửa tag `Expiration`/`Renewal`.

### 2. Storage public access = Deny
- Policy **"Storage accounts should disable public network access"** (id `b2982f36-99f2-4db5-8eff-283140c09693`) = Deny → MỌI storage account bắt buộc `publicNetworkAccess = Disabled`.
- Hệ quả: **azurerm remote backend KHÔNG dùng được từ máy ngoài VNet** → env/dev dùng **local state**.
- Storage dữ liệu (Azure Files) cũng phải Disabled → ML job truy cập qua private endpoint; **upload dataset ban đầu từ máy ngoài bị chặn** (gap mở — cần jump VM/VNet runner/exemption).

### 3. "Deny Subnet without NSG" = Deny
- Policy definition `Deny-Subnet-Without-Nsg` tại MG **FSO**, assignment `deny-subnet-without-nsg` tại FSO-SZ.
- Bắt MỌI subnet có `networkSecurityGroup.id` ngay trong PUT tạo subnet; chỉ miễn trừ `GatewaySubnet`, `AzureFirewallSubnet`, `AzureFirewallManagementSubnet` (param `excludedSubnets`). **KHÔNG miễn trừ delegated subnet.**
- `azurerm_subnet` không gắn NSG được lúc tạo → **fix = ARM template** (`azurerm_resource_group_template_deployment`) gắn NSG + delegation cùng PUT; subnet id tính tay `<vnet_id>/subnets/<name>`.
- Rủi ro mở: gắn NSG lên delegated subnet (CAE/PG) có thể làm service không provision — cần test; nếu fail → xin FSO exemption.

### 4. Key Vault public access = Deny
- Policy **"Azure Key Vault should disable public network access"** (definition `405c5871-3e91-4644-8a63-58e19d68ff5b`, assignment `8c6fbc6e65e6460b96c574ea`) = Deny → `public_network_access_enabled = false`.
- Hệ quả: `azurerm_key_vault_secret` (data-plane) không ghi được từ máy ngoài VNet → gate sau biến `seed_kv_secrets` (default false); seed sau bằng jump VM/runner trong VNet/ARM control-plane.

### 5. Private DNS zone/link giới hạn 15 tag
- `inherit_tags_to_resources` (modify) thêm ~9 tag → 8 tag riêng + 9 = 17 > 15 → lỗi "maximum of 15 tags".
- Fix: private DNS zone + vnet link chỉ gửi 3 tag bắt buộc (`ServiceOwner`/`Description`/`CreatedBy`) qua local `dns_tags`.
