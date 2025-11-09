[CmdletBinding()] param(
  [int]$TimeoutSec = 90,
  [string]$ComposeFile = "$(Split-Path -Parent $PSCommandPath)\..\docker-compose.yml",
  [string]$WebUrl = "http://localhost:5173"
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Load-DotEnv([string]$Path) {
  if (-not (Test-Path $Path)) { return @{} }
  $m=@{}; (Get-Content -Raw $Path).Split("`n") | ForEach-Object {
    $l=$_.Trim(); if (-not $l -or $l.StartsWith('#')) {return}
    if ($l -match '^\s*([^=]+)\s*=\s*(.*)$') {
      $k=$matches[1].Trim(); $v=$matches[2].Trim('"').Trim("'"); $m[$k]=$v
    }
  } ; return $m
}

Write-Host "== jsonify2ai :: start_all" -ForegroundColor Cyan
$root = Resolve-Path (Join-Path (Split-Path -Parent $PSCommandPath) "..")
Set-Location $root

# Ensure API_AUTH_TOKEN exists before starting services
& "$PSScriptRoot\ensure_tokens.ps1" | Out-Null

$null = Load-DotEnv ".env"

try {
  if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
    Write-Host "Starting Docker Desktop..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 8
  }
} catch {}

Write-Host "Bringing services up..." -ForegroundColor Cyan
docker compose -f "$ComposeFile" up -d | Out-Null

function Wait-Http($url, $expect=200) {
  $stop=(Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $stop) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri $url -Method GET -TimeoutSec 4
      if ($r.StatusCode -eq $expect) { return $true }
    } catch {}
    Start-Sleep -Milliseconds 800
  }
  return $false
}

$okWorker = Wait-Http "http://localhost:8090/status" 200
$okApi    = Wait-Http "http://localhost:8082/health/full" 200
$okWeb    = Wait-Http $WebUrl 200

Write-Host "health :: worker=$okWorker api=$okApi web=$okWeb"
if (-not $okApi)  { Write-Warning "API not healthy yet." }
if (-not $okWeb)  { Write-Warning "Web UI not responding yet." }

try { Start-Process $WebUrl } catch {}
Write-Host "== READY" -ForegroundColor Green
Write-Host "Open: $WebUrl"
