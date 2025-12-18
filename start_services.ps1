# Start all services in separate windows
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting CryptoArth Services" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Starting API Server..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

Start-Sleep -Seconds 2

Write-Host "Starting Delta WebSocket Feed..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; .\venv\Scripts\python.exe -m app.feed.delta_ws_live"

Start-Sleep -Seconds 2

Write-Host "Starting Strategy Engine..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; .\venv\Scripts\python.exe -m app.engine.engine"

Write-Host ""
Write-Host "All services started in separate windows:" -ForegroundColor Yellow
Write-Host "  - API Server: http://localhost:8000" -ForegroundColor Cyan
Write-Host "  - WebSocket Feed: Running" -ForegroundColor Cyan
Write-Host "  - Strategy Engine: Running" -ForegroundColor Cyan
Write-Host ""
Write-Host "Close individual windows to stop specific services." -ForegroundColor Yellow

