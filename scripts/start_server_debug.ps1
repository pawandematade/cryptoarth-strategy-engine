# Strategy Engine Server Startup Script with Debug Output
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting Strategy Engine Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check virtual environment
if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "ERROR: Virtual environment not found!" -ForegroundColor Red
    exit 1
}

# Check .env file
if (-not (Test-Path ".\.env")) {
    Write-Host "WARNING: .env file not found!" -ForegroundColor Yellow
}

Write-Host "Python path: .\venv\Scripts\python.exe" -ForegroundColor Cyan
Write-Host "Starting server on: http://0.0.0.0:8000" -ForegroundColor Green
Write-Host "API will be available at: http://localhost:8000" -ForegroundColor Green
Write-Host "API Docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "Press CTRL+C to stop" -ForegroundColor Yellow
Write-Host ""

# Start with verbose output
$env:PYTHONUNBUFFERED = "1"
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug

