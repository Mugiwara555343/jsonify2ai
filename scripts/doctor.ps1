# INTERNAL: dev helper, not part of public demo surface
# doctor.ps1 — quick diagnostics for common breakages
$ErrorActionPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest

function Ping-Url($u){ try{ (Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 4).StatusCode }catch{ 0 } }

$S=@{}
$S.Docker = (docker info | Out-Null; $LASTEXITCODE -eq 0)
$S.Api    = (Ping-Url "http://localhost:8082/health/full") -eq 200
$S.Worker = (Ping-Url "http://localhost:8090/status") -eq 200
$S.Web    = (Ping-Url "http://localhost:5173") -eq 200
$S.Qdrant = (Ping-Url "http://localhost:6333/readyz") -eq 200
$S.Ollama = (Ping-Url "http://localhost:11434/api/tags") -eq 200
$S | Format-List
Write-Host "`nTip: If API/Worker are red, run scripts/start_all.ps1" -ForegroundColor Yellow
