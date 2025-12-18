# Script to help create .env file
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Create .env File for Strategy Engine" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$envPath = Join-Path $PSScriptRoot ".env"

if (Test-Path $envPath) {
    Write-Host ".env file already exists!" -ForegroundColor Yellow
    Write-Host "Location: $envPath" -ForegroundColor Cyan
    Write-Host ""
    $overwrite = Read-Host "Do you want to overwrite it? (y/N)"
    if ($overwrite -ne "y" -and $overwrite -ne "Y") {
        Write-Host "Cancelled. Existing .env file preserved." -ForegroundColor Yellow
        exit 0
    }
}

Write-Host "Creating .env file..." -ForegroundColor Green
Write-Host ""

# Get OpenAI API Key
Write-Host "Enter your OpenAI API Key (starts with 'sk-'):" -ForegroundColor Yellow
Write-Host "You can get it from: https://platform.openai.com/api-keys" -ForegroundColor Cyan
$apiKey = Read-Host "OPENAI_API_KEY"

if ([string]::IsNullOrWhiteSpace($apiKey)) {
    Write-Host "No API key provided. Using placeholder." -ForegroundColor Yellow
    $apiKey = "your_openai_api_key_here"
}

# Create .env content
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$envLines = @(
    "# Strategy Engine Environment Variables",
    "# Generated on $timestamp",
    "",
    "# OpenAI API Configuration (REQUIRED for AI Strategy Builder)",
    "OPENAI_API_KEY=$apiKey",
    "OPENAI_MODEL=gpt-4o-mini",
    "",
    "# Delta Exchange API Configuration",
    "DELTA_BASE_URL=https://api.india.delta.exchange",
    "",
    "# Redis Configuration",
    "REDIS_HOST=localhost",
    "REDIS_PORT=6379",
    "",
    "# Application Environment",
    "APP_ENV=development"
)

$envLines | Out-File -FilePath $envPath -Encoding utf8 -ErrorAction Stop

Write-Host ""
Write-Host ".env file created successfully!" -ForegroundColor Green
Write-Host "Location: $envPath" -ForegroundColor Cyan
Write-Host ""

if ($apiKey -eq "your_openai_api_key_here") {
    Write-Host "Remember to edit .env and add your actual OpenAI API key!" -ForegroundColor Yellow
} else {
    Write-Host "OpenAI API key added!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Restart the server (if it's running)" -ForegroundColor White
    Write-Host "2. Try generating a strategy in the AI Builder" -ForegroundColor White
}

