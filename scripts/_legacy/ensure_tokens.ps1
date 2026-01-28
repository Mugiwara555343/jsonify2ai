[CmdletBinding()] param(
  [string]$EnvPath = "$(Split-Path -Parent $PSCommandPath)\..\.env"
)
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
if (-not (Test-Path $EnvPath) -and (Test-Path "$EnvPath.example")) {
  Copy-Item "$EnvPath.example" $EnvPath -Force
}
$map=@{}
if (Test-Path $EnvPath) {
  (Get-Content -Raw $EnvPath).Split("`n") | % {
    $l=$_.Trim(); if (!$l -or $l.StartsWith('#')) { return }
    if ($l -match '^\s*([^=]+)\s*=\s*(.*)$'){ $map[$matches[1]]=$matches[2] }
  }
}
function gen { -join ((1..32) | % { '{0:x2}' -f (Get-Random -Max 256) }) }
if (-not $map.ContainsKey('API_AUTH_TOKEN') -or [string]::IsNullOrWhiteSpace($map['API_AUTH_TOKEN'])) { $map['API_AUTH_TOKEN']=gen }
if (-not $map.ContainsKey('WORKER_AUTH_TOKEN') -or [string]::IsNullOrWhiteSpace($map['WORKER_AUTH_TOKEN'])) { $map['WORKER_AUTH_TOKEN']=gen }
# Ensure VITE_API_TOKEN matches API_AUTH_TOKEN for web bundle
if ($map.ContainsKey('API_AUTH_TOKEN') -and -not [string]::IsNullOrWhiteSpace($map['API_AUTH_TOKEN'])) {
  $map['VITE_API_TOKEN'] = $map['API_AUTH_TOKEN']
}
$lines=@(); foreach($k in $map.Keys){ $lines+=("$k="+$map[$k].Trim()) }
Set-Content -NoNewline -Path $EnvPath -Value ($lines -join "`n"); Add-Content -Path $EnvPath -Value "`n"
Write-Host "Tokens ensured in .env" -ForegroundColor Green
