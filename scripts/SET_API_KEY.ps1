# Quick script to set OpenAI API key directly
param(
    [Parameter(Mandatory=$false)]
    [string]$ApiKey
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Set OpenAI API Key" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$envPath = Join-Path $PSScriptRoot ".env"

if (-not $ApiKey) {
    Write-Host "Enter your OpenAI API Key (starts with 'sk-'):" -ForegroundColor Yellow
    Write-Host "Get it from: https://platform.openai.com/api-keys" -ForegroundColor Cyan
    $ApiKey = Read-Host "API Key"
}

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    Write-Host "✗ No API key provided. Exiting." -ForegroundColor Red
    exit 1
}

if (-not $ApiKey.StartsWith("sk-")) {
    Write-Host "⚠ Warning: API key should start with 'sk-'" -ForegroundColor Yellow
    $continue = Read-Host "Continue anyway? (y/N)"
    if ($continue -ne "y" -and $continue -ne "Y") {
        exit 1
    }
}

# Read existing .env file or create new
$envContent = @()
if (Test-Path $envPath) {
    $envContent = Get-Content $envPath
}

# Update or add OPENAI_API_KEY
$updated = $false
$newContent = @()
foreach ($line in $envContent) {
    if ($line -match "^OPENAI_API_KEY=") {
        $newContent += "OPENAI_API_KEY=$ApiKey"
        $updated = $true
    } else {
        $newContent += $line
    }
}

if (-not $updated) {
    # Add it if not found
    $newContent += "OPENAI_API_KEY=$ApiKey"
}

# Write back to file
$newContent | Out-File -FilePath $envPath -Encoding utf8

Write-Host ""
Write-Host "✓ API key updated in .env file!" -ForegroundColor Green
Write-Host ""
Write-Host "⚠ IMPORTANT: Restart the server for changes to take effect!" -ForegroundColor Yellow
Write-Host ""
Write-Host "To restart:" -ForegroundColor Cyan
Write-Host "1. Stop the current server (CTRL+C)" -ForegroundColor White
Write-Host "2. Run: .\start_server.ps1" -ForegroundColor Green

