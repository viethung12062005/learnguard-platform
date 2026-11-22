# LearnGuard — build & push image lên ACR (local Docker).
#
# Cách dùng:
#   pwsh deploy/docker/build-push.ps1 -AcrName acrdevxxxxx -Component api -Tag 0.1.0
#   pwsh deploy/docker/build-push.ps1 -AcrName acrdevxxxxx -Component ml  -Tag 0.1.0
#
# Sau khi push, script in digest (@sha256:...) để ghim vào deploy (deploy_apps=true).
# KHÔNG in mật khẩu/secret — chỉ in image ref + digest.

param(
  [Parameter(Mandatory = $true)][string]$AcrName,
  [Parameter(Mandatory = $true)][ValidateSet("api", "ml")][string]$Component,
  [Parameter(Mandatory = $true)][string]$Tag
)

$ErrorActionPreference = "Stop"

# Docker Desktop cài user-local, chưa chắc có trong PATH → thêm để docker +
# docker-credential-desktop tìm được (cần cho credsStore "desktop").
$dockerBin = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin"
if ((Test-Path $dockerBin) -and ($env:Path -notlike "*$dockerBin*")) {
  $env:Path = "$dockerBin;$env:Path"
}

$repoMap = @{
  api = @{ repo = "learnguard-api"; app = "D:/Learn-guard/BE-MLOPS";        dockerfile = "Dockerfile.api" }
  ml  = @{ repo = "learnguard-ml";  app = "D:/Learn-guard/Data-ML-MLOPS";   dockerfile = "Dockerfile.ml" }
}
$c = $repoMap[$Component]

$platformRoot = "D:/Learn-guard/learnguard-platform"
$dockerfile = Join-Path $platformRoot "deploy/docker/$($c.dockerfile)"
$image = "$AcrName.azurecr.io/$($c.repo):$Tag"

Write-Host "== az acr login $AcrName =="
az acr login --name $AcrName
if ($LASTEXITCODE -ne 0) { throw "az acr login failed" }

Write-Host "== docker build $image =="
# Dockerfile nằm ngoài build context (app repo read-only); -f trỏ tới platform repo.
docker build -f $dockerfile -t $image $c.app
if ($LASTEXITCODE -ne 0) { throw "docker build failed" }

Write-Host "== docker push $image =="
docker push $image
if ($LASTEXITCODE -ne 0) { throw "docker push failed" }

$digest = docker image inspect --format '{{index .RepoDigests 0}}' $image
Write-Host ""
Write-Host "OK. Dùng digest này cho deploy (deploy_apps=true):"
Write-Host "  $digest"
