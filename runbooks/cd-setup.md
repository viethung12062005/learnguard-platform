# Runbook — Thiết lập CD (self-hosted runner)

> CD chạy trên **máy của bạn** và tái dùng phiên `az login` sẵn có.
> Đây là cách duy nhất chạy CD tự động mà **không cần Admin** (vì không tạo được
> service principal và không gán được role).

---

## 1. Tạo repo GitHub và push

```powershell
cd D:\Learn-guard\learnguard-platform
git init
git add .
git commit -m "Initial infrastructure and CD pipeline"
git branch -M main
git remote add origin https://github.com/<org>/learnguard-platform.git
git push -u origin main
```

> `.gitignore` đã chặn `terraform.tfvars`, `backend.hcl`, `*.tfstate`, `plan.json`.
> Kiểm tra bằng `git status` trước khi commit lần đầu.

---

## 2. Cài self-hosted runner trên máy

Vào **Repo → Settings → Actions → Runners → New self-hosted runner → Windows**.

Làm theo lệnh GitHub đưa ra, nhưng **thêm label**:

```powershell
.\config.cmd --url https://github.com/<org>/learnguard-platform --token <TOKEN> --labels learnguard
```

Điều kiện bắt buộc:

| Yêu cầu | Lý do |
|---|---|
| Runner chạy dưới **đúng user** đã `az login` | `az` lưu phiên trong `%USERPROFILE%\.azure` |
| `terraform` có trong PATH của user đó | workflow gọi `terraform` trực tiếp |
| `python` có trong PATH | guardrail |
| Runner **không** bật cho fork / PR từ ngoài | runner mang credential của bạn |

Kiểm tra sau khi runner online:

```powershell
# Chạy trên máy runner
az account show --query "{sub:name, user:user.name}" -o table
terraform version
python --version
```

Nếu `az` hết hạn phiên: `az login` lại. Workflow sẽ fail với thông báo rõ nếu thiếu phiên.

> ⚠️ **Bảo mật:** self-hosted runner = quyền của chính bạn. Chỉ dùng repo **private**,
> bật *Require approval for all outside collaborators*, không thêm runner cho repo public.

---

## 3. Cấu hình Variables và Secrets

**Settings → Secrets and variables → Actions**

### Variables (không phải secret)

| Tên | Ví dụ | Lấy từ |
|---|---|---|
| `TF_BACKEND_RG` | `learn-guard-tfstate` | output bootstrap |
| `TF_BACKEND_SA` | `lgstateab12cd` | output bootstrap |
| `TF_BACKEND_CONTAINER` | `tfstate` | output bootstrap |
| `TF_STATE_KEY` | `dev.terraform.tfstate` | cố định |
| `RESOURCE_GROUP` | `learn-guard-dev` | `terraform output resource_group_name` |
| `API_APP_NAME` | `lg-dev-api` | tên Container App API |
| `APP_ORG` | org GitHub của bạn | — |
| `API_BASE_URL` | `https://<api fqdn>` | `terraform output api_fqdn` |

### Secrets

| Tên | Dùng cho | Lấy từ |
|---|---|---|
| `SWA_API_TOKEN` | deploy frontend | `terraform output -raw` không in được secret — lấy trong Portal: Static Web App → Manage deployment token |
| `APPS_READ_TOKEN` | CI checkout 3 repo app | PAT read-only trên repo app (nếu repo private) |

---

## 4. Chạy CD

### 4.1 Hạ tầng

**Actions → CD · dev · infrastructure → Run workflow**

- `action = plan` → chỉ plan + guardrail
- `action = apply` → apply đúng plan đã duyệt

Có `environment: dev` → có thể bật *Required reviewers* trong Settings → Environments để chặn apply tự động.

### 4.2 Ứng dụng (image)

**Actions → CD · dev · app image → Run workflow**

- `component = api` hoặc `ml-job`
- `image` = `acrdevxxxx.azurecr.io/learnguard-api@sha256:...` (bắt buộc có digest)

Luồng: plan → guardrail → apply → smoke test `/health`.
Smoke fail → **tự động rollback** traffic về revision trước (không rebuild).

### 4.3 Frontend

**Actions → CD · dev · frontend → Run workflow** với `ref` của FE-MLOPS.

---

## 5. CD trên GitHub-hosted runner (dùng token / service principal)

Có **hai** pipeline CD song song. Chọn một:

| Workflow | Runner | Cần Admin? | Khi nào dùng |
|---|---|---|---|
| `cd-dev-infra.yml` | self-hosted (máy bạn) | Không | dùng ngay |
| `cd-dev-infra-hosted.yml` | GitHub-hosted | **Có** (identity + role) | khi có SP/UAMI |

### 5.1 Lấy `AZURE_CREDENTIALS` mà KHÔNG tự tạo SP

Role `FSO-SandboxOps` chặn tạo SP + gán role. Nhưng nếu **bạn đã có** một service principal
đã được cấp quyền trên subscription/RG này, chỉ cần dựng JSON:

```json
{
  "clientId": "<appId của SP>",
  "clientSecret": "<secret>",
  "subscriptionId": "c4a86d00-6328-4d7b-8c75-6293553cd19c",
  "tenantId": "f01e930a-b52e-42b1-b70f-a8882b5d043b"
}
```

Lưu vào **Settings → Secrets → Actions → `AZURE_CREDENTIALS`**.

> ⚠️ **Không dùng** các SP của platform FPT (ví dụ `FSO.ITCloud - ALZ Subscription Auto`,
> `FSO.ITCloud - ALZ Dev Auto`) dù chúng có role Owner. Đó là automation của hạ tầng chung.
> Cũng **không** chạy `az ad sp credential reset` lên SP không do bạn sở hữu.

### 5.2 Nếu chưa có SP nào của riêng bạn

Gửi `admin-requests.md` §1. Admin cần làm đúng 3 việc:

1. Tạo App Registration + Service Principal (hoặc UAMI)
2. Gán **Contributor** trên scope `learn-guard-dev` (không phải cả subscription)
3. Trả về `appId` + `clientSecret` (hoặc cấu hình federated credential cho OIDC)

Sau đó điền secret `AZURE_CREDENTIALS` (hoặc 3 vars OIDC) là xong.

### 5.3 Kiểm tra token có đúng quyền trước khi tin

```powershell
az login --service-principal -u <appId> -p <secret> --tenant <tenantId>
az account show
az group exists -n learn-guard-dev          # phải trả true
az role assignment list --assignee <objectId> --all --query "[].{role:roleDefinitionName, scope:scope}" -o table
```

Nếu `az group exists` báo lỗi 403 → SP chưa có quyền, đừng đưa vào GitHub Secrets.

## 6. Chuyển hẳn sang OIDC (khuyến nghị khi đã có UAMI)

1. Gửi `runbooks/admin-requests.md` §1 cho Admin.
2. Admin cấp: UAMI + role Contributor trên `learn-guard-dev` + federated credential
   (`issuer = https://token.actions.githubusercontent.com`,
   `subject = repo:<org>/learnguard-platform:ref:refs/heads/main`,
   `audience = api://AzureADTokenExchange`).
3. Thêm Variables: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`.
4. Chạy `cd-dev-infra-hosted.yml` với `auth_method = oidc`.
5. Tắt `cd-dev-infra.yml` (đổi đuôi thành `.disabled`) nếu không cần self-hosted nữa.

Lúc đó CD chạy được trên GitHub-hosted runner, không phụ thuộc máy bạn, và không có secret dài hạn.

---

## 7. Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| `Runner chưa có phiên az login` | runner chạy user khác / phiên hết hạn | `az login` dưới đúng user chạy runner |
| `terraform: not recognized` | PATH của runner thiếu | thêm vào PATH user, restart runner service |
| `tfplan` không tải về được | artifact hết hạn (3 ngày) | chạy lại job plan |
| Guardrail fail | plan có resource cần Admin | xem danh sách, đó là việc của Admin |
| Smoke fail liên tục | API không có `/health` hoặc image sai | kiểm tra `target_port` và log Container App |
| Runner offline | máy tắt / service dừng | bật máy, `.\run.cmd` hoặc restart service |
