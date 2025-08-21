New-Item -ItemType Directory -Force -Path data/dropzone | Out-Null
New-Item -ItemType Directory -Force -Path data/exports | Out-Null
$env:EMBED_DEV_MODE="1"; $env:AUDIO_DEV_MODE="1"; $env:PYTHONPATH="worker"
Write-Host "Place your resume (pdf/docx/txt) into data\dropzone and press Enter"; Read-Host | Out-Null
python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/resume.jsonl
python examples/ask_local.py --q "What roles does this resume target?" --k 6 --show-sources
