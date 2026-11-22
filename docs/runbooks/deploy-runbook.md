# Hướng dẫn triển khai LearnGuard lên Azure — từ đầu đến cuối

> Tài liệu này chép lại **đúng các bước đã chạy thành công** ngày 2026-11-05.
> Mỗi bước gồm: mục đích → lệnh → kết quả mong đợi → lỗi thường gặp.
> Làm tuần tự từ mục 1 đến mục 12 là có một môi trường chạy thật.
> Mục 14–15 dành cho destroy và triển khai lại.
>
> Quy ước: lệnh PowerShell chạy trên **máy bạn**; lệnh bash trong khối ```bash ``` chạy
> trên **jump VM**. Những chỗ có `<...>` là giá trị bạn phải thay.
>
> **Chỉ muốn copy-paste lệnh?** Dùng [`commands-only.md`](commands-only.md) — cùng quy trình,
> không có phần giải thích, mọi giá trị tự lấy từ biến và `terraform output`.

---

## 0. Bức tranh tổng thể

Luồng triển khai có 9 giai đoạn:

```
[1] terraform apply (hạ tầng, chưa có app)
        ↓
[2] build image → push vào ACR → lấy digest
        ↓
[3] SSH vào jump VM (nằm trong VNet)
        ↓
[4] tạo schema DB + role + ghi secret vào Key Vault
        ↓
[5] upload dataset OULAD + script pipeline lên Azure Files
        ↓
[6] terraform apply lần 2 (bật Container App API + Job ML)
        ↓
[7] chạy job ML → sinh dự đoán vào PostgreSQL
        ↓
[8] build + deploy frontend lên Static Web App
        ↓
[9] kiểm thử đầu-cuối
```

Lý do phải chia làm hai lần apply: Container App cần image đã tồn tại trong ACR. Nếu bật
`deploy_apps = true` khi ACR còn rỗng, app sẽ tạo ra nhưng không khởi động được.

---

## 1. Tài nguyên sẽ được tạo

Hậu tố `<s>` là chuỗi 5 ký tự ngẫu nhiên do Terraform sinh (ví dụ `cjalc`). Hậu tố này
nằm trong state — **giữ state là giữ nguyên tên tài nguyên**.

| Nhóm | Tài nguyên | Tên |
|---|---|---|
| Mạng | VNet | `vnet-lg-dev` (10.20.0.0/16) |
| | Subnet | `snet-cae` /23, `snet-pg` /24, `snet-pe` /24, `snet-jump` /24, `snet-app`, `snet-data` |
| | NSG | mỗi subnet một NSG (policy bắt buộc) |
| Bảo mật | Key Vault | `kv-lg-dev-<s>` (public access tắt) |
| | Managed identity | `id-lg-dev-api`, `id-lg-dev-job` |
| Dữ liệu | PostgreSQL Flexible | `psql-lg-dev-<s>` (private DNS, subnet `snet-pg`) |
| | Storage account + share | `stlgdev<s>` / `lgdata` (16 GB) |
| Registry | ACR | `acrdev<s>` |
| Quan sát | Log Analytics + App Insights | `log-lg-dev`, `appi-lg-dev` |
| Compute | Container Apps Env | `cae-lg-dev` (subnet `snet-cae`) |
| | Container App (API) | `ca-lg-dev-api` |
| | Container App Job (ML) | `caj-lg-dev-ml` |
| Truy cập | Jump VM | `vm-az-lg-jump` (Standard_D2as_v5) |
| Frontend | Static Web App | `swa-lg-dev` (Free) |

Tên có ràng buộc riêng của Azure (đã xử lý trong `locals.tf`):

- Key Vault ≤ 24 ký tự, chỉ chữ + số + gạch nối.
- Storage/ACR chỉ chữ thường + số, ≤ 24 ký tự.
- VM phải bắt đầu `vm-az-` và ≤ 15 ký tự → `vm-az-lg-jump` (13 ký tự).

---

## 2. Điều kiện tiên quyết

| Công cụ | Phiên bản đã dùng | Kiểm tra |
|---|---|---|
| Azure CLI | 2.6x | `az version` |
| Terraform | 1.15.8 | `terraform version` |
| Docker Desktop | bất kỳ | `docker version` |
| Node.js + npm | 20+ | `node -v` |
| OpenSSH client | có sẵn Windows 11 | `ssh -V` |
| Git Bash / WSL (để chạy bash) | — | — |

Quyền Azure cần có: role `FSO-SandboxOps` trên subscription `FSO-SB-GHCHCS-OJT-DEV`
(`c4a86d00-6328-4d7b-8c75-6293553cd19c`). Role này **không** cho tạo role assignment,
không tạo service principal, không đụng `Microsoft.Authorization/*/Write`. Toàn bộ
hướng dẫn được thiết kế để không cần các quyền đó.

Dữ liệu đầu vào cần có trên máy:

```
D:\Learn-guard\Data-ML-MLOPS\data\archive.zip     (dataset OULAD, ~44 MB)
D:\Learn-guard\BE-MLOPS\db_schema_seed.sql        (schema 7 bảng)
D:\Learn-guard\FE-MLOPS\                          (mã nguồn frontend)
```

Ba repo ứng dụng là **read-only** — chỉ build, không sửa.

---

## 3. Khởi tạo phiên làm việc

Mở PowerShell mới, chạy khối này một lần. Các lệnh sau dùng lại biến.

```powershell
# Đường dẫn terraform (bản portable, không cài vào PATH)
$T = "C:\Users\vieth\Downloads\terraform_1.15.8_windows_amd64\terraform.exe"

# Terraform cần file CLI config trỏ tới provider mirror/cài đặt cục bộ
$env:TF_CLI_CONFIG_FILE = "C:\Users\vieth\AppData\Local\Temp\lg-terraformrc"

$RG        = "learn-guard-dev"
$SUB       = "c4a86d00-6328-4d7b-8c75-6293553cd19c"
$PLATFORM  = "D:\Learn-guard\learnguard-platform"
$ENVDIR    = "$PLATFORM\infra\env\dev"
$SEEDDIR   = "C:\Users\vieth\.lg-seed"       # nơi giữ khóa SSH + script seed (không commit)

# Đăng nhập
az login
az account set --subscription $SUB
az account show --query "{name:name, id:id, user:user.name}" -o table
```

Kết quả mong đợi: bảng có `FSO-SB-GHCHCS-OJT-DEV` và email của bạn.

> `.lg-seed` không nằm trong repo. Nếu chưa có, tạo: `New-Item -ItemType Directory $SEEDDIR -Force`

---

## 4. Giai đoạn 1 — Dựng hạ tầng (chưa có ứng dụng)

### 4.1 Chuẩn bị biến

`infra/env/dev/terraform.tfvars` — lần đầu để `deploy_apps = false`:

```hcl
location         = "eastasia"
environment      = "dev"
operator_ip_cidr = "113.185.0.0/16"   # xem giải thích bên dưới
deploy_apps      = false
api_image        = ""
job_image        = ""
```

**Vì sao `/16` mà không phải `/32`:** ISP dùng CGNAT, IP ra Internet của bạn đổi liên tục
trong dải `113.185.x.x`. Nếu khai `/32` (IP hiện tại), lần sau IP đổi là mất SSH vào jump VM
và mất quyền vào Key Vault. Kiểm tra dải của bạn bằng `curl https://api.ipify.org` vài lần
trong ngày; nếu IP nhảy sang dải khác thì mở rộng CIDR tương ứng.

> Nhược điểm của `/16`: dải IP rộng được phép SSH. Chấp nhận cho dev; khi lên production
> phải dùng IP tĩnh hoặc VPN point-to-site.

### 4.2 Init

```powershell
cd $ENVDIR
& $T init
```

Kết quả mong đợi: `Terraform has been successfully initialized!` và tải `azurerm` 4.81.

> Nếu dùng remote state: `& $T init -backend-config=backend.hcl -migrate-state`.
> Hiện tại môi trường dev đang dùng **state local** (`terraform.tfstate` trong thư mục này).

### 4.3 Plan và apply

```powershell
& $T validate
& $T plan -out=tfplan
& $T apply tfplan
```

Thời gian: 8–15 phút (PostgreSQL và Container Apps Env chậm nhất).

Kết quả mong đợi: `Apply complete! Resources: N added, 0 changed, 0 destroyed.`

> **Nếu mạng công ty hay reset kết nối** (`HTTP response was nil; connection may have been
> reset`, `connection reset by peer`), xem mục 13.1 — chạy qua proxy SOCKS của jump VM.

### 4.4 Kiểm tra

```powershell
& $T output
```

Bảng output phải có: `resource_group_name`, `postgres_fqdn`, `key_vault_uri`,
`acr_login_server`, `storage_account_name`, `jump_public_ip`, `container_app_default_domain`,
`static_web_app_host`, `api_fqdn` (rỗng vì `deploy_apps=false`).

Ghi lại các giá trị sau để dùng về sau:

```powershell
& $T output -raw acr_login_server
& $T output -raw key_vault_name
& $T output -raw storage_account_name
& $T output -raw jump_public_ip
& $T output -raw container_app_default_domain
& $T output -raw static_web_app_host
```

> ⚠️ `terraform output pg_admin_password` và `jump_ssh_private_key` là **secret**:
> chỉ đọc bằng `-raw` và ghi thẳng vào file/biến, không in ra chat, không dán vào tài liệu.

---

## 5. Giai đoạn 2 — Build và push image

Container App lấy image từ ACR. Ta build hai image:

| Image | Nguồn | Dockerfile |
|---|---|---|
| `learnguard-api` | `D:\Learn-guard\BE-MLOPS` | `deploy/docker/Dockerfile.api` |
| `learnguard-ml` | `D:\Learn-guard\Data-ML-MLOPS` | `deploy/docker/Dockerfile.ml` |

```powershell
cd $PLATFORM
$ACR = (& $T output -raw acr_login_server).Split('.')[0]   # ví dụ acrdevcjalc

.\deploy\docker\build-push.ps1 -AcrName $ACR -Component api -Tag 0.1.0
.\deploy\docker\build-push.ps1 -AcrName $ACR -Component ml  -Tag 0.1.0
```

Kết quả mong đợi (mỗi lần chạy in ra dòng cuối):

```
OK. Dùng digest này cho deploy (deploy_apps=true):
  acrdevcjalc.azurecr.io/learnguard-api@sha256:<digest>
```

**Ghim theo digest, không theo tag.** Tag `0.1.0` có thể bị ghi đè; digest thì bất biến,
nhờ vậy redeploy luôn ra đúng phiên bản đã kiểm thử.

Cập nhật `terraform.tfvars` bằng hai digest vừa nhận:

```hcl
deploy_apps = true
api_image   = "acrdevcjalc.azurecr.io/learnguard-api@sha256:<digest-api>"
job_image   = "acrdevcjalc.azurecr.io/learnguard-ml@sha256:<digest-ml>"
```

---

## 6. Giai đoạn 3 — Vào trong VNet

PostgreSQL, Key Vault và Storage đều **tắt public access** (do policy tenant). Không có
đường nào từ máy bạn vào trực tiếp — phải qua jump VM.

### 6.1 Lấy khóa SSH

Khóa private sinh ra trong state, chưa từng nằm trên đĩa:

```powershell
cd $ENVDIR
& $T output -raw jump_ssh_private_key | Out-File -Encoding ascii -NoNewline "$SEEDDIR\jump_key"
icacls "$SEEDDIR\jump_key" /inheritance:r /grant:r "$env:USERNAME:(R)"
```

Kiểm tra quyền: `icacls "$SEEDDIR\jump_key"` phải chỉ có đúng user của bạn với `(R)`.

### 6.2 SSH

```powershell
$JUMP = & $T output -raw jump_public_ip
ssh -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new lgops@$JUMP
```

Kết quả mong đợi: prompt `lgops@vm-az-lg-jump:~$`.

Máy này đã được cài sẵn `psql`, `az`, `unzip`, `openssl`, `python3`.

> Không SSH được? Xem 13.2 (NSG/CGNAT) và 13.3 (key quyền sai).

---

## 7. Giai đoạn 4 — Database và Key Vault

### 7.1 Chuẩn bị file trên VM

Từ PowerShell (máy bạn):

```powershell
scp -i "$SEEDDIR\jump_key" D:\Learn-guard\BE-MLOPS\db_schema_seed.sql lgops@$JUMP:/tmp/
scp -i "$SEEDDIR\jump_key" "$PLATFORM\deploy\db\roles.sql"      lgops@$JUMP:/tmp/
scp -i "$SEEDDIR\jump_key" "$PLATFORM\deploy\db\seed.sh"        lgops@$JUMP:/tmp/
```

Trên VM, tạo file biến môi trường chứa thông tin nhạy cảm. Lấy giá trị bằng
`terraform output -raw` trên máy bạn rồi dán vào:

```bash
cat > /tmp/lg.env <<'EOF'
PG_FQDN=<postgres_fqdn>              # psql-lg-dev-<s>.postgres.database.azure.com
PG_DB=learnguard
PG_ADMIN_LOGIN=lgadmin
PG_ADMIN_PW=<pg_admin_password>
ACR_PW=<acr_admin_password>
KV_NAME=kv-lg-dev-<s>
EOF
chmod 600 /tmp/lg.env
```

Lấy ba giá trị `<...>`:

```powershell
# máy bạn — CHỈ hiển thị trên màn hình của bạn
& $T output -raw postgres_fqdn
& $T output -raw pg_admin_password
& $T output -raw acr_admin_password
& $T output -raw key_vault_name
```

> Không dán các giá trị này vào chat, email, hay commit. `seed.sh` tự xoá `/tmp/lg.env`
> sau khi chạy xong.

### 7.2 Chạy seed

Trên VM:

```bash
chmod +x /tmp/seed.sh
/tmp/seed.sh
```

Script làm 5 việc, theo đúng thứ tự:

1. Nạp `db_schema_seed.sql` → 7 bảng: `users`, `audit_logs`, `briefs`, `decisions`,
   `llm_calls`, `ml_predictions`, `alembic_version`.
2. Tạo (hoặc làm mới) hai role:
   - `lg_api` — backend: CRUD các bảng backend, chỉ `SELECT` trên `ml_predictions`.
   - `lg_ml_writer` — pipeline ML: sở hữu `ml_predictions`, không đọc được bảng backend.
3. Sinh DSN cho từng role.
4. `az login --identity --allow-no-subscriptions` — đăng nhập Key Vault bằng managed
   identity của jump VM (quyền đến từ access policy, không cần RBAC subscription).
5. Ghi 4 secret: `pg-admin-password`, `pg-dsn` (role `lg_api`), `pg-dsn-ml` (role
   `lg_ml_writer`), `acr-admin-password`.

Kết quả mong đợi (phần cuối):

```
[seed] api login: ok
[seed] ml  login: ok
[seed] Secrets:
acr-admin-password
pg-admin-password
pg-dsn
pg-dsn-ml
[seed] Tables:
alembic_version
audit_logs
briefs
decisions
llm_calls
ml_predictions
users
[seed] Roles:
lg_api
lg_ml_writer
[seed] DONE
```

> Seed này **idempotent**: chạy lại bao nhiêu lần cũng được. Mỗi lần chạy sinh mật khẩu
> mới và ghi đè vào Key Vault, nên không cần biết mật khẩu cũ. Container App đọc secret
> từ KV theo tên, nên chỉ cần restart revision là nhận mật khẩu mới.

### 7.3 Vì sao `roles.sql` có hai dòng "lạ"

```sql
GRANT CREATE ON SCHEMA public TO lg_ml_writer;
ALTER TABLE public.ml_predictions OWNER TO lg_ml_writer;
```

- Dòng 1: từ PostgreSQL 15, kể cả `CREATE TABLE IF NOT EXISTS` cũng phải có quyền `CREATE`
  trên schema **trước khi** server kiểm tra bảng đã tồn tại. Thiếu dòng này, job ML chết
  với `permission denied for schema public`.
- Dòng 2: `CREATE INDEX IF NOT EXISTS` yêu cầu quyền **chủ sở hữu bảng**, không phải chỉ
  quyền ghi. Thiếu dòng này, job ML chết với `must be owner of table ml_predictions`.

Hai lỗi này đã gặp thật trong lần đầu triển khai; đừng xoá hai dòng trên.

---

## 8. Giai đoạn 5 — Dữ liệu và script pipeline

### 8.1 Upload dataset OULAD

```powershell
scp -i "$SEEDDIR\jump_key" D:\Learn-guard\Data-ML-MLOPS\data\archive.zip lgops@$JUMP:/tmp/
```

Trên VM, giải nén:

```bash
cd /tmp && rm -rf oulad && mkdir oulad && unzip -q -o archive.zip -d oulad && ls oulad
```

Kết quả mong đợi: 7 file CSV:

```
assessments.csv  courses.csv  studentAssessment.csv  studentInfo.csv
studentRegistration.csv  studentVle.csv  vle.csv
```

Upload lên Azure Files. Storage không cho dùng public access, nên lấy key và **đẩy thẳng
qua pipe** (không ghi key ra đĩa, không in ra màn hình):

```powershell
# máy bạn
$STG = & $T output -raw storage_account_name
$K   = az storage account keys list --account-name $STG --resource-group $RG --query "[0].value" -o tsv

$K | ssh -i "$SEEDDIR\jump_key" lgops@$JUMP `
  "read -r KEY; export AZURE_STORAGE_ACCOUNT=$STG AZURE_STORAGE_KEY=`$KEY AZURE_STORAGE_AUTH_MODE=key; unset KEY;
   az storage file upload-batch --destination lgdata --source /tmp/oulad --destination-path oulad --only-show-errors --output none"

Remove-Variable K
```

Kiểm tra (dùng lại cùng cách — key đi qua pipe, không lưu đĩa):

```powershell
$K = az storage account keys list --account-name $STG --resource-group $RG --query "[0].value" -o tsv
$K | ssh -i "$SEEDDIR\jump_key" lgops@$JUMP `
  "read -r KEY; AZURE_STORAGE_ACCOUNT=$STG AZURE_STORAGE_KEY=`$KEY AZURE_STORAGE_AUTH_MODE=key az storage file list --share-name lgdata --path oulad --output table"
Remove-Variable K
```

Kết quả mong đợi: 7 dòng file tương ứng 7 CSV.

### 8.2 Upload script điều phối pipeline

File gốc: `$PLATFORM\deploy\ml\ml_pipeline.py` — chạy lần lượt M1 → M5 trong một tiến trình.

```powershell
scp -i "$SEEDDIR\jump_key" "$PLATFORM\deploy\ml\ml_pipeline.py" lgops@$JUMP:/tmp/
```

Trên máy bạn, tạo thư mục và upload (key đi qua pipe như mục 8.1):

```powershell
$K = az storage account keys list --account-name $STG --resource-group $RG --query "[0].value" -o tsv
$K | ssh -i "$SEEDDIR\jump_key" lgops@$JUMP `
  "read -r KEY; export AZURE_STORAGE_ACCOUNT=$STG AZURE_STORAGE_KEY=`$KEY AZURE_STORAGE_AUTH_MODE=key; unset KEY;
   az storage directory create --share-name lgdata --name scripts --only-show-errors &&
   az storage file upload --share-name lgdata --source /tmp/ml_pipeline.py --path scripts/ml_pipeline.py --only-show-errors --output none"
Remove-Variable K
```

> `az storage file upload --path scripts/...` báo `ParentNotFound` nếu thư mục `scripts`
> chưa tồn tại — luôn tạo thư mục trước.

### 8.3 Script này làm gì

| Bước | Việc | Kết quả |
|---|---|---|
| M1 | Nạp 7 CSV, chuẩn hoá | ~10,1 triệu dòng |
| M2 | Chốt ảnh chụp đặc trưng tại ngày 27 | `snapshot-v1:cutoff27:...` |
| M3 | Kiểm tra rò rỉ dữ liệu + cổng chất lượng | audit ok / gate ok |
| M4 | Tiền xử lý + huấn luyện logistic | `logreg-v1:...` |
| M5 | Chấm điểm toàn bộ sinh viên + ghi DB | ghi/upsert `ml_predictions` |

Biến môi trường (khai trong `apps.tf`, không cần sửa script):

```
LEARNGUARD_DATA_DIR=/mnt/data/oulad
LEARNGUARD_ARTIFACTS_DIR=/mnt/data/artifacts
LEARNGUARD_PG_DSN=<secret pg-dsn-ml>
LEARNGUARD_CUTOFF_DAY=27
LEARNGUARD_THRESHOLD=0.5
```

---

## 9. Giai đoạn 6 — Bật ứng dụng

Quay lại máy bạn. Biến `terraform.tfvars` đã có digest ở mục 5.

```powershell
cd $ENVDIR
& $T plan -out=tfplan-apps
& $T apply tfplan-apps
```

Terraform tạo thêm:

- `azurerm_container_app_environment_storage` — gắn share `lgdata` vào môi trường với tên
  volume `lgfiles` (job sẽ mount thành `/mnt/data`).
- `ca-lg-dev-api` — Container App, ingress công khai cổng 8000, `min_replicas=0`,
  `max_replicas=2`, revision mode Multiple.
- `caj-lg-dev-ml` — Container App Job, trigger thủ công, timeout 3600 giây, 2 vCPU / 4 GiB.

Hai điểm cấu hình quan trọng:

1. **Secret tham chiếu bằng ID dựng sẵn**, không phải resource Terraform:

   ```hcl
   key_vault_secret_id = "${module.security.key_vault_uri}secrets/pg-dsn"
   ```

   Vì secret được seed thủ công từ trong VNet, nếu khai `azurerm_key_vault_secret` thì
   Terraform sẽ cố ghi qua data-plane từ máy ngoài VNet và thất bại.

2. **Job ghi đè ENTRYPOINT của image**:

   ```hcl
   command = ["python"]
   args    = ["/mnt/data/scripts/ml_pipeline.py"]
   ```

   Image ML có `ENTRYPOINT ["learnguard"]` (CLI cần subcommand). Không ghi đè sẽ lỗi
   `the following arguments are required: area`.

### 9.1 Kiểm tra

```powershell
& $T output -raw api_fqdn
```

Kết quả: `ca-lg-dev-api.<domain-của-env>` — **đây là URL ổn định**, không đổi giữa các
revision. Không dùng `latest_revision_fqdn`: URL đó gắn chết vào một revision và sẽ trả
404/không nhận cấu hình mới sau khi deploy revision khác.

```powershell
$API = "https://" + (& $T output -raw api_fqdn)
curl "$API/health"
```

Kết quả mong đợi:

```json
{"status":"ok","app":"LearnGuard Backend","version":"0.1.0",
 "dependencies":{"database":"reachable","llm":"not_configured"}}
```

`database: reachable` nghĩa là Container App đã đọc được secret `pg-dsn` và nối được
PostgreSQL. Nếu là `unreachable` hoặc `not_configured`, xem 13.4.

---

## 10. Giai đoạn 7 — Chạy pipeline ML

```powershell
az containerapp job start -n caj-lg-dev-ml -g $RG
az containerapp job execution list -n caj-lg-dev-ml -g $RG -o table
```

Thời gian: ~90 giây (M1 đọc file `studentVle.csv` ~450 MB là bước chậm nhất).

Kết quả mong đợi:

```
Name                     Status     StartTime
-----------------------  ---------  -------------------------
caj-lg-dev-ml-<id>       Succeeded  2026-11-05T07:35:23+00:00
```

Khi cần xem log (extension `containerapp` không phải lúc nào cũng ổn định), dùng Log
Analytics:

```powershell
$WS = az monitor log-analytics workspace show --ids (& $T output -raw log_analytics_workspace_id) --query customerId -o tsv
az monitor log-analytics query -w $WS --analytics-query `
  "ContainerAppConsoleLogs_CL | where ContainerJobName_s == 'caj-lg-dev-ml' | order by TimeGenerated desc | take 50 | project TimeGenerated, Log_s" `
  -o table
```

### 10.1 Kiểm tra dữ liệu đã ghi

Trên jump VM:

```bash
source /tmp/lg.env   # nếu file đã bị xoá, tạo lại từ terraform output
PGPASSWORD="$PG_ADMIN_PW" psql -h "$PG_FQDN" -U lgadmin -d learnguard \
  -c "select run_id, count(*), round(min(risk_score)::numeric,3), round(max(risk_score)::numeric,3)
      from ml_predictions group by run_id order by run_id desc limit 5;"
```

Kết quả lần chạy thật:

```
        run_id         | count |  round |  round
-----------------------+-------+--------+--------
 batch-20261105T073523Z| 27535 |  0.014 |  0.997
```

Job ghi theo kiểu **upsert** khoá `(code_module, code_presentation, student_key)`, nên chạy
lại nhiều lần không sinh bản ghi trùng; mỗi lần có `run_id` mới để truy vết.

### 10.2 Kiểm tra API trả dữ liệu

```powershell
curl "$API/predictions?limit=2"
```

Mong đợi: `{"items":[{...}],"total":...,"limit":2,"offset":0}` với các trường
`risk_score`, `predicted_label`, `top_signals`, `model_version`, `run_id`.

---

## 11. Giai đoạn 8 — Frontend

### 11.1 Build với URL API thật

```powershell
cd D:\Learn-guard\FE-MLOPS
npm ci

$env:VITE_BACKEND_API_URL = "https://ca-lg-dev-api.<domain-của-env>"
$env:VITE_USE_MOCK         = "false"
npm run build
```

`VITE_USE_MOCK=false` bật chế độ lai: dữ liệu dự đoán gọi API thật; đăng nhập / thống kê /
briefs vẫn chạy mock vì backend chưa có M6/M8.

Kiểm tra nhanh bundle có đúng URL không:

```powershell
Select-String -Path .\dist\assets\*.js -Pattern "ca-lg-dev-api" -SimpleMatch | Select-Object -First 1
```

### 11.2 Thêm cấu hình SPA

```powershell
Copy-Item "$PLATFORM\deploy\frontend\staticwebapp.config.json" .\dist\
```

File này khiến mọi đường dẫn sâu (`/review`, `/predictions/...`) trả về `index.html` thay
vì 404 — React Router xử lý phần còn lại.

### 11.3 Deploy

```powershell
$TOKEN = az staticwebapp secrets list -n swa-lg-dev -g $RG --query properties.apiKey -o tsv
npx -y "@azure/static-web-apps-cli@2.0.6" deploy .\dist --deployment-token $TOKEN --env production
Remove-Variable TOKEN
```

Kết quả mong đợi: dòng cuối in ra URL, ví dụ
`https://red-rock-0a95dbc00.3.azurestaticapps.net`.

### 11.4 CORS

API chỉ chấp nhận origin của Static Web App. Giá trị này được Terraform tính sẵn:

```hcl
env {
  name  = "CORS_ORIGINS"
  value = "https://${module.frontend.default_host_name}"
}
```

Nếu đổi tên SWA hoặc dùng domain riêng, phải sửa `apps.tf` rồi apply lại. Triệu chứng khi
sai: trình duyệt báo `blocked by CORS policy`, preflight trả 400.

---

## 12. Giai đoạn 9 — Kiểm thử đầu-cuối

| # | Việc | Lệnh / thao tác | Kết quả đạt |
|---|---|---|---|
| 1 | API sống | `curl $API/health` | 200, `database: reachable` |
| 2 | API có dữ liệu | `curl "$API/predictions?limit=2"` | 200, có `items` |
| 3 | Tra một sinh viên | `curl "$API/predictions/DDD/2013B/<student_key>"` | 200 hoặc 404 `prediction_not_found` |
| 4 | Tra theo sinh viên | `curl "$API/predictions/by-student/<student_key>"` | 200 |
| 5 | Trang chủ FE | mở `https://<swa>.azurestaticapps.net` | 200 |
| 6 | Đường dẫn sâu | mở `.../review` | 200 (không 404) |
| 7 | Đăng nhập | `advisor@learnguard.vn` / `advisor123` | vào được danh sách sinh viên |
| 8 | Dữ liệu thật | danh sách hiển thị điểm rủi ro | khớp với API |
| 9 | Log | `ContainerAppConsoleLogs_CL` | không có lỗi 500 |

> Lần gọi đầu tiên sau khi để lâu có thể chậm ~20 giây: `min_replicas = 0` nên Container
> App ngủ khi không có request. Đây là thiết kế tiết kiệm chi phí, không phải lỗi.
> Muốn tránh: đặt `min_replicas = 1` trong `apps.tf` (tốn thêm chi phí).

---

## 13. Xử lý sự cố

### 13.1 Terraform lỗi kết nối (`HTTP response was nil`, `connection reset`)

Nguyên nhân: mạng văn phòng chặn/reset TLS tới `management.azure.com`, thường gặp với
`Microsoft.App` (Container App/Job). Giảm `-parallelism` không giải quyết.

Cách xử lý đã dùng: đi qua proxy SOCKS của jump VM (egress của Azure ổn định).

```bash
# trên máy bạn (Git Bash) — mở tunnel ở nền
ssh -i C:/Users/vieth/.lg-seed/jump_key -o ExitOnForwardFailure=yes -D 1080 -N -f lgops@<jump_ip>
```

```powershell
$env:HTTPS_PROXY = "socks5h://127.0.0.1:1080"
$env:HTTP_PROXY  = "socks5h://127.0.0.1:1080"
$env:NO_PROXY    = "127.0.0.1,localhost,api.ipify.org"
& $T apply -refresh=false -input=false -auto-approve -parallelism=1
```

Ba chi tiết bắt buộc:

- `socks5h://` (có `h`) để DNS resolve phía proxy. `az` (PySocks) và `curl` đều cần.
- `api.ipify.org` phải nằm trong `NO_PROXY` — data source `my_ip` của Terraform không đi
  qua proxy được.
- Tunnel phải còn sống: kiểm tra `netstat -ano | findstr 1080`.

Dừng tunnel khi xong: `taskkill /F /IM ssh.exe` (hoặc PID trong netstat).

### 13.2 Không SSH được vào jump VM

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| `Connection timed out` | IP hiện tại ngoài `operator_ip_cidr` (CGNAT đổi) | `curl https://api.ipify.org`, rồi đổi CIDR trong `terraform.tfvars` và apply |
| `Permission denied (publickey)` | Sai khóa hoặc khóa bị đổi quyền | Xuất lại khóa từ state (6.1) |
| `Bad permissions` trên Linux/WSL | File key cho phép group/other đọc | `chmod 600` |
| `Host key verification failed` | IP bị cấp lại cho VM khác | `ssh-keygen -R <ip>` |

NSG của subnet jump chỉ mở cổng 22 từ `operator_ip_cidr`, cộng với luật
`allow-vnet-inbound`; mọi luồng từ Internet khác bị `deny-internet-inbound`.

### 13.3 Lỗi khi seed

| Lỗi | Nguyên nhân | Xử lý |
|---|---|---|
| `No access was configured for the managed identity` | `az login --identity` không có `--allow-no-subscriptions` | Thêm cờ đó (đã có trong `seed.sh`) |
| `permission denied for schema public` khi job chạy | Thiếu `GRANT CREATE` | Chạy lại `seed.sh` |
| `must be owner of table ml_predictions` | Chưa `ALTER TABLE ... OWNER` | Chạy lại `seed.sh` |
| `role "lg_api" already exists` | Dùng `roles.sql` trực tiếp thay vì `seed.sh` | Dùng `seed.sh` (đã xử lý idempotent) |
| `psql: connection refused/timeout` | Chạy từ máy ngoài VNet | Chạy trên jump VM |

### 13.4 API trả `database: unreachable`

Thứ tự kiểm tra:

1. Secret tồn tại: trên VM `az keyvault secret list --vault-name <kv> --query "[].name" -o tsv`.
2. Container App đọc được secret: revision mới nhất có lỗi `secret not found` không.
3. DSN đúng role và đúng mật khẩu: chạy lại `seed.sh` (sinh mật khẩu mới + ghi KV).
4. Khởi động lại revision: `az containerapp revision restart -n ca-lg-dev-api -g $RG --revision <name>`.
5. DNS nội bộ: từ một máy trong VNet, `nslookup psql-lg-dev-<s>.postgres.database.azure.com`.

### 13.5 Job ML thất bại

| Thông báo trong log | Nguyên nhân | Xử lý |
|---|---|---|
| `the following arguments are required: area` | Job không ghi đè ENTRYPOINT | Kiểm tra `command`/`args` trong `apps.tf` |
| `permission denied for schema public` | Thiếu `GRANT CREATE` | `seed.sh` |
| `must be owner of table ml_predictions` | Thiếu `ALTER TABLE OWNER` | `seed.sh` |
| `No such file or directory: /mnt/data/oulad` | Chưa upload dataset hoặc mount sai | Mục 8.1 |
| `No such file or directory: /mnt/data/scripts/ml_pipeline.py` | Chưa upload script | Mục 8.2 |
| Bị kill, exit 137 | Hết RAM | Tăng `memory` trong `apps.tf` (hiện 4 GiB) |
| `could not connect to server` | Secret `pg-dsn-ml` sai hoặc thiếu | `seed.sh` rồi restart job |

Xem log chi tiết:

```powershell
az monitor log-analytics query -w $WS --analytics-query `
  "ContainerAppConsoleLogs_CL | where ContainerJobName_s == 'caj-lg-dev-ml'
   | where Log_s has_any ('Error','Traceback','FAILED','denied','owner')
   | order by TimeGenerated desc | take 30 | project TimeGenerated, Log_s" -o table
```

### 13.6 Frontend

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| `/review` trả 404 | Thiếu `staticwebapp.config.json` | Mục 11.2 rồi deploy lại |
| Trang trắng, console báo 404 file JS | Deploy sai thư mục | Deploy `.\dist`, không phải `.\` |
| `blocked by CORS policy` | `CORS_ORIGINS` thiếu domain SWA | Sửa `apps.tf`, apply lại |
| Dữ liệu là số giả | Bundle build với mock | Build lại với `VITE_USE_MOCK=false` |
| Gọi nhầm revision cũ | Dùng `latest_revision_fqdn` | Dùng `api_fqdn` ổn định |
| Đăng nhập báo sai mật khẩu | Dùng tài khoản khác | `advisor@learnguard.vn` / `advisor123` |

---

## 14. Destroy

### 14.1 Trước khi destroy — bắt buộc

- [ ] Sao lưu `terraform.tfstate` và `terraform.tfvars` ra nơi an toàn (chứa secret).
- [ ] Ghi lại danh sách tên tài nguyên đang có (mục 14.2) — cần khi mất state.
- [ ] Nếu cần giữ dữ liệu: dump `ml_predictions` và tải artifacts trên share về.
- [ ] Xác nhận không còn ai dùng môi trường.
- [ ] Ghi lại hai digest image (vẫn còn trong ACR cho tới khi xoá).

Ghi lại tên tài nguyên:

```powershell
az resource list -g learn-guard-dev --query "sort_by([].{name:name,type:type}, &type)" -o table
```

### 14.2 Lệnh destroy

```powershell
cd $ENVDIR

# nếu mạng chập chờn, bật proxy trước (13.1)
& $T destroy -refresh=false -input=false -parallelism=1
```

Terraform sẽ hỏi xác nhận; gõ `yes`. Thời gian: 10–20 phút.

`-refresh=false` tránh phải đọc lại toàn bộ tài nguyên (và tránh lỗi mạng khi đọc).
`-parallelism=1` giảm khả năng bị reset kết nối.

### 14.3 Những gì còn lại sau destroy

| Thứ còn lại | Vì sao | Cần làm gì |
|---|---|---|
| Key Vault ở trạng thái soft-deleted | Azure giữ 90 ngày | Purge hoặc recover trước khi tạo lại cùng tên |
| State backend (nếu dùng remote) | Nằm ngoài Terraform | Giữ nguyên |
| `terraform.tfstate` trên máy | Không bị xoá | Giữ để redeploy đúng tên, hoặc xoá nếu muốn tên mới |
| Log Analytics (nếu chọn giữ) | Tuỳ cấu hình | Kiểm tra `az monitor log-analytics workspace list -g $RG` |
| Static Web App | Do Terraform quản lý → bị xoá | Deploy lại ở mục 11 |
| Image trong ACR | ACR bị xoá → image mất | Build lại ở mục 5 |

Xử lý Key Vault:

```powershell
az keyvault list-deleted --query "[?name=='kv-lg-dev-<s>'].{name:name,deletionDate:properties.deletionDate}" -o table
```

- **Triển khai lại ngay** → `az keyvault recover --name kv-lg-dev-<s>` (giữ nguyên tên,
  nhưng phải đối chiếu tên trong state).
- **Muốn tên sạch** → `az keyvault purge --name kv-lg-dev-<s> --location eastasia`.

> Không purge nếu còn nghi ngờ cần khôi phục secret cũ.

### 14.4 Kiểm tra đã xoá sạch

```powershell
az resource list -g learn-guard-dev -o table
# mong đợi: danh sách rỗng
az group show -n learn-guard-dev --query properties.provisioningState -o tsv
# nếu resource group vẫn còn (Terraform quản lý RG) -> "Succeeded" là bình thường khi chưa destroy xong
az keyvault list-deleted --query "[?properties.vaultUri!=null].name" -o tsv
```

---

## 15. Triển khai lại

Có ba tình huống. Chọn đúng tình huống trước khi làm.

### 15.1 Kịch bản A — Còn state (khuyến nghị, nhanh nhất)

Điều kiện: `infra/env/dev/terraform.tfstate` vẫn còn, hoặc state remote vẫn còn.

```powershell
cd $ENVDIR

# 1) Nếu vừa destroy và Key Vault còn soft-deleted cùng tên:
az keyvault recover --name kv-lg-dev-<s> --resource-group learn-guard-dev
#    (hoặc purge nếu chắc chắn không cần dữ liệu cũ)

# 2) TẮT app trước: ACR đã bị xoá nên image cũ không còn.
#    (Bỏ bước này, apply sẽ tạo Container App trỏ tới image không tồn tại.)
$tfvars = @"
location         = "eastasia"
environment      = "dev"
operator_ip_cidr = "<operator_ip_cidr>"
deploy_apps      = false
api_image        = ""
job_image        = ""
"@
[IO.File]::WriteAllText("$ENVDIR\terraform.tfvars", $tfvars)

# 3) Dựng lại hạ tầng
& $T apply -refresh=false -input=false -parallelism=1
```

Terraform tạo lại **đúng tên cũ** vì hậu tố nằm trong state. Nhưng:

- Image trong ACR mất → phải build/push lại (mục 5).
- PostgreSQL mới → dữ liệu trống → phải seed lại (mục 7).
- Key Vault mới/recover → secret có thể còn (nếu recover) hoặc trống (nếu purge):
  chạy `seed.sh` để chắc chắn đúng.
- Share Azure Files mới → phải upload lại dataset + script (mục 8).

Thứ tự bắt buộc sau khi apply:

```
4 (hạ tầng) → 5 (image) → 6 (vào VNet) → 7 (DB/KV) → 8 (dữ liệu)
→ 9 (apply apps) → 10 (job ML) → 11 (frontend) → 12 (kiểm thử)
```

Lưu ý: nếu apply một lần với `deploy_apps = true` khi chưa có image, Container App vẫn
được tạo nhưng revision ở trạng thái lỗi. Cách sạch là để `false` cho lần đầu, build image,
rồi apply lần hai.

### 15.2 Kịch bản B — Mất state, muốn tên mới

Điều kiện: không còn `terraform.tfstate` (đổi máy, xoá nhầm, hoặc cố ý).

```powershell
cd $ENVDIR
Move-Item terraform.tfstate terraform.tfstate.old -ErrorAction SilentlyContinue
Move-Item terraform.tfstate.backup terraform.tfstate.old.backup -ErrorAction SilentlyContinue

# tfvars cũ trỏ tới ACR cũ → phải tắt app trước
$tfvars = @"
location         = "eastasia"
environment      = "dev"
operator_ip_cidr = "<operator_ip_cidr>"
deploy_apps      = false
api_image        = ""
job_image        = ""
"@
[IO.File]::WriteAllText("$ENVDIR\terraform.tfvars", $tfvars)

& $T init
& $T plan -out=tfplan
& $T apply tfplan
```

Terraform sinh **hậu tố mới** → mọi tên tài nguyên đổi (ví dụ `acrdevq7xkz`). Hệ quả:

- Phải cập nhật `terraform.tfvars` với ACR mới, build/push image mới.
- Phải build lại frontend với FQDN API mới.
- Không cần purge Key Vault (tên khác).
- Tài nguyên cũ (nếu còn) phải xoá tay: `az group delete -n <rg-cũ> --yes`.

Cách tìm tên cũ nếu lỡ mất state mà tài nguyên vẫn còn:

```powershell
az resource list --query "[?contains(name,'lg-dev')].{name:name,type:type,rg:resourceGroup}" -o table
```

Từ tên cũ có thể dựng lại state bằng `terraform import` cho từng resource — làm được nhưng
tốn công; thực tế nhanh hơn là xoá resource group và làm lại từ đầu.

### 15.3 Kịch bản C — Chỉ deploy lại ứng dụng, giữ hạ tầng

Dùng khi hạ tầng còn nguyên, chỉ muốn cập nhật code.

```powershell
# 1) Build image phiên bản mới
cd $PLATFORM
.\deploy\docker\build-push.ps1 -AcrName $ACR -Component api -Tag 0.1.1
.\deploy\docker\build-push.ps1 -AcrName $ACR -Component ml  -Tag 0.1.1

# 2) Cập nhật digest trong terraform.tfvars rồi apply
cd $ENVDIR
& $T apply -var="api_image=<digest-api>" -var="job_image=<digest-ml>" -auto-approve

# 3) Nếu chỉ đổi frontend: build + deploy lại (mục 11), không cần terraform
```

Nếu chỉ muốn chạy lại pipeline với dữ liệu mới:

```powershell
az containerapp job start -n caj-lg-dev-ml -g $RG
```

### 15.4 Bảng so sánh ba kịch bản

| | A — còn state | B — mất state | C — chỉ app |
|---|---|---|---|
| Tên tài nguyên | giữ nguyên | mới | giữ nguyên |
| Terraform apply | toàn bộ | toàn bộ | chỉ app |
| Build image | có | có | có |
| Seed DB + KV | có | có | không |
| Upload dataset | có | có | không |
| Build FE | có (URL đổi nếu tên đổi) | có | chỉ khi đổi FE |
| Thời gian | ~40 phút | ~50 phút | 5–10 phút |

---

## 16. Danh sách kiểm tra sau mỗi lần redeploy

Sao chép và tick dần:

```
[ ] terraform output đủ giá trị, không rỗng
[ ] az acr repository show-tags -n <acr> --repository learnguard-api   -> có tag mới
[ ] DB: 7 bảng
[ ] DB: role lg_api và lg_ml_writer tồn tại
[ ] DB: ml_predictions owner = lg_ml_writer
[ ] KV: đủ 4 secret (pg-admin-password, pg-dsn, pg-dsn-ml, acr-admin-password)
[ ] Share lgdata/oulad: 7 file CSV
[ ] Share lgdata/scripts/ml_pipeline.py tồn tại
[ ] API /health -> 200, database: reachable
[ ] Job ML -> Succeeded
[ ] ml_predictions có bản ghi với run_id mới
[ ] API /predictions -> 200 có items
[ ] FE trang chủ -> 200
[ ] FE deep link /review -> 200
[ ] Đăng nhập advisor@learnguard.vn / advisor123 thành công
[ ] Danh sách sinh viên hiển thị điểm rủi ro thật
[ ] Không có lỗi 5xx trong log Container App
```

Lệnh kiểm tra nhanh (PowerShell):

```powershell
$API = "https://" + (& $T output -raw api_fqdn)
curl "$API/health"
curl "$API/predictions?limit=1"
curl -o NUL -w "%{http_code}`n" https://<swa-host>/
curl -o NUL -w "%{http_code}`n" https://<swa-host>/review
```

---

## 17. Bảo mật, chi phí và giới hạn

### 17.1 Nguyên tắc đã áp dụng

- **Không secret trong repo/state công khai**: mật khẩu sinh bằng `random_password`, DSN
  ghi vào Key Vault, Container App đọc qua managed identity.
- **Least privilege DB**: `lg_api` không ghi được `ml_predictions`; `lg_ml_writer` không
  đọc được bảng người dùng.
- **Least privilege Azure**: managed identity của app/job không có role assignment nào;
  quyền Key Vault đến từ access policy riêng.
- **Không public**: PostgreSQL, Storage, Key Vault đều private; chỉ API và Static Web App
  công khai.
- **Không dùng quyền admin**: không tạo role assignment, không tạo service principal.

### 17.2 Việc còn hở (chấp nhận cho dev)

| Điểm | Rủi ro | Cách xử lý khi lên production |
|---|---|---|
| Đăng nhập là mock | Không có xác thực thật | Triển khai M6 (OIDC/Entra ID) |
| NSG mở SSH từ /16 | Dải IP rộng | IP tĩnh hoặc VPN point-to-site |
| ACR dùng admin account | Không dùng RBAC | Chuyển sang managed identity + AcrPull |
| State local chứa secret | Mất máy là mất state | Bật remote backend (bootstrap đã có sẵn) |
| `min_replicas = 0` | Khởi động nguội | Đặt 1 khi cần SLA |

### 17.3 Chi phí

Các thành phần tốn tiền liên tục:

- PostgreSQL Flexible (B-series) — khoản lớn nhất.
- Container Apps Environment — phí nền theo môi trường.
- Jump VM `Standard_D2as_v5` — chạy 24/7 nếu không tắt.
- Log Analytics + App Insights — theo dung lượng, đã đặt quota 0,5 GB/ngày.

Tiết kiệm khi không dùng:

```powershell
az vm deallocate -g $RG -n vm-az-lg-jump     # tắt jump VM, giữ nguyên cấu hình
az vm start      -g $RG -n vm-az-lg-jump     # bật lại khi cần seed
```

Container App tự về 0 replica khi không có request. Static Web App gói Free không tốn phí.

### 17.4 Giới hạn của tenant

- VM: chỉ B/D series ≤ 8 vCPU; tên phải `vm-az-` ≤ 15 ký tự.
- Mọi resource phải có tag bắt buộc (policy `tag_governance` tự thêm tag → Terraform dùng
  `ignore_changes = [tags]`).
- Storage và Key Vault bắt buộc tắt public network access.
- Subnet bắt buộc có NSG.
- Không được tạo role assignment / policy / management lock.

---

## 18. Phụ lục — lệnh tra cứu nhanh

```powershell
# --- thông tin môi trường ---
& $T output
& $T output -raw api_fqdn
& $T output -raw static_web_app_host

# --- tài nguyên ---
az resource list -g learn-guard-dev --query "sort_by([].{name:name,type:type}, &type)" -o table
az containerapp list -g learn-guard-dev -o table
az containerapp job list -g learn-guard-dev -o table
az postgres flexible-server list -g learn-guard-dev -o table
az staticwebapp list -g learn-guard-dev -o table

# --- trạng thái job ML ---
az containerapp job execution list -n caj-lg-dev-ml -g learn-guard-dev -o table

# --- log API ---
$WS = az monitor log-analytics workspace show --ids (& $T output -raw log_analytics_workspace_id) --query customerId -o tsv
az monitor log-analytics query -w $WS --analytics-query `
  "ContainerAppConsoleLogs_CL | where ContainerAppName_s == 'ca-lg-dev-api' | order by TimeGenerated desc | take 50 | project TimeGenerated, Log_s" -o table

# --- revision đang phục vụ ---
az containerapp revision list -n ca-lg-dev-api -g learn-guard-dev --query "[?properties.active].{name:name,traffic:properties.trafficWeight,created:properties.createdTime}" -o table

# --- secret trong Key Vault (chỉ tên, không giá trị) ---
az keyvault secret list --vault-name <kv-name> --query "[].name" -o tsv

# --- image trong ACR ---
az acr repository list -n <acr> -o table
az acr repository show-tags -n <acr> --repository learnguard-api -o table
```

Trên jump VM:

```bash
# DB
PGPASSWORD="$PG_ADMIN_PW" psql -h "$PG_FQDN" -U lgadmin -d learnguard -c "\dt"
PGPASSWORD="$PG_ADMIN_PW" psql -h "$PG_FQDN" -U lgadmin -d learnguard \
  -c "select run_id, count(*) from ml_predictions group by run_id order by run_id desc limit 5;"

# share (cần key — dùng lệnh PowerShell ở mục 8.1, không chạy az storage trực tiếp trên VM
#         nếu chưa có AZURE_STORAGE_KEY trong phiên)
# az storage file list --share-name lgdata --path oulad --output table
# az storage file list --share-name lgdata --path scripts --output table

# DNS nội bộ
nslookup "$PG_FQDN"
```

---

## 19. Những lỗi đã gặp thật trong lần triển khai đầu tiên

Bảng này để tra nhanh khi gặp thông báo lạ — tất cả đã được xử lý và ghi vào code/script.

| # | Thông báo | Nguyên nhân thật | Đã sửa ở đâu |
|---|---|---|---|
| 1 | `RequestDisallowedByPolicy` khi tạo VM | Tên VM không đúng quy ước | `main.tf`: `vm-az-lg-jump` |
| 2 | `SkuNotAvailable Standard_B2s` | Capacity/allowlist | `Standard_D2as_v5` |
| 3 | `AmbiguousPolicyEvaluationPaths` | Tag `environment` và `Environment` cùng tồn tại | `variables.tf`: chỉ dùng `Environment` |
| 4 | `populating Resource Provider cache` | `skip_provider_registration` deprecated ở azurerm 4.x | `resource_provider_registrations = "none"` |
| 5 | `HTTP response was nil` khi apply Microsoft.App | Mạng reset TLS | Proxy SOCKS (13.1) |
| 6 | `az login --identity` → `No access was configured...` | Identity không có RBAC subscription | `--allow-no-subscriptions` |
| 7 | `az storage file upload` → `ParentNotFound` | Chưa tạo thư mục | `az storage directory create` trước |
| 8 | JOB: `required: area` | Không ghi đè ENTRYPOINT | `command`/`args` trong `apps.tf` |
| 9 | JOB: `permission denied for schema public` | Thiếu `GRANT CREATE` | `roles.sql` + `seed.sh` |
| 10 | JOB: `must be owner of table ml_predictions` | Thiếu `ALTER TABLE OWNER` | `roles.sql` + `seed.sh` |
| 11 | FE `/review` 404 | Thiếu SPA fallback | `staticwebapp.config.json` |
| 12 | CORS 400 | Thiếu `CORS_ORIGINS` | `apps.tf` |
| 13 | FE gọi vào revision cũ | Dùng `latest_revision_fqdn` | Đổi sang FQDN ổn định |

---

## 20. Tóm tắt bằng một khối lệnh

Chỉ dùng khi đã hiểu các mục trên và state còn nguyên (kịch bản A):

```powershell
# 0. phiên
$T="C:\Users\vieth\Downloads\terraform_1.15.8_windows_amd64\terraform.exe"
$env:TF_CLI_CONFIG_FILE="C:\Users\vieth\AppData\Local\Temp\lg-terraformrc"
$RG="learn-guard-dev"; $ENVDIR="D:\Learn-guard\learnguard-platform\infra\env\dev"
$SEEDDIR="C:\Users\vieth\.lg-seed"; cd $ENVDIR

# 1. hạ tầng
& $T apply -refresh=false -input=false -parallelism=1

# 2. image
cd "D:\Learn-guard\learnguard-platform"
$ACR=(& $T output -raw acr_login_server).Split('.')[0]
.\deploy\docker\build-push.ps1 -AcrName $ACR -Component api -Tag 0.1.0
.\deploy\docker\build-push.ps1 -AcrName $ACR -Component ml  -Tag 0.1.0
# -> cập nhật terraform.tfvars bằng digest vừa in

# 3. khóa SSH
cd $ENVDIR
& $T output -raw jump_ssh_private_key | Out-File -Encoding ascii -NoNewline "$SEEDDIR\jump_key"
$JUMP = & $T output -raw jump_public_ip

# 4. file lên VM
scp -i "$SEEDDIR\jump_key" D:\Learn-guard\BE-MLOPS\db_schema_seed.sql lgops@${JUMP}:/tmp/
scp -i "$SEEDDIR\jump_key" "$ENVDIR\..\..\..\deploy\db\roles.sql" lgops@${JUMP}:/tmp/
scp -i "$SEEDDIR\jump_key" "$ENVDIR\..\..\..\deploy\db\seed.sh"   lgops@${JUMP}:/tmp/
scp -i "$SEEDDIR\jump_key" D:\Learn-guard\Data-ML-MLOPS\data\archive.zip lgops@${JUMP}:/tmp/
scp -i "$SEEDDIR\jump_key" "$ENVDIR\..\..\..\deploy\ml\ml_pipeline.py" lgops@${JUMP}:/tmp/

# 5. trên VM: tạo /tmp/lg.env (mục 7.1) rồi
#    /tmp/seed.sh
#    giải nén + upload dataset (mục 8.1)
#    upload ml_pipeline.py (mục 8.2)

# 6. bật app
cd $ENVDIR
& $T apply -refresh=false -input=false -parallelism=1

# 7. pipeline
az containerapp job start -n caj-lg-dev-ml -g $RG

# 8. frontend (mục 11)
```
