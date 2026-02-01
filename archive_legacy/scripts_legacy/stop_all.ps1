[CmdletBinding()] param(
  [string]$ComposeFile = "$(Split-Path -Parent $PSCommandPath)\..\docker-compose.yml",
  [switch]$Wipe
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Resolve-Path (Join-Path (Split-Path -Parent $PSCommandPath) "..")
Set-Location $root

Write-Host "== jsonify2ai :: stop_all" -ForegroundColor Cyan

if ($Wipe) {
  Write-Host "Stopping services and removing volumes..." -ForegroundColor Yellow
  docker compose -f "$ComposeFile" down -v
} else {
  docker compose -f "$ComposeFile" down
}

Write-Host "== STOPPED" -ForegroundColor Green
