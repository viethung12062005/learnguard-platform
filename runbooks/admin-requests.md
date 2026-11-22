# Admin Requests — LearnGuard (ticket gửi Admin)

> Runbook: danh sách những việc **chỉ Admin làm được** do role `FSO-SandboxOps` không có quyền
> `Microsoft.Authorization/*/Write+Delete` và `microsoft.aadiam/*/write`.

## 1. (Tùy chọn — chỉ khi muốn CI/CD tự động) Service principal / UAMI + gán role

- **Mục đích:** để GitHub Actions (OIDC) hoặc runner deploy thay cho deploy tay.
- **Yêu cầu Admin:**
  1. Tạo **User-Assigned Managed Identity** (hoặc service principal) cho CI, ví dụ `lg-ci-{env}`.
  2. Gán role **Contributor** (hoặc custom role tối thiểu) trên resource group `learn-guard-{dev,prod}`.
  3. Cấu hình **federated credential** (GitHub OIDC: issuer `https://token.actions.githubusercontent.com`, subject theo repo+branch) — hoặc cấp cho chúng tôi quyền `federatedIdentityCredentials/write`.
- **Nếu không:** chúng tôi deploy **tay bằng CLI** (tài khoản `HungTV88@fpt.com` đã có role), không chặn tiến độ.

## 2. Xác nhận không có Azure Policy / deny assignment

- **Mục đích:** đảm bảo tạo VNet, private endpoint, PostgreSQL Flexible, Key Vault, ACR, Storage, Container Apps không bị chặn ở management group `FSO`.
- **Yêu cầu Admin:** xác nhận hoặc liệt kê policy/deny assignment áp lên subscription `FSO-SB-GHCHCS-OJT-DEV` có thể chặn các resource trên.

## 3. (Tùy chọn) ACR SKU Premium nếu cần private endpoint cho ACR

- **Mục đích:** ACR private endpoint yêu cầu **Premium**. Hiện chúng tôi dùng ACR public + repo-scoped token (không cần).
- **Yêu cầu Admin:** chỉ khi sau này yêu cầu ACR nằm sau private endpoint.

## 4. Quota / giới hạn (nếu gặp)

- Nếu deploy gặp lỗi quota (số vCPU Container Apps, số public IP, dung lượng PG), sẽ escalate kèm mã lỗi cụ thể.

## Thông tin nhận dạng

- Subscription: `FSO-SB-GHCHCS-OJT-DEV` (`c4a86d00-6328-4d7b-8c75-6293553cd19c`)
- Resource group dự kiến: `learn-guard-dev`, `learn-guard-prod` (region `southeastasia`)
- Người yêu cầu: `HungTV88@fpt.com`
