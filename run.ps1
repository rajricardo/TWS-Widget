# Turbo Trader - Launch Script for Windows
# This script activates the Python virtual environment and launches the Electron app

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "   Turbo Trader - Starting App" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment exists
if ((-not (Test-Path "Scripts")) -or (-not (Test-Path "Scripts\activate.ps1"))) {
    Write-Host "❌ Virtual environment not found" -ForegroundColor Red
    Write-Host "Please run .\install.ps1 first to set up dependencies" -ForegroundColor Red
    exit 1
}

# Check if node_modules exists
if (-not (Test-Path "node_modules")) {
    Write-Host "❌ Node modules not found" -ForegroundColor Red
    Write-Host "Please run .\install.ps1 first to set up dependencies" -ForegroundColor Red
    exit 1
}

# Activate Python virtual environment
Write-Host "Activating Python virtual environment..." -ForegroundColor Yellow

try {
    & ".\Scripts\activate.ps1"
    Write-Host "✓ Virtual environment activated" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to activate virtual environment" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Starting Turbo Trader..." -ForegroundColor Cyan
Write-Host ""

# Launch the Electron app
npm start

# Deactivate virtual environment when app closes
deactivate
