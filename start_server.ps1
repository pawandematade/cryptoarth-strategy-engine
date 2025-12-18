# Strategy Engine Server Startup Script
# This script starts the FastAPI server for the Strategy Engine

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CryptoArth Strategy Engine Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment exists
if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "Error: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please create a virtual environment first:" -ForegroundColor Yellow
    Write-Host "  python -m venv venv" -ForegroundColor Yellow
    Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host "  pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

# Check if .env file exists
if (-not (Test-Path ".\.env")) {
    Write-Host "Warning: .env file not found!" -ForegroundColor Yellow
    Write-Host "Please create a .env file with your configuration:" -ForegroundColor Yellow
    Write-Host "  OPENAI_API_KEY=your_key_here" -ForegroundColor Yellow
    Write-Host "  OPENAI_MODEL=gpt-4o-mini" -ForegroundColor Yellow
    Write-Host ""
} else {
    # Check if OpenAI API key is set
    $envContent = Get-Content ".\.env" -ErrorAction SilentlyContinue
    if ($envContent -notmatch "OPENAI_API_KEY") {
        Write-Host "Warning: OPENAI_API_KEY not found in .env file!" -ForegroundColor Yellow
        Write-Host "AI Strategy Builder will not work without an API key." -ForegroundColor Yellow
        Write-Host ""
    }
}

# Check if required Python packages are installed
Write-Host "Checking dependencies..." -ForegroundColor Cyan
$missingPackages = @()
$requiredPackages = @("fastapi", "uvicorn", "openai", "redis", "websocket", "requests", "python-dotenv")
foreach ($package in $requiredPackages) {
    $result = .\venv\Scripts\python.exe -c "import $package" 2>&1
    if ($LASTEXITCODE -ne 0) {
        $missingPackages += $package
    }
}
if ($missingPackages.Count -gt 0) {
    Write-Host "Installing missing packages: $($missingPackages -join ', ')" -ForegroundColor Yellow
    .\venv\Scripts\python.exe -m pip install $missingPackages
}

Write-Host "Starting Strategy Engine server..." -ForegroundColor Green
Write-Host "Server will be available at: http://localhost:8000" -ForegroundColor Cyan
Write-Host "API Documentation: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press CTRL+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Start the server
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

