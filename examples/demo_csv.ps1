New-Item -ItemType Directory -Force -Path data/dropzone | Out-Null
New-Item -ItemType Directory -Force -Path data/exports | Out-Null
$env:EMBED_DEV_MODE="1"; $env:PYTHONPATH="worker"
Set-Content -Path data/dropzone/pay.csv -Value "name,dept,salary`nalice,eng,140000`nbob,ops,90000"
python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/csv.jsonl
python examples/ask_local.py --q "Summarize departments and salaries present." --k 6 --show-sources
