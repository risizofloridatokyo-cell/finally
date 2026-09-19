<#
.SYNOPSIS
    Start FinAlly in Docker (Windows PowerShell). Idempotent: safe to run repeatedly.

.PARAMETER Build
    Rebuild the image even if it already exists.

.PARAMETER NoOpen
    Do not open the browser.

.EXAMPLE
    .\scripts\start_windows.ps1
    .\scripts\start_windows.ps1 -Build -NoOpen
#>
param(
    [switch]$Build,
    [switch]$NoOpen
)

# Native commands report failure via $LASTEXITCODE; do not turn their stderr into terminating errors.
$ErrorActionPreference = 'Continue'

$Image = 'finally'
$Container = 'finally'
$Volume = 'finally-data'
$Port = 8000
$Url = "http://localhost:$Port"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error 'docker is not installed or not on PATH.'
    exit 1
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error 'The Docker daemon is not running. Start Docker Desktop and retry.'
    exit 1
}

if (-not (Test-Path (Join-Path $Root '.env'))) {
    Write-Error ".env not found in $Root. Create it from the template and add your OpenRouter key:  Copy-Item .env.example .env"
    exit 1
}

docker image inspect $Image *> $null
$ImageExists = ($LASTEXITCODE -eq 0)

if ($Build -or -not $ImageExists) {
    Write-Host "Building image '$Image'..."
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'docker build failed.'
        exit 1
    }
} else {
    Write-Host "Using existing image '$Image' (pass -Build to rebuild)."
}

# Replace any existing container (running or stopped) with the same name.
docker container inspect $Container *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Replacing existing container '$Container'..."
    docker rm -f $Container *> $null
}

Write-Host "Starting container '$Container'..."
docker run -d --name $Container -v "${Volume}:/app/db" -p "${Port}:8000" --env-file .env $Image *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker run failed (is port $Port already in use?)."
    exit 1
}

# Wait (up to ~30s) for the API to come up.
Write-Host -NoNewline 'Waiting for the app to become healthy'
$Ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "$Url/api/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $Ready = $true; break }
    } catch {
        # not up yet
    }
    Write-Host -NoNewline '.'
    Start-Sleep -Seconds 1
}
Write-Host ''
if (-not $Ready) {
    Write-Warning "The app did not report healthy within 30s. Check logs:  docker logs $Container"
}

Write-Host "FinAlly is running at $Url"
Write-Host 'Stop it with: .\scripts\stop_windows.ps1'

if (-not $NoOpen) {
    Start-Process $Url
}
