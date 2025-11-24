[CmdletBinding()] param(
  [string]$ComposeFile = "$(Split-Path -Parent $PSCommandPath)\..\docker-compose.yml"
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Write-Host "== jsonify2ai :: start_all" -ForegroundColor Cyan
$root = Resolve-Path (Join-Path (Split-Path -Parent $PSCommandPath) "..")
Set-Location $root

# Optionally ensure tokens (non-blocking - don't fail if tokens aren't needed in local mode)
try {
  & "$PSScriptRoot\ensure_tokens.ps1" | Out-Null
} catch {
  Write-Host "Note: Token generation skipped (not required for local mode)" -ForegroundColor Yellow
}

try {
  if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
    Write-Host "Starting Docker Desktop..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 8
  }
} catch {}

Write-Host "Bringing services up..." -ForegroundColor Cyan
docker compose -f "$ComposeFile" up -d qdrant worker api web

Write-Host ""
Write-Host "== READY" -ForegroundColor Green
Write-Host "API: http://localhost:8082"
Write-Host "Web: http://localhost:5173"
Write-Host "Mode: AUTH_MODE=local (no auth required)"
Write-Host ""
Write-Host "Open http://localhost:5173 in your browser to get started."
