<#
.SYNOPSIS
    Stop and remove the FinAlly container (Windows PowerShell). Idempotent.
    The 'finally-data' volume is NOT removed, so your data persists.
#>

$ErrorActionPreference = 'Continue'

$Container = 'finally'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error 'docker is not installed or not on PATH.'
    exit 1
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error 'The Docker daemon is not running.'
    exit 1
}

docker container inspect $Container *> $null
if ($LASTEXITCODE -eq 0) {
    docker rm -f $Container *> $null
    Write-Host "Stopped and removed container '$Container' (volume 'finally-data' kept)."
} else {
    Write-Host "Container '$Container' is not running; nothing to do."
}
