<# ensure_api_token.ps1 — creates API_AUTH_TOKEN in .env if missing #>
[CmdletBinding()] param(
  [string]$EnvPath = "$(Split-Path -Parent $PSCommandPath)\..\.env"
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Load-DotEnv([string]$Path) {
  if (-not (Test-Path $Path)) { return @{} }
  $map=@{}
  (Get-Content -Raw $Path).Split("`n") | ForEach-Object {
    $l=$_.Trim(); if (-not $l -or $l.StartsWith('#')) { return }
    if ($l -match '^\s*([^=]+)\s*=\s*(.*)$') {
      $k=$matches[1].Trim(); $v=$matches[2].Trim('"').Trim("'"); $map[$k]=$v
    }
  }; return $map
}

function Save-Env([string]$Path, [hashtable]$Map) {
  $lines = @()
  foreach ($k in $Map.Keys) {
    $v = $Map[$k]
    $lines += "$k=$v"
  }
  Set-Content -NoNewline -Path $Path -Value ($lines -join "`n")
  Add-Content -Path $Path -Value "`n"
}

$envMap = Load-DotEnv $EnvPath
if (-not $envMap.ContainsKey("API_AUTH_TOKEN") -or [string]::IsNullOrWhiteSpace($envMap["API_AUTH_TOKEN"])) {
  # generate 32-byte token (hex)
  $token = -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
  $envMap["API_AUTH_TOKEN"] = $token
  if (-not (Test-Path $EnvPath)) { New-Item -Force -Path $EnvPath | Out-Null }
  Save-Env $EnvPath $envMap
  Write-Host "API_AUTH_TOKEN created and saved to .env" -ForegroundColor Green
} else {
  Write-Host "API_AUTH_TOKEN present in .env" -ForegroundColor Cyan
}
