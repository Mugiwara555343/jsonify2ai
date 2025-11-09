[CmdletBinding()] param()

$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
& "$PSScriptRoot\ensure_tokens.ps1" | Out-Null
Push-Location "$PSScriptRoot\.."
docker compose up -d --build web api worker qdrant | Out-Null
# seed
$seed = "data/dropzone/smoke_readme.md"
if (-not (Test-Path $seed)) { New-Item -Force -ItemType Directory data/dropzone | Out-Null; "Qdrant is used for vector search." | Set-Content $seed }
# verify
python scripts/ingest_diagnose.py | Write-Output
Pop-Location
