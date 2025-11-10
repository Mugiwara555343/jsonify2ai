<#
Verify env + reachability + ingest/search/ask (pure PowerShell)

What this script does:
1) Loads .env (non-destructive; does not echo secrets).
2) Restarts the worker so new envs apply.
3) From inside the worker: checks OLLAMA_HOST reachability and prints EMBED_DEV_MODE/EMBEDDINGS_MODEL.
4) Ensures 3 seed files exist; processes them via /process/text (authorized).
5) Verifies:
   - worker /status shows chunks >= 3
   - API /search returns hits for 3 probes
   - API /ask returns answers_count > 0 and final_present when Ollama reachable
6) Prints a concise summary block.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Load-DotEnv {
    param([string]$Path = ".env")
    if (-not (Test-Path $Path)) { return @{} }
    $ht = @{}
    Get-Content -Raw $Path -Encoding UTF8 | ForEach-Object {
        $_ -split "`n"
    } | ForEach-Object {
        $line = $_.Trim()
        if (-not $line) { return }
        if ($line.StartsWith('#')) { return }
        # support KEY="value with = and spaces"
        if ($line -match '^\s*([^=]+)\s*=\s*(.*)\s*$') {
            $k = $matches[1].Trim()
            $vRaw = $matches[2]
            if ($vRaw.StartsWith('"') -and $vRaw.EndsWith('"')) {
                $v = $vRaw.Trim('"')
            } elseif ($vRaw.StartsWith("'") -and $vRaw.EndsWith("'")) {
                $v = $vRaw.Trim("'")
            } else {
                $v = $vRaw
            }
            $ht[$k] = $v
        }
    }
    return $ht
}

function Post-Json {
    param(
        [string]$Url,
        [hashtable]$Body,
        [hashtable]$Headers
    )
    $json = ($Body | ConvertTo-Json -Depth 6 -Compress)
    Invoke-RestMethod -Method Post -Uri $Url -Headers $Headers -ContentType 'application/json' -Body $json
}

# 0) Load tokens from .env if not already set in the session
$envMap = Load-DotEnv ".env"
if (-not $env:WORKER_AUTH_TOKEN -and $envMap.ContainsKey('WORKER_AUTH_TOKEN')) { $env:WORKER_AUTH_TOKEN = $envMap['WORKER_AUTH_TOKEN'] }
if (-not $env:API_AUTH_TOKEN    -and $envMap.ContainsKey('API_AUTH_TOKEN'))    { $env:API_AUTH_TOKEN    = $envMap['API_AUTH_TOKEN']    }

# 1) Restart worker to pick env changes
Write-Host ">> Restarting worker..." -ForegroundColor Cyan
docker compose up -d worker | Out-Null

# 2) Inside-container diagnostics (Ollama reachability + embed flags)
$pyLines = @(
    'import os, requests, sys'
    'host = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")'
    'print("OLLAMA_HOST=", host)'
    'try:'
    '    r = requests.get(host.rstrip("/") + "/api/tags", timeout=5)'
    '    print("OLLAMA_REACHABILITY=OK", r.status_code)'
    'except Exception as e:'
    '    print("OLLAMA_REACHABILITY=FAIL", e)'
    'print("EMBED_DEV_MODE=", os.getenv("EMBED_DEV_MODE"))'
    'print("EMBEDDINGS_MODEL=", os.getenv("EMBEDDINGS_MODEL"))'
)
$pyScript = $pyLines -join "`n"
$diag = $pyScript | docker exec -i jsonify2ai-main-worker-1 python -
Write-Host $diag

# 3) Ensure seed files exist
$seedDir = "data/dropzone"
if (-not (Test-Path $seedDir)) { New-Item -ItemType Directory -Path $seedDir | Out-Null }

$seed1 = Join-Path $seedDir "seed_qdrant.md"
$seed2 = Join-Path $seedDir "seed_export.md"
$seed3 = Join-Path $seedDir "seed_env.md"

if (-not (Test-Path $seed1)) { @"
Qdrant is the vector database used by this project for semantic search (768-dim embeddings, cosine distance).
"@ | Set-Content -NoNewline -Path $seed1 -Encoding UTF8 }

if (-not (Test-Path $seed2)) { @"
Export ZIPs include a manifest.json alongside chunks.jsonl or images.jsonl and any source files under source/.
"@ | Set-Content -NoNewline -Path $seed2 -Encoding UTF8 }

if (-not (Test-Path $seed3)) { @"
Dev toggles include EMBED_DEV_MODE and AUDIO_DEV_MODE for lightweight runs.
"@ | Set-Content -NoNewline -Path $seed3 -Encoding UTF8 }

# 4) Process seeds via worker (authorized)
if (-not $env:WORKER_AUTH_TOKEN) {
    Write-Warning "WORKER_AUTH_TOKEN not found; skipping seed processing calls."
} else {
    $wh = @{ Authorization = "Bearer $($env:WORKER_AUTH_TOKEN)" }
    Post-Json -Url "http://localhost:8090/process/text" -Headers $wh -Body @{ path = "data/dropzone/seed_qdrant.md" } | Out-Null
    Post-Json -Url "http://localhost:8090/process/text" -Headers $wh -Body @{ path = "data/dropzone/seed_export.md" } | Out-Null
    Post-Json -Url "http://localhost:8090/process/text" -Headers $wh -Body @{ path = "data/dropzone/seed_env.md" }    | Out-Null
}

Start-Sleep -Seconds 3

# 5) Status + searches
$status = Invoke-RestMethod -Uri "http://localhost:8090/status" -Method Get
$counts = $status.counts

function Get-Hit { param([string]$q)
    try {
        $uri = "http://localhost:8082/search?kind=text&q="+[uri]::EscapeDataString($q)+"&limit=5"
        if ($env:API_AUTH_TOKEN) {
            $r = Invoke-RestMethod -Uri $uri -Method Get -Headers @{ Authorization = "Bearer $($env:API_AUTH_TOKEN)" }
        } else {
            $r = Invoke-RestMethod -Uri $uri -Method Get
        }
        if ($null -eq $r -or $null -eq $r.results) { return $false }
        return ($r.results.Count -gt 0)
    } catch { return $false }
}

$hitVector   = Get-Hit "vector"
$hitManifest = Get-Hit "manifest.json"
$hitEmbed    = Get-Hit "EMBED_DEV_MODE"

# 6) Ask
$answersCount = "N/A"; $finalPresent = "N/A"
if ($env:API_AUTH_TOKEN) {
    $ah = @{ Authorization = "Bearer $($env:API_AUTH_TOKEN)" }
    $askBody = @{ kind = "text"; q = "What is Qdrant used for in this repo?"; limit = 3 }
    try {
        $ask = Post-Json -Url "http://localhost:8082/ask" -Headers $ah -Body $askBody
        if ($ask) {
            # Ask endpoint returns 'sources' not 'answers'
            if ($ask.sources) {
                $answersCount = ($ask.sources | Measure-Object).Count
            } elseif ($ask.answers) {
                $answersCount = ($ask.answers | Measure-Object).Count
            } else {
                $answersCount = 0
            }
            # Check for 'final' field (added by LLM synthesis) or 'answer' field
            $hasFinal = $ask.PSObject.Properties.Name -contains 'final' -and -not [string]::IsNullOrEmpty($ask.final)
            $hasAnswer = $ask.PSObject.Properties.Name -contains 'answer' -and -not [string]::IsNullOrEmpty($ask.answer)
            $finalPresent = $hasFinal -or $hasAnswer
        } else {
            $answersCount = 0
            $finalPresent = $false
        }
    } catch {
        Write-Host "Ask error: $_" -ForegroundColor Yellow
        $answersCount = "ERR"
        $finalPresent = "ERR"
    }
}

# 7) Summary
Write-Host ""
Write-Host "==== SUMMARY ====" -ForegroundColor Yellow
# parse the diag for reachability line
$reachLine = ($diag -split "`r?`n") | Where-Object { $_ -like "OLLAMA_REACHABILITY=*" } | Select-Object -First 1
$hostLine  = ($diag -split "`r?`n") | Where-Object { $_ -like "OLLAMA_HOST=*" } | Select-Object -First 1
$devLine   = ($diag -split "`r?`n") | Where-Object { $_ -like "EMBED_DEV_MODE=*" } | Select-Object -First 1

Write-Host $hostLine
Write-Host $reachLine
Write-Host $devLine
Write-Host ("counts: chunks={0} images={1} total={2}" -f $counts.chunks, $counts.images, $counts.total)
Write-Host ("search_hits: vector={0} manifest.json={1} EMBED_DEV_MODE={2}" -f $hitVector, $hitManifest, $hitEmbed)
Write-Host ("ask: answers_count={0} final_present={1}" -f $answersCount, $finalPresent)
