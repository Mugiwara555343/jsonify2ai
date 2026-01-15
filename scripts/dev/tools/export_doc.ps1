param(
  [Parameter(Mandatory = $true)] [string]$DocId,
  [string]$Collection = ""
)

$base = "http://localhost:8082/export?document_id=$DocId"
if ($Collection -ne "") { $base += "&collection=$Collection" }

# ensure exports dir exists at repo root
$destDir = Join-Path -Path (Get-Location) -ChildPath "exports"
if (!(Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir | Out-Null }

$outFile = Join-Path $destDir ("export_" + $DocId + ".jsonl")

Invoke-WebRequest $base -OutFile $outFile
Write-Host "Saved -> $outFile"
