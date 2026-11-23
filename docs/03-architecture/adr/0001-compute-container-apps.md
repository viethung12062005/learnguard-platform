# ADR-0001 — Compute: Azure Container Apps (API + Jobs), không AKS

- **Trạng thái:** Accepted
- **Ngày:** 2026-11-04 (duyệt 2026-11-04; sửa: VNet integration BẬT — ràng buộc "không Network" là sai)

## Bối cảnh
Cần chạy 2 loại workload: API FastAPI (luôn bật, scale-to-zero) và ML batch M1→M5 (job định kỳ, không mở port). Ràng buộc: không RBAC role-assignment, không AKS. Xác minh quyền cho thấy `Microsoft.Network/*` **có sẵn** → dùng được VNet.

## Quyết định
Dùng **Azure Container Apps**: `Container App` cho backend API (ingress external + IP restriction) và `Container App Job` cho ML batch (trigger manual/cron, không ingress). KHÔNG dùng AKS, KHÔNG dùng VM.

**Container Apps Environment được VNet-integrated** (`infrastructure_subnet_id` = `snet-cae`, delegated `Microsoft.App/environments`).

## Hệ quả
- Scale-to-zero → rẻ nhất cho dev (D-011, D-012).
- VNet integration cho phép outbound tới PostgreSQL private, Key Vault private endpoint.
- Egress đi qua subnet → kiểm soát được bằng NSG (khác v1 nói "dùng VNet Microsoft quản lý").
- Không phải quản OS/Docker/ingress/TLS — so với VM đây là ít việc hơn.

## Cần xác minh
- `Microsoft.App` khả dụng ở `eastasia` (nếu không, fallback `southeastasia`).
- Quyền tạo `Microsoft.App/managedEnvironments` + `containerApps`/`jobs` (đã có qua `actions:*`).
