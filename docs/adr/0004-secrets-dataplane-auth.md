# ADR-0004 — Secrets & data-plane auth (không RBAC role)

- **Trạng thái:** Accepted
- **Ngày:** 2026-11-04 (sửa 2026-11-04: thêm private endpoint, sửa guardrail)

## Bối cảnh
Không có quyền `Microsoft.Authorization/roleAssignments/write` → không gán RBAC role (AcrPull, Key Vault Secrets User, Storage Blob Data *). Cần cách cấp quyền data-plane. Nay có `Microsoft.Network/*` → thêm private endpoint cho secret/data path.

## Quyết định
- **Key Vault:** dùng **access policy** (gán object-id của UAMI app/job) — KHÔNG dùng RBAC model; **private endpoint** vào `snet-pe` + private DNS `privatelink.vaultcore.azure.net` (KHÔNG public access).
- **ACR:** **repository-scoped token** (hoặc admin user) cho pull image; token lưu Key Vault, nhập vào `registry` config của Container App. ACR **giữ public + token** vì private-endpoint ACR cần SKU Premium (đắt) → hoãn.
- **Storage (Azure Files):** mount bằng **account key / SAS** (không managed-identity RBAC data role); (tùy chọn) private endpoint + storage firewall để lock.
- Managed identity của app/job chỉ dùng để **authenticate Key Vault access policy** (đây không phải RBAC role).

## Hệ quả
- Tránh hoàn toàn `roleAssignments` trong IaC.
- Key Vault không public → secret không ra internet (prod-like).
- Token/key là secret → xoay vòng thủ công (runbook) vì không có automation RBAC.
- Guardrail fail build nếu phát hiện `roleAssignments`/`roleDefinitions`/`policyAssignments`/`management_lock` trong plan. (Bỏ `Microsoft.Network` khỏi guardrail vì nay đã được phép.)

## Cần xác minh
- `Microsoft.ContainerRegistry/registries/tokens/write` + `Microsoft.KeyVault/vaults/write` (access policy) khả dụng.
- Private endpoint ACR nếu sau này chuyển Premium.
