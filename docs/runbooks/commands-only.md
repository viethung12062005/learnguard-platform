# Runbook lệnh — copy/paste từ đầu đến cuối

> Chỉ có lệnh. Chạy **tuần tự từng khối** trong **PowerShell** trên máy bạn.
> Mọi thao tác trong VNet đều được đẩy qua SSH nên không cần mở phiên VM riêng.
> Mọi giá trị đều lấy từ biến ở BƯỚC 0 và `terraform output` — không cần sửa tay.
> Giải thích chi tiết: `deploy-runbook.md`.

```powershell
# ===========================================================================
# BƯỚC 0 — BIẾN CHUNG VÀ ĐĂNG NHẬP
# ===========================================================================
$T        = "C:\Users\vieth\Downloads\terraform_1.15.8_windows_amd64\terraform.exe"
$RG       = "learn-guard-dev"
$SUB      = "c4a86d00-6328-4d7b-8c75-6293553cd19c"
$PLATFORM = "D:\Learn-guard\learnguard-platform"
$ENVDIR   = "$PLATFORM\infra\env\dev"
$SEEDDIR  = "C:\Users\vieth\.lg-seed"
$OPERATOR_CIDR = "113.185.0.0/16"
$TAG = "0.1.0"

$env:TF_CLI_CONFIG_FILE = "C:\Users\vieth\AppData\Local\Temp\lg-terraformrc"
New-Item -ItemType Directory $SEEDDIR -Force | Out-Null

# Extension cần cho job / static web app (idempotent)
az extension add --name containerapp  --only-show-errors 2>$null
az extension add --name staticwebapp --only-show-errors 2>$null

# Lấy storage key, retry vì mạng hay reset
function Get-LgStorageKey {
  for ($i = 0; $i -lt 6; $i++) {
    $k = az storage account keys list --account-name $STG --resource-group $RG --query "[0].value" -o tsv --only-show-errors
    if ($k) { return $k }
    Start-Sleep -Seconds 5
  }
  throw "Không lấy được storage key"
}

az login
az account set --subscription $SUB
az account show --query "{name:name, id:id}" -o table
```

```powershell
# ===========================================================================
# BƯỚC 1 — GHI terraform.tfvars (lần 1: CHƯA bật app)
# ===========================================================================
$tfvars = @"
location         = "eastasia"
environment      = "dev"
operator_ip_cidr = "$OPERATOR_CIDR"
deploy_apps      = false
api_image        = ""
job_image        = ""
"@
[IO.File]::WriteAllText("$ENVDIR\terraform.tfvars", $tfvars)
```

```powershell
# ===========================================================================
# BƯỚC 2 — DỰNG HẠ TẦNG
# ===========================================================================
cd $ENVDIR
& $T init
& $T validate
& $T apply -input=false -auto-approve -parallelism=1
```

```powershell
# ===========================================================================
# BƯỚC 3 — ĐỌC OUTPUT VÀO BIẾN
# ===========================================================================
cd $ENVDIR
$ACR     = (& $T output -raw acr_login_server).Split('.')[0]
$STG     = & $T output -raw storage_account_name
$KV      = & $T output -raw key_vault_name
$PGFQDN  = & $T output -raw postgres_fqdn
$JUMP    = & $T output -raw jump_public_ip
$CAEDOM  = & $T output -raw container_app_default_domain
$SWAHOST = & $T output -raw static_web_app_host
$ACR; $STG; $KV; $PGFQDN; $JUMP; $CAEDOM; $SWAHOST
```

```powershell
# ===========================================================================
# BƯỚC 4 — XUẤT KHÓA SSH
# ===========================================================================
cd $ENVDIR
& $T output -raw jump_ssh_private_key | Out-File -Encoding ascii -NoNewline "$SEEDDIR\jump_key"
icacls "$SEEDDIR\jump_key" /inheritance:r /grant:r "$env:USERNAME:(R)"

ssh -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new lgops@$JUMP "echo SSH_OK"
```

```powershell
# ===========================================================================
# BƯỚC 5 — BUILD + PUSH IMAGE, LẤY DIGEST, CẬP NHẬT tfvars
# ===========================================================================
cd $PLATFORM
.\deploy\docker\build-push.ps1 -AcrName $ACR -Component api -Tag $TAG
.\deploy\docker\build-push.ps1 -AcrName $ACR -Component ml  -Tag $TAG

$API_REF = docker image inspect --format '{{index .RepoDigests 0}}' "$ACR.azurecr.io/learnguard-api:$TAG"
$ML_REF  = docker image inspect --format '{{index .RepoDigests 0}}' "$ACR.azurecr.io/learnguard-ml:$TAG"
$API_REF
$ML_REF

$tfvars = @"
location         = "eastasia"
environment      = "dev"
operator_ip_cidr = "$OPERATOR_CIDR"
deploy_apps      = true
api_image        = "$API_REF"
job_image        = "$ML_REF"
"@
[IO.File]::WriteAllText("$ENVDIR\terraform.tfvars", $tfvars)
```

```powershell
# ===========================================================================
# BƯỚC 6 — ĐƯA FILE LÊN JUMP VM
# ===========================================================================
scp -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new `
  D:\Learn-guard\BE-MLOPS\db_schema_seed.sql lgops@${JUMP}:/tmp/

scp -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new `
  "$PLATFORM\deploy\db\roles.sql" "$PLATFORM\deploy\db\seed.sh" lgops@${JUMP}:/tmp/

scp -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new `
  D:\Learn-guard\Data-ML-MLOPS\data\archive.zip lgops@${JUMP}:/tmp/

scp -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new `
  "$PLATFORM\deploy\ml\ml_pipeline.py" lgops@${JUMP}:/tmp/

ssh -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new lgops@$JUMP `
  "ls -l /tmp/db_schema_seed.sql /tmp/roles.sql /tmp/seed.sh /tmp/archive.zip /tmp/ml_pipeline.py"
```

```powershell
# ===========================================================================
# BƯỚC 7 — SEED DATABASE + KEY VAULT (chạy trên VM qua SSH)
# ===========================================================================
cd $ENVDIR
$PGPW  = & $T output -raw pg_admin_password
$ACRPW = & $T output -raw acr_admin_password

$envContent = "PG_FQDN=$PGFQDN`nPG_DB=learnguard`nPG_ADMIN_LOGIN=lgadmin`nPG_ADMIN_PW=$PGPW`nACR_PW=$ACRPW`nKV_NAME=$KV`n"
$envContent | ssh -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new lgops@$JUMP `
  "cat > /tmp/lg.env; chmod 600 /tmp/lg.env; echo ENV_OK"

ssh -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new lgops@$JUMP `
  "chmod +x /tmp/seed.sh && /tmp/seed.sh"

Remove-Variable PGPW, ACRPW, envContent
```

```powershell
# ===========================================================================
# BƯỚC 8 — UPLOAD DATASET OULAD LÊN AZURE FILES
# ===========================================================================
ssh -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new lgops@$JUMP `
  "cd /tmp && rm -rf oulad && mkdir oulad && unzip -q -o archive.zip -d oulad && ls oulad"

$K = Get-LgStorageKey
$K | ssh -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new lgops@$JUMP `
  "read -r KEY; export AZURE_STORAGE_ACCOUNT=$STG AZURE_STORAGE_KEY=`$KEY AZURE_STORAGE_AUTH_MODE=key; unset KEY; az storage file upload-batch --destination lgdata --source /tmp/oulad --destination-path oulad --only-show-errors --output none; echo UPLOAD_DONE"

$K | ssh -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new lgops@$JUMP `
  "read -r KEY; AZURE_STORAGE_ACCOUNT=$STG AZURE_STORAGE_KEY=`$KEY AZURE_STORAGE_AUTH_MODE=key az storage file list --share-name lgdata --path oulad --output table"

Remove-Variable K
```

```powershell
# ===========================================================================
# BƯỚC 9 — UPLOAD SCRIPT PIPELINE ML
# ===========================================================================
$K = Get-LgStorageKey
$K | ssh -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new lgops@$JUMP `
  "read -r KEY; export AZURE_STORAGE_ACCOUNT=$STG AZURE_STORAGE_KEY=`$KEY AZURE_STORAGE_AUTH_MODE=key; unset KEY; az storage directory create --share-name lgdata --name scripts --only-show-errors; az storage file upload --share-name lgdata --source /tmp/ml_pipeline.py --path scripts/ml_pipeline.py --only-show-errors --output none; echo SCRIPT_UPLOADED"

$K | ssh -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new lgops@$JUMP `
  "read -r KEY; AZURE_STORAGE_ACCOUNT=$STG AZURE_STORAGE_KEY=`$KEY AZURE_STORAGE_AUTH_MODE=key az storage file list --share-name lgdata --path scripts --output table"

Remove-Variable K
```

```powershell
# ===========================================================================
# BƯỚC 10 — BẬT CONTAINER APP + JOB ML
# ===========================================================================
cd $ENVDIR
& $T plan -out=tfplan-apps
& $T apply tfplan-apps

$API_FQDN = & $T output -raw api_fqdn
$API = "https://$API_FQDN"
$API
```

```powershell
# ===========================================================================
# BƯỚC 11 — CHẠY PIPELINE ML VÀ KIỂM TRA
# ===========================================================================
az containerapp job start -n caj-lg-dev-ml -g $RG

# Chờ job kết thúc (tối đa ~5 phút). Dừng ngay khi có kết quả cuối.
for ($i = 0; $i -lt 30; $i++) {
  $s = az containerapp job execution list -n caj-lg-dev-ml -g $RG --query "[0].properties.status" -o tsv
  if ($s -eq "Succeeded" -or $s -eq "Failed") { Write-Host "JOB: $s"; break }
  Write-Host "JOB: $s - chờ 10s..."
  Start-Sleep -Seconds 10
}

az containerapp job execution list -n caj-lg-dev-ml -g $RG -o table
curl.exe "$API/health"
```

```powershell
# ===========================================================================
# BƯỚC 12 — KIỂM TRA DATABASE (qua VM)
# ===========================================================================
$PGPW = & $T output -raw pg_admin_password
$PGPW | ssh -i "$SEEDDIR\jump_key" -o StrictHostKeyChecking=accept-new lgops@$JUMP `
  "read -r P; PGPASSWORD=`$P psql -h $PGFQDN -U lgadmin -d learnguard -Atc 'select run_id, count(*) from ml_predictions group by run_id order by run_id desc limit 5;'"
Remove-Variable PGPW
```

```powershell
# ===========================================================================
# BƯỚC 13 — BUILD + DEPLOY FRONTEND
# ===========================================================================
cd D:\Learn-guard\FE-MLOPS
$env:VITE_BACKEND_API_URL = "https://$API_FQDN"
$env:VITE_USE_MOCK         = "false"
npm ci
npm run build
Copy-Item "$PLATFORM\deploy\frontend\staticwebapp.config.json" .\dist\ -Force

$TOKEN = az staticwebapp secrets list -n swa-lg-dev -g $RG --query properties.apiKey -o tsv
npx -y "@azure/static-web-apps-cli@2.0.6" deploy .\dist --deployment-token $TOKEN --env production
Remove-Variable TOKEN
```

```powershell
# ===========================================================================
# BƯỚC 14 — SMOKE TEST
# ===========================================================================
curl.exe "$API/health"
curl.exe "$API/predictions?limit=2"
curl.exe -o NUL -w "FE root : %{http_code}`n" "$SWAHOST/"
curl.exe -o NUL -w "FE /review: %{http_code}`n" "$SWAHOST/review"
```

```powershell
# ===========================================================================
# BƯỚC 15 — DESTROY
# ===========================================================================
cd $ENVDIR
& $T destroy -refresh=false -input=false -parallelism=1

az resource list -g $RG -o table
az keyvault list-deleted --query "[].name" -o tsv
```

```powershell
# ===========================================================================
# BƯỚC 16A — REDEPLOY KHI CÒN STATE (tên giữ nguyên)
# ===========================================================================
cd $ENVDIR

# Nếu Key Vault còn soft-deleted và muốn dùng lại:
az keyvault recover --name $KV --resource-group $RG
# Hoặc xoá hẳn để tạo mới:
# az keyvault purge --name $KV --location eastasia

& $T apply -refresh=false -input=false -parallelism=1

# Từ đây chạy lại: BƯỚC 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11 -> 12 -> 13 -> 14
```

```powershell
# ===========================================================================
# BƯỚC 16B — REDEPLOY KHI MẤT STATE (tên mới)
# ===========================================================================
cd $ENVDIR
Move-Item terraform.tfstate        terraform.tfstate.old        -ErrorAction SilentlyContinue
Move-Item terraform.tfstate.backup terraform.tfstate.old.backup -ErrorAction SilentlyContinue

# BẮT BUỘC: tfvars cũ trỏ tới ACR đã bị xoá → phải tắt app trước khi apply
$tfvars = @"
location         = "eastasia"
environment      = "dev"
operator_ip_cidr = "$OPERATOR_CIDR"
deploy_apps      = false
api_image        = ""
job_image        = ""
"@
[IO.File]::WriteAllText("$ENVDIR\terraform.tfvars", $tfvars)

& $T init
& $T apply -input=false -auto-approve -parallelism=1

# Từ đây chạy lại từ BƯỚC 3 (biến sẽ mang giá trị mới), rồi 4 -> 5 -> ... -> 14
```

```powershell
# ===========================================================================
# BƯỚC 16C — CHỈ DEPLOY LẠI ỨNG DỤNG (giữ hạ tầng)
# ===========================================================================
cd $PLATFORM
$TAG = "0.1.1"
.\deploy\docker\build-push.ps1 -AcrName $ACR -Component api -Tag $TAG
.\deploy\docker\build-push.ps1 -AcrName $ACR -Component ml  -Tag $TAG

$API_REF = docker image inspect --format '{{index .RepoDigests 0}}' "$ACR.azurecr.io/learnguard-api:$TAG"
$ML_REF  = docker image inspect --format '{{index .RepoDigests 0}}' "$ACR.azurecr.io/learnguard-ml:$TAG"

cd $ENVDIR
& $T apply -auto-approve -var="api_image=$API_REF" -var="job_image=$ML_REF" -parallelism=1

# Chỉ chạy lại pipeline:
az containerapp job start -n caj-lg-dev-ml -g $RG

# Chỉ deploy lại frontend: chạy BƯỚC 13
```

```powershell
# ===========================================================================
# PHỤ — LOG VÀ TRẠNG THÁI
# ===========================================================================
$WS = az monitor log-analytics workspace show --ids (& $T output -raw log_analytics_workspace_id) --query customerId -o tsv

az containerapp revision list -n ca-lg-dev-api -g $RG `
  --query "[?properties.active].{name:name,created:properties.createdTime}" -o table

az monitor log-analytics query -w $WS --analytics-query `
  "ContainerAppConsoleLogs_CL | where ContainerAppName_s == 'ca-lg-dev-api' | order by TimeGenerated desc | take 30 | project TimeGenerated, Log_s" -o table

az monitor log-analytics query -w $WS --analytics-query `
  "ContainerAppConsoleLogs_CL | where ContainerJobName_s == 'caj-lg-dev-ml' | order by TimeGenerated desc | take 30 | project TimeGenerated, Log_s" -o table
```

```powershell
# ===========================================================================
# PHỤ — DỌN BIẾN TẠM CUỐI PHIÊN
# ===========================================================================
Remove-Variable API_REF, ML_REF, API, API_FQDN, TOKEN, K -ErrorAction SilentlyContinue
```
