# Quick script to check if the Strategy Engine server is running

Write-Host "Checking Strategy Engine server status..." -ForegroundColor Cyan
Write-Host ""

$baseUrl = "http://localhost:8000"

try {
    $response = Invoke-WebRequest -Uri "$baseUrl/" -TimeoutSec 5 -UseBasicParsing
    
    if ($response.StatusCode -eq 200) {
        Write-Host "✓ Server is RUNNING!" -ForegroundColor Green
        Write-Host "  Status Code: $($response.StatusCode)" -ForegroundColor Green
        Write-Host "  Response: $($response.Content)" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Server URLs:" -ForegroundColor Yellow
        Write-Host "  - Health: $baseUrl/" -ForegroundColor Cyan
        Write-Host "  - API Docs: $baseUrl/docs" -ForegroundColor Cyan
        Write-Host "  - AI Strategy: $baseUrl/auth/ai-strategy/generate" -ForegroundColor Cyan
        exit 0
    }
} catch {
    Write-Host "✗ Server is NOT running or not accessible" -ForegroundColor Red
    Write-Host ""
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "To start the server, run:" -ForegroundColor Yellow
    Write-Host "  .\start_server.ps1" -ForegroundColor Cyan
    Write-Host "  OR" -ForegroundColor Yellow
    Write-Host "  .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" -ForegroundColor Cyan
    exit 1
}

