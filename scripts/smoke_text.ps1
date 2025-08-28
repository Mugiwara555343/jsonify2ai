$ErrorActionPreference = "Stop"
Write-Host 'Running API upload smoke test...'
$env:PORT_API = $env:PORT_API -or 8082
curl.exe -F 'file=@.\README.md' "http://localhost:$env:PORT_API/upload"
Write-Host ' running worker process/text smoke test...'
$env:PORT_WORKER = $env:PORT_WORKER -or 8090
curl.exe -X POST "http://localhost:$env:PORT_WORKER/process/text" `
  -H "Content-Type: application/json" `
  -d "{\"document_id\":\"00000000-0000-0000-0000-000000000000\",\"text\":\"hello world\"}"
