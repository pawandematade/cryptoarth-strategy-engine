# Strategy Engine Server Restart Script
# This script stops and restarts the FastAPI server

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Restarting Strategy Engine Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to project directory
$projectPath = "C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine"
Set-Location $projectPath

# Stop any running Python processes related to uvicorn
Write-Host "Stopping existing server processes..." -ForegroundColor Yellow
$processes = Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*uvicorn*" -or $_.Path -like "*venv*"
}
if ($processes) {
    $processes | Stop-Process -Force
    Write-Host "Stopped $($processes.Count) process(es)" -ForegroundColor Green
    Start-Sleep -Seconds 2
} else {
    Write-Host "No running server processes found" -ForegroundColor Gray
}

# Clear Python cache (optional)
Write-Host "Clearing Python cache..." -ForegroundColor Yellow
Get-ChildItem -Path "app" -Recurse -Filter "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path "app" -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Cache cleared" -ForegroundColor Green

# Check if virtual environment exists
if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "Error: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please create a virtual environment first:" -ForegroundColor Yellow
    Write-Host "  python -m venv venv" -ForegroundColor Yellow
    Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host "  pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

# Start the server
Write-Host ""
Write-Host "Starting Strategy Engine server..." -ForegroundColor Green
Write-Host "Server will be available at: http://localhost:8000" -ForegroundColor Cyan
Write-Host "API Documentation: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press CTRL+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Start the server
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
