# Azure Permissions Report — 2026-11-04

> Khảo sát chỉ-đọc bằng `az` CLI. Không tạo/sửa/xóa resource.

## 1. Danh tính & subscription

| Mục | Giá trị |
|---|---|
| User | `HungTV88@fpt.com` (type: user) |
| Tenant | FPT Corporation — `fpt.com` (`f01e930a-b52e-42b1-b70f-a8882b5d043b`) |
| Subscription | `FSO-SB-GHCHCS-OJT-DEV` (`c4a86d00-6328-4d7b-8c75-6293553cd19c`) |
| signed-in objectId | `d74e18ee-4ab9-4c2b-bdb9-f1eb8c67b3da` |

## 2. Role thực tế: `FSO-SandboxOps` (CustomRole)

- **Scope assignment:** subscription (`/subscriptions/c4a86d00-…`), createdOn 2026-11-04, description "hello".
- **Role definition:** `FSO-SandboxOps`, CustomRole, created 2025-04-04, assignable tại management group `FSO`.
- `permissions[0].actions = ["*"]`
- `permissions[0].notActions`:
  - `Microsoft.Authorization/*/Delete`, `Microsoft.Authorization/*/Write`, `Microsoft.Authorization/elevateAccess/Action`
  - `Microsoft.Blueprint/blueprintAssignments/write`, `Microsoft.Blueprint/blueprintAssignments/delete`
  - `Microsoft.Compute/galleries/share/action`
  - `Microsoft.Purview/consents/write`, `Microsoft.Purview/consents/delete`
  - `Microsoft.Resources/deploymentStacks/manageDenySetting/action`
  - `Microsoft.Subscription/cancel/action`, `Microsoft.Subscription/enable/action`
  - `microsoft.aadiam/*/delete`, `microsoft.aadiam/*/write`
  - `Microsoft.Billing/*/write`

### Diễn giải

| Khả năng | Trạng thái |
|---|---|
| Tạo/sửa resource (App/DB/KV/ACR/Storage/… ) | ✅ `actions:*` |
| **Network (VNet/NSG/private endpoint/private DNS)** | ✅ `actions:*`, không bị chặn → **brief nói "KHÔNG Network" là sai** |
| Đăng ký provider (`*/register/action`) | ✅ (chưa dùng) |
| **Role assignment / role def / policy / lock** | ❌ `Microsoft.Authorization/*/Write+Delete` |
| Ghi AAD (tạo service principal) | ❌ `microsoft.aadiam/*/write` |
| Billing / Blueprint / Purview-consent / hủy subscription | ❌ |

## 3. Provider registration

| Namespace | State |
|---|---|
| Microsoft.App | **NotRegistered** → đã POST `register` (2026-11-04), state **Registering** |
| Microsoft.DBforPostgreSQL | Registered |
| Microsoft.KeyVault | Registered |
| Microsoft.ContainerRegistry | Registered |
| Microsoft.Storage | Registered |
| Microsoft.Web | Registered |
| Microsoft.OperationalInsights | Registered |
| Microsoft.Insights | Registered |
| Microsoft.ManagedIdentity | Registered |
| Microsoft.Authorization | Registered |
| Microsoft.Network | Registered |

## 4. Resource hiện có

- Resource groups: `HCS-POC`, `rg-fooddelivery-lab` (region `southeastasia`).

## 5. Vấn đề môi trường

- `graph.microsoft.com` bị timeout (Read timed out) → lệnh `az` cần Graph (vd `role assignment list --assignee`) treo. Đã dùng ARM `az rest` thay thế.
- Một số gọi ARM bị reset kết nối ngắt quãng (`ConnectionResetError 10054`) — retry là được.

## 6. Open items

- **Q-REGISTER:** ~~đăng ký `Microsoft.App`~~ → **đã chạy** (user OK), state Registering (chờ chuyển Registered).
- **Q-CI-IDENTITY:** không tự tạo SP + không gán role → CI/CD cần Admin (SP/UAMI + gán role) hoặc deploy tay bằng CLI.
- **Q-NETWORK:** nay có quyền Network → chọn public (đơn giản/rẻ) hay private networking (prod-like)?
- **Q-POLICY:** có thể còn Azure Policy deny assignment ở management group `FSO` chặn thêm — chưa xác minh (mạng chập chờn).
