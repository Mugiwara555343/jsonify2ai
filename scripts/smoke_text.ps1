<#
  scripts/smoke_text.ps1
  One-shot smoke test: Ingest → Stats → Ask → API health

  Usage:
    pwsh -ExecutionPolicy Bypass -File scripts/smoke_text.ps1
    # or with overrides:
    pwsh -ExecutionPolicy Bypass -File scripts/smoke_text.ps1 -Dir "data\demo" -ApiBase "http://localhost:8080" -WorkerBase "http://localhost:8090"
#>

param(
  [string]$Dir = "data\dropzone",
  [string]$Export = "data\exports\ingest.jsonl",
  [string]$ApiBase = "$(if ($env:PORT_API) { "http://localhost:$($env:PORT_API)" } else { "http://localhost:8080" })",
  [string]$WorkerBase = "$(if ($env:WORKER_URL) { $env:WORKER_URL } else { "http://localhost:8090" })",
  [switch]$LLM  # add --llm to examples/ask_local.py
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Section($t) {
  Write-Host ""
  Write-Host "==== $t ====" -ForegroundColor Cyan
}

function Ensure-Python() {
  try {
    $py = (Get-Command python).Source
    return $py
  } catch {
    Write-Error "Python not found on PATH. Install Python 3 and retry."
    exit 1
  }
}

function Ensure-Dirs([string]$p) {
  $d = New-Item -ItemType Directory -Force -Path $p -ErrorAction SilentlyContinue
}

# Move to repo root (script folder’s parent)
Set-Location (Split-Path -Parent $PSScriptRoot)

# Env for worker imports
$env:PYTHONPATH = "worker"

# 0) Show config
Write-Section "Config"
Write-Host "Dir........: $Dir"
Write-Host "Export.....: $Export"
Write-Host "API Base...: $ApiBase"
Write-Host "Worker Base: $WorkerBase"
if ($LLM) { Write-Host "LLM Mode...: ON" }

# 1) Ensure basics
$python = Ensure-Python
Ensure-Dirs (Split-Path -Parent $Export)

# 2) Ingest (idempotent replace)
Write-Section "Ingest"
try {
  $ingestRaw = & $python scripts/ingest_dropzone.py --dir $Dir --export $Export --replace-existing 2>&1
  $ingestOut = $ingestRaw | Out-String
  Write-Host $ingestOut
  $ingestJson = $ingestOut | ConvertFrom-Json
} catch {
  Write-Error "Ingest failed. Output:`n$ingestOut"
  exit 2
}

# 3) Stats (total + per-kind + filtered if desired)
Write-Section "Stats"
try {
  $statsRaw = & $python scripts/ingest_dropzone.py --stats 2>&1
  $statsOut = $statsRaw | Out-String
  Write-Host $statsOut
  $statsJson = $statsOut | ConvertFrom-Json
} catch {
  Write-Warning "Stats check failed (non-fatal)."
}

# 4) Ask (retrieval-only by default; toggle with -LLM)
Write-Section "Ask (local)"
$askArgs = @("examples/ask_local.py", "--q", "How do I install it?", "-k", "5", "--show-sources")
if ($LLM) { $askArgs += "--llm" }
try {
  $askOut = & $python @askArgs 2>&1
  $askTxt = $askOut | Out-String
  Write-Host $askTxt
} catch {
  Write-Warning "Ask script failed (non-fatal): $($_.Exception.Message)"
}

# 5) API health
Write-Section "API /health/full"
$apiHealthy = $false
try {
  $full = Invoke-RestMethod -Uri "$ApiBase/health/full" -TimeoutSec 10 -Method GET
  $apiHealthy = ($full.ok -eq $true)
  $full | ConvertTo-Json -Depth 6 | Write-Host
} catch {
  Write-Warning "API /health/full unreachable: $($_.Exception.Message)"
}

# 6) API /status passthrough
Write-Section "API /status"
try {
  $st = Invoke-RestMethod -Uri "$ApiBase/status" -TimeoutSec 10 -Method GET
  $st | ConvertTo-Json -Depth 6 | Write-Host
} catch {
  Write-Warning "API /status unreachable: $($_.Exception.Message)"
}

# 7) Quick assertions and exit code
Write-Section "Result"
$chunks = 0
try {
  if ($statsJson -and $statsJson.total) { $chunks = [int]$statsJson.total }
  elseif ($ingestJson -and $ingestJson.chunks_upserted) { $chunks = [int]$ingestJson.chunks_upserted }
} catch {}

if (-not $apiHealthy) {
  Write-Error "API health check failed."
  exit 3
}
if ($chunks -le 0) {
  Write-Error "No chunks indexed (expected > 0)."
  exit 4
}

Write-Host "Smoke test PASSED ✅" -ForegroundColor Green
exit 0
