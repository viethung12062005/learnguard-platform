# LearnGuard — Kế hoạch triển khai P1–P8

> File "kiến thức" → không commit. Nguồn: architecture v2 (private networking) + ràng buộc quyền.
> Nguyên tắc xuyên suốt: **không** `roleAssignments`/`roleDefinitions`/`policyAssignments`/`locks` trong IaC; secret qua Key Vault access policy + repo token + account key/SAS.

## P1 — Terraform nền + network + observability (env dev)

- Khởi tạo `infra/` structure: provider, state (backend local/`azurerm` backend), vars, `env/dev`.
- `azurerm_resource_group` `learn-guard-dev`.
- `azurerm_virtual_network` `10.0.0.0/16` + 3 subnet: `snet-cae` (delegated `Microsoft.App/environments`), `snet-pg` (delegated `Microsoft.DBforPostgreSQL/flexibleServers`), `snet-pe`.
- `azurerm_log_analytics_workspace` + `azurerm_application_insights`.
- **Gate:** `terraform plan` sạch, verify không bị Azure Policy deny (Q-POLICY).

## P2 — PostgreSQL private + 2 DB user

- `azurerm_postgresql_flexible_server` `public_network_access=Disabled`, TLS bắt buộc.
- Private endpoint + `privatelink.postgres.database.azure.com` + VNet link.
- Tạo 2 role DB (`lg_ml_writer`, `lg_api`) bằng SQL script (không phải Azure RBAC).
- **Gate:** connect từ trong VNet (CAE) → PG; không public.

## P3 — Key Vault private + access policy + seed secret

- `azurerm_key_vault` private endpoint + `privatelink.vaultcore.azure.net`.
- Access policy cho object-id UAMI của app/job (Secret `get`).
- Seed secret: PG DSN, ACR token, storage key, OpenRouter key, app config (thủ công qua CLI/portal vì không automation).

## P4 — ACR + repo token + push image

- `azurerm_container_registry` (Basic/Standard) + repository-scoped token.
- Build + push image theo **digest** từ `build/` (backend, ml-batch, frontend build artifacts).

## P5 — Container Apps Environment + API (blue/green)

- `azurerm_container_app_environment` VNet-integrated (`snet-cae`).
- `azurerm_container_app` API: ingress external + IP restriction; env từ Key Vault (secret ref); `activeRevisionMode=multiple`.
- Blue/green deploy: revision mới + smoke test + promote/rollback.

## P6 — Azure Files + ML Job

- `azurerm_storage_account` + `storage_share` (data + artifacts); (tùy chọn) private endpoint + firewall.
- `azurerm_container_app_job` ml-batch: mount share, cron score, manual M4 train; exit code 0/1/2.
- **Gate:** job đọc CSV → UPSERT `ml_predictions` (qua private PG).

## P7 — Static Web App (FE) + config/CORS

- `azurerm_static_web_app` deploy FE build; inject API URL + `CORS_ORIGINS` (origin SWA, không `*`).

## P8 — CI/CD + guardrails + runbooks + prod

- GitHub Actions: build + test + push image (không cần quyền Azure); **apply** = CLI tay (hoặc self-hosted runner tái dùng `az login`).
- Guardrail: fail build nếu plan chứa `roleAssignments`/`roleDefinitions`/`policyAssignments`/`locks`.
- Runbooks: deploy, rollback, xoay secret, seed data, score định kỳ.
- **Prod** `env/prod`: nhân bản dev + approval gate + ticket Admin (OIDC UAMI nếu muốn tự động).
- Cost estimate theo SKU đã chọn (Q-PRICE).

## Ticket Admin (song song)

- Xem `learnguard-platform/runbooks/admin-requests.md`: OIDC UAMI + gán role (nếu muốn CI tự động); xác nhận không Azure Policy deny; ACR Premium nếu cần ACR private endpoint.
