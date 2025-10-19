# Test script for authentication
Write-Host "Testing API authentication..."

# Test 1: Without token (should work if no auth token is set)
Write-Host "`n1. Testing /status without token (should work):"
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8082/status" -UseBasicParsing
    Write-Host "Status: $($response.StatusCode)"
    Write-Host "Response: $($response.Content)"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}

# Test 2: With token (if auth is enabled)
Write-Host "`n2. Testing /search without token (should fail if auth enabled):"
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8082/search?q=test" -UseBasicParsing
    Write-Host "Status: $($response.StatusCode)"
    Write-Host "Response: $($response.Content)"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}

# Test 3: With token (if auth is enabled)
Write-Host "`n3. Testing /search with token (should work if auth enabled):"
try {
    $headers = @{ "Authorization" = "Bearer test-token" }
    $response = Invoke-WebRequest -Uri "http://localhost:8082/search?q=test" -Headers $headers -UseBasicParsing
    Write-Host "Status: $($response.StatusCode)"
    Write-Host "Response: $($response.Content)"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}
