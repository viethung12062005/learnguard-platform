# ADR-0006 — CI/CD: self-hosted runner (không cần Admin) + OIDC (cần Admin)

- **Trạng thái:** Accepted
- **Ngày:** 2026-11-04 (sửa 2026-11-04: đính chính — VẪN có CI/CD, CD = self-hosted runner là chính)

## Bối cảnh
Cần deploy lặp lại + rollback. Ràng buộc: **KHÔNG** tự tạo service principal (`microsoft.aadiam/*/write`) và **KHÔNG** gán role (`Microsoft.Authorization/*/Write`). → không tạo được identity CI riêng. Nhưng **vẫn có CI/CD**, vì CI (build/test/push) không cần quyền Azure, còn CD có thể dùng runner tái dùng `az login` của user.

## Quyết định
- **CI (GitHub-hosted runner):** build + test + push image theo digest — chạy tự động, KHÔNG cần quyền Azure.
- **CD (self-hosted runner — đường chính, không cần Admin):** runner chạy trên máy/VM đã `az login` (tài khoản `HungTV88@fpt.com`, role `FSO-SandboxOps`). Workflow deploy chạy trên runner này, thực thi `terraform plan/apply` bằng phiên đăng nhập sẵn → **full CI/CD, không tạo identity mới.**
  - Caveat: máy runner phải online khi chạy; `az login` phải định kỳ re-auth (refresh token hết hạn); runner mang credential user → pin action theo SHA, chỉ repo tin cậy.
- **OIDC + UAMI (chuẩn production, cần Admin):** Admin tạo UAMI + gán Contributor(RG) + `federatedIdentityCredentials` → ticket `admin-requests.md`. Hướng nên chuyển khi có Admin.
- **Deploy tay CLI = bootstrap/fallback** (không phải đường chính): dùng khi chưa dựng runner hoặc chạy 1 lần.
- Build image **immutable theo digest** (`sha256:...`), không deploy theo tag động.
- **Release manifest (gitops)** `deploy/releases/{dev,prod}.yaml`: app git SHA + image digest + config → deploy tái lập được.
- **Blue/green**: Container Apps multiple revisions + routing → smoke test → promote; fail → revert traffic (rollback).
- Pin action theo commit SHA; mask secret (`::add-mask::`).

## Vì sao KHÔNG dùng "credential GitHub cất trong Key Vault" làm cách cấp quyền
- Key Vault chỉ giải quyết **"cất secret ở đâu"** (authentication material), không giải quyết **"cấp quyền cho ai"** (authorization = RBAC role assignment).
- GitHub **PAT** chỉ xác thực với **GitHub**, không với Azure ARM → không tạo resource Azure.
- **SP client secret** cất KV vẫn cần SP **tồn tại** + **được gán role** — 2 bước do Admin làm. KV không bỏ qua được.
- → Key Vault là nơi **cất** secret đúng chuẩn (sau khi có identity), không phải cách **tạo** quyền.

## Hệ quả
- Full CI/CD khả thi ngay, không chờ Admin (self-hosted runner).
- Rollback nhanh ở tầng revision (không rebuild).
- Caveat self-hosted runner (online + re-auth + security) → ghi runbook.

## Cần xác minh
- Cài runner + `az` + `terraform` trên máy/VM; thời hạn refresh token `az login`.
- Nếu đi OIDC: quyền tạo `Microsoft.ManagedIdentity/userAssignedIdentities` + `federatedIdentityCredentials` (vẫn cần Admin để gán role).
