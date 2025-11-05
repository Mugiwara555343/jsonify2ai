[CmdletBinding()] param(
  [string]$ComposeFile = "$(Split-Path -Parent $PSCommandPath)\..\docker-compose.yml"
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Resolve-Path (Join-Path (Split-Path -Parent $PSCommandPath) "..")
Set-Location $root

Write-Host "== jsonify2ai :: stop_all" -ForegroundColor Cyan
docker compose -f "$ComposeFile" stop
Write-Host "== STOPPED" -ForegroundColor Green
