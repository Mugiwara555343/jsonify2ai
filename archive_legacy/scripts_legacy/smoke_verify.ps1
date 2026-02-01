# smoke_verify.ps1 — repo-root aware, stable paths, single JSON verdict

[CmdletBinding()] param()

$ErrorActionPreference = "Stop"; Set-StrictMode -Version Latest

# --- Resolve repo root (parent of scripts/) and cd there ---
$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot  = Resolve-Path (Join-Path $scriptDir '..')
Set-Location $repoRoot

function CurlJson([string]$url, [hashtable]$headers) {
  try {
    $wc = New-Object System.Net.WebClient
    foreach ($k in $headers.Keys) { $wc.Headers.Add($k, $headers[$k]) }
    return $wc.DownloadString($url)
  } catch {
    return "{}"
  }
}

# --- Clean start ---
docker compose down -v | Out-Null

# --- Ensure tokens (bootstrap .env) ---
powershell -NoProfile -File (Join-Path $repoRoot 'scripts\ensure_tokens.ps1') | Out-Null

# --- Bring up with rebuild (qdrant, worker, api, web) ---
docker compose up -d --build qdrant worker api web | Out-Null
Start-Sleep -Seconds 3

# --- Optional smoke helper (best-effort) ---
$smokeScript = Join-Path $repoRoot 'scripts\smoke_all.ps1'
if (Test-Path $smokeScript) {
  try {
    $smoke = powershell -NoProfile -File $smokeScript
    Write-Host $smoke
  } catch {
    Write-Host "NOTE: smoke_all.ps1 failed; continuing inline verification."
  }
} else {
  Write-Host "NOTE: scripts\smoke_all.ps1 not found; continuing inline verification."
}

# --- Load tokens (masked) ---
$envPath = Join-Path $repoRoot '.env'
$API_TOKEN = ""; $WORKER_TOKEN = ""
if (Test-Path $envPath) {
  Get-Content $envPath | ForEach-Object {
    if ($_ -match "^\s*API_AUTH_TOKEN\s*=\s*(.+)$")    { $API_TOKEN=$Matches[1].Trim() }
    if ($_ -match "^\s*WORKER_AUTH_TOKEN\s*=\s*(.+)$") { $WORKER_TOKEN=$Matches[1].Trim() }
  }
}

$apiTokShort = if ($API_TOKEN.Length -ge 4) { $API_TOKEN.Substring(0,4) } else { "" }

# --- Health checks ---
$apiHealthRaw    = CurlJson "http://localhost:8082/health/full" @{}
$workerStatusRaw = CurlJson "http://localhost:8090/status" @{}

# --- Ensure seed under repoRoot/data/dropzone ---
$seedPath = Join-Path $repoRoot 'data\dropzone\smoke_cli_seed.md'
$seedDir  = Split-Path -Parent $seedPath
if (-not (Test-Path $seedDir)) { New-Item -Force -ItemType Directory $seedDir | Out-Null }
if (-not (Test-Path $seedPath)) {
  "Qdrant is used for vector search (smoke seed)." | Set-Content $seedPath
}

# --- Upload via API (auth) ---
$boundary = [System.Guid]::NewGuid().ToString("N")
$ct = "multipart/form-data; boundary=$boundary"
$bytes = [System.IO.File]::ReadAllBytes($seedPath)
$filename = [System.IO.Path]::GetFileName($seedPath)
$crlf = "`r`n"
$body = [System.Text.StringBuilder]::new()
$null = $body.Append("--$boundary$crlf")
$null = $body.Append("Content-Disposition: form-data; name=`"file`"; filename=`"$filename`"$crlf")
$null = $body.Append("Content-Type: text/markdown$crlf$crlf")
$bodyBytes = [System.Text.Encoding]::ASCII.GetBytes($body.ToString()) + $bytes + [System.Text.Encoding]::ASCII.GetBytes("$crlf--$boundary--$crlf")

$uploadStatus = 0
try {
  $wc2 = New-Object System.Net.WebClient
  if ($API_TOKEN) { $wc2.Headers.Add("Authorization", "Bearer $API_TOKEN") }
  $wc2.Headers.Add("Content-Type", $ct)
  $resp = $wc2.UploadData("http://localhost:8082/upload", "POST", $bodyBytes)
  $uploadStatus = 200
} catch {
  $uploadStatus = if ($_.Exception.Response) { $_.Exception.Response.StatusCode.value__ } else { 0 }
}

# --- Search via API (auth) ---
$headers = @{}
if ($API_TOKEN) { $headers["Authorization"] = "Bearer $API_TOKEN" }
$search1 = CurlJson "http://localhost:8082/search?kind=text&q=Qdrant&limit=3" $headers
$search2 = CurlJson "http://localhost:8082/search?kind=text&q=vector&limit=3" $headers

# --- Auto-seed if no search hits found ---
function HasHits($json) {
  try { $o = $json | ConvertFrom-Json; return ($o.results -and $o.results.Count -gt 0) } catch { return $false }
}
$hits1Initial = HasHits $search1
$hits2Initial = HasHits $search2

if (-not ($hits1Initial -or $hits2Initial)) {
  # Create unique seed file with timestamp marker
  $timestamp = Get-Date -Format "yyyyMMddHHmmss"
  $uniqueToken = "SMOKE_EXPORT_TOKEN_$timestamp"
  $seedPath = Join-Path $repoRoot "data\dropzone\export_seed.md"
  $seedDir = Split-Path -Parent $seedPath
  if (-not (Test-Path $seedDir)) { New-Item -Force -ItemType Directory $seedDir | Out-Null }
  "Qdrant is used for vector search. $uniqueToken" | Set-Content $seedPath

  # Upload via API with auth (reuse upload logic)
  $boundary = [System.Guid]::NewGuid().ToString("N")
  $ct = "multipart/form-data; boundary=$boundary"
  $bytes = [System.IO.File]::ReadAllBytes($seedPath)
  $filename = [System.IO.Path]::GetFileName($seedPath)
  $crlf = "`r`n"
  $body = [System.Text.StringBuilder]::new()
  $null = $body.Append("--$boundary$crlf")
  $null = $body.Append("Content-Disposition: form-data; name=`"file`"; filename=`"$filename`"$crlf")
  $null = $body.Append("Content-Type: text/markdown$crlf$crlf")
  $bodyBytes = [System.Text.Encoding]::ASCII.GetBytes($body.ToString()) + $bytes + [System.Text.Encoding]::ASCII.GetBytes("$crlf--$boundary--$crlf")

  try {
    $wcSeed = New-Object System.Net.WebClient
    if ($API_TOKEN) { $wcSeed.Headers.Add("Authorization", "Bearer $API_TOKEN") }
    $wcSeed.Headers.Add("Content-Type", $ct)
    $null = $wcSeed.UploadData("http://localhost:8082/upload", "POST", $bodyBytes)
    Write-Host "Auto-seeded export_seed.md with token: $uniqueToken"
  } catch {
    Write-Host "Auto-seed upload failed: $_"
  }

  # Wait for processing
  Start-Sleep -Seconds 3

  # Re-run search queries using unique token
  $search1 = CurlJson "http://localhost:8082/search?kind=text&q=$uniqueToken&limit=3" $headers
  $search2 = CurlJson "http://localhost:8082/search?kind=text&q=export_seed&limit=3" $headers
}

# --- Ask via API ---
$askJson = "{}"
try {
  $wc3 = New-Object System.Net.WebClient
  if ($API_TOKEN) { $wc3.Headers.Add("Authorization","Bearer $API_TOKEN") }
  $wc3.Headers.Add("Content-Type","application/json")
  $askBody = '{"kind":"text","q":"What is Qdrant used for in this repo?"}'
  $askJson = $wc3.UploadString("http://localhost:8082/ask", "POST", $askBody)
} catch { $askJson = "{}" }

# --- Export (best-effort; uses first search result) ---
$exportOk = $false
try {
  $sr = $search1 | ConvertFrom-Json
  if ($sr.results.Count -gt 0) {
    $docId = $sr.results[0].document_id
    $wc4 = New-Object System.Net.WebClient
    if ($API_TOKEN) { $wc4.Headers.Add("Authorization","Bearer $API_TOKEN") }
    $zip = $wc4.DownloadData("http://localhost:8082/export/archive?document_id=$docId&collection=jsonify2ai_chunks_768")
    $exportOk = ($zip.Length -gt 0)
  }
} catch { $exportOk = $false }

# --- Parse & compute verdict ---
$apiHealthOk = $false; try { $apiHealthOk = (($apiHealthRaw | ConvertFrom-Json).ok -eq $true) } catch {}
$workerOk    = $false; try { $workerOk    = (($workerStatusRaw | ConvertFrom-Json).ok -eq $true) } catch {}
$counts = $null; try { $counts = ($workerStatusRaw | ConvertFrom-Json).counts } catch {}
$qdrantPoints = if ($counts) { [int]$counts.total } else { 0 }

# Parse LLM reachability (default false if missing)
$llmReachable = $false
try {
  $llmStatus = ($workerStatusRaw | ConvertFrom-Json).llm
  if ($llmStatus -and $llmStatus.reachable) { $llmReachable = $true }
} catch {}

$hits1 = HasHits $search1
$hits2 = HasHits $search2

$ask = $askJson | ConvertFrom-Json
$answersCount = 0; $finalPresent = $false
try {
  if ($ask.answers) { $answersCount = $ask.answers.Count }
  if ($ask.final -and $ask.final.Trim().Length -gt 0) { $finalPresent = $true }
} catch {}

$inferred = "ok"
if (-not $apiHealthOk) { $inferred = "api_unhealthy" }
elseif (-not $workerOk) { $inferred = "worker_unhealthy" }
elseif ($uploadStatus -ne 200) { $inferred = "upload_failed" }
elseif (-not ($hits1 -or $hits2)) { $inferred = "search_empty" }
elseif ($llmReachable -and -not $finalPresent) { $inferred = "llm_expected_final_missing" }

$diag = @{}
if ($inferred -ne "ok") {
  $diag.apiBaseHint  = "Footer should show API: http://localhost:8082 when running via browser"
  $diag.tokens       = @{ api_prefix = $apiTokShort; worker_set = ([bool]$WORKER_TOKEN) }
  $diag.docker_ps    = (docker ps --format "{{.Names}}\t{{.Status}}")
  $diag.api_last     = (docker logs --tail=80 jsonify2ai-main-api-1 2>$null)
  $diag.worker_last  = (docker logs --tail=80 jsonify2ai-main-worker-1 2>$null)
}

$SMOKE_RESULT = [ordered]@{
  api_health_ok       = $apiHealthOk
  worker_status_ok    = $workerOk
  api_upload_ok       = ($uploadStatus -eq 200)
  search_hits_all     = ($hits1 -and $hits2)
  ask_answers         = $answersCount
  ask_final_present   = $finalPresent
  export_manifest_ok  = $exportOk
  qdrant_points       = $qdrantPoints
  inferred_issue      = $inferred
  diag                = $diag
}

$SMOKE_RESULT | ConvertTo-Json -Depth 5
