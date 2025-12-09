# Turbo Trader - Installation Script for Windows
# This script installs all required dependencies for running Turbo Trader

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "Turbo Trader - Installation Script" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Check for Node.js
Write-Host "Checking for Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node -v
    Write-Host "✓ Node.js found: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js is not installed" -ForegroundColor Red
    Write-Host "Please install Node.js from https://nodejs.org/" -ForegroundColor Red
    Write-Host "Required version: Node.js 16.x or higher" -ForegroundColor Red
    exit 1
}

# Check for npm
try {
    $npmVersion = npm -v
    Write-Host "✓ npm found: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ npm is not installed" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Check for Python 3
Write-Host "Checking for Python 3..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python 3 is not installed" -ForegroundColor Red
    Write-Host "Please install Python 3.7 or higher from https://www.python.org/" -ForegroundColor Red
    Write-Host "Make sure to check 'Add Python to PATH' during installation" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Install Node.js dependencies
Write-Host "==================================" -ForegroundColor Cyan
Write-Host "Installing Node.js dependencies..." -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
npm install

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Node.js dependencies installed successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to install Node.js dependencies" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Check if virtual environment exists and is working
$venvBroken = $false
if ((Test-Path "Scripts") -and (Test-Path "Scripts\activate.ps1")) {
    Write-Host "Checking existing virtual environment..." -ForegroundColor Yellow
    try {
        & ".\Scripts\activate.ps1"
        # Test if pip install actually works
        $testInstall = python -m pip install --dry-run --upgrade pip 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "⚠ Virtual environment appears broken, recreating..." -ForegroundColor Yellow
            $venvBroken = $true
            deactivate
        } else {
            Write-Host "✓ Virtual environment found and working" -ForegroundColor Green
            deactivate
        }
    } catch {
        $venvBroken = $true
    }
}

# Create or recreate Python virtual environment
if ((-not (Test-Path "Scripts")) -or (-not (Test-Path "Scripts\activate.ps1")) -or $venvBroken) {
    Write-Host "==================================" -ForegroundColor Cyan
    Write-Host "Creating Python virtual environment..." -ForegroundColor Cyan
    Write-Host "==================================" -ForegroundColor Cyan
    
    # Remove broken virtual environment if it exists
    if ($venvBroken) {
        Remove-Item -Recurse -Force Scripts, Lib, Include, pyvenv.cfg -ErrorAction SilentlyContinue
    }
    
    python -m venv .
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Virtual environment created" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

# Activate virtual environment and install Python dependencies
Write-Host "==================================" -ForegroundColor Cyan
Write-Host "Installing Python API dependencies..." -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan

# Activate the virtual environment
& ".\Scripts\activate.ps1"

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install requirements
Write-Host "Installing ib-insync and pytz..." -ForegroundColor Yellow
python -m pip install -r requirements.txt

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Python dependencies installed successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to install Python dependencies" -ForegroundColor Red
    deactivate
    exit 1
}

# Deactivate virtual environment
deactivate

Write-Host ""
Write-Host "==================================" -ForegroundColor Cyan
Write-Host "✓ Installation Complete!" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Make sure TWS or IB Gateway is running"
Write-Host "2. Run the application with: .\run.ps1"
Write-Host ""
