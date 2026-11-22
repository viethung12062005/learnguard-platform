<#
.SYNOPSIS
  Smoke test API sau khi deploy revision mới; rollback traffic nếu fail.

.DESCRIPTION
  Container Apps giữ revision cũ (revision_mode = Multiple). Nếu revision mới
  không qua smoke test, chuyển 100% traffic về revision trước đó — rollback
  tức thời, không cần rebuild.

.EXAMPLE
  .\smoke-and-rollback.ps1 -AppName lg-dev-api -ResourceGroup learn-guard-dev -Fqdn lg-dev-api.xxx.eastasia.azurecontainerapps.io
#>
param(
  [Parameter(Mandatory = $true)][string]$AppName,
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$Fqdn,
  [string]$Path = "/health",
  [int]$Retries = 12,
  [int]$DelaySeconds = 10
)

$ErrorActionPreference = "Stop"
$url = "https://$Fqdn$Path"

$ok = $false
for ($i = 1; $i -le $Retries; $i++) {
  try {
    $r = Invoke-WebRequest -Uri $url -TimeoutSec 15 -UseBasicParsing
    if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { $ok = $true; break }
    Write-Host "lan $i/$Retries : HTTP $($r.StatusCode)"
  }
  catch {
    Write-Host "lan $i/$Retries : $($_.Exception.Message)"
  }
  Start-Sleep -Seconds $DelaySeconds
}

if ($ok) {
  Write-Host "SMOKE OK - $url"
  exit 0
}

Write-Warning "Smoke test that bai sau $Retries lan thu. Bat dau rollback."

$revs = az containerapp revision list -n $AppName -g $ResourceGroup --query "sort_by(@, &properties.createdTime)" -o json | ConvertFrom-Json
$active = @($revs | Where-Object { $_.properties.active -eq $true })

if ($active.Count -lt 2) {
  Write-Error "Chi co $($active.Count) revision active - khong the rollback tu dong. Kiem tra thu cong."
  exit 1
}

$new = $active[-1]
$prev = $active[-2]

Write-Host "Rollback: $($new.name) -> $($prev.name)"
az containerapp ingress traffic set -n $AppName -g $ResourceGroup --revision-weight "$($prev.name)=100" "$($new.name)=0"
if ($LASTEXITCODE -ne 0) {
  Write-Error "Rollback that bai - can xu ly thu cong ngay."
  exit 1
}

Write-Host "Da rollback ve $($prev.name)."
exit 1
