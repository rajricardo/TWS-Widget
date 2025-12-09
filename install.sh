#!/bin/bash

# Turbo Trader - Installation Script for macOS
# This script installs all required dependencies for running Turbo Trader

set -e  # Exit on any error

echo "=================================="
echo "Turbo Trader - Installation Script"
echo "=================================="
echo ""

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check for Node.js
echo "Checking for Node.js..."
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js is not installed${NC}"
    echo "Please install Node.js from https://nodejs.org/"
    echo "Required version: Node.js 16.x or higher"
    exit 1
fi

NODE_VERSION=$(node -v)
echo -e "${GREEN}✓ Node.js found: $NODE_VERSION${NC}"

# Check for npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}❌ npm is not installed${NC}"
    exit 1
fi

NPM_VERSION=$(npm -v)
echo -e "${GREEN}✓ npm found: $NPM_VERSION${NC}"
echo ""

# Check for Python 3
echo "Checking for Python 3..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed${NC}"
    echo "Please install Python 3.7 or higher from https://www.python.org/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✓ Python found: $PYTHON_VERSION${NC}"
echo ""

# Install Node.js dependencies
echo "=================================="
echo "Installing Node.js dependencies..."
echo "=================================="
npm install

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Node.js dependencies installed successfully${NC}"
else
    echo -e "${RED}❌ Failed to install Node.js dependencies${NC}"
    exit 1
fi
echo ""

#Check if virtual environment exists and is working
VENV_BROKEN=0
if [ -d "bin" ] && [ -f "bin/activate" ]; then
    echo "Checking existing virtual environment..."
    source bin/activate 2>/dev/null
    # Test if pip install actually works (this catches externally-managed-environment errors)
    if ! python3 -m pip install --dry-run --upgrade pip &>/dev/null; then
        echo -e "${YELLOW}⚠ Virtual environment appears broken, recreating...${NC}"
        VENV_BROKEN=1
        deactivate 2>/dev/null || true
    else
        echo -e "${GREEN}✓ Virtual environment found and working${NC}"
        deactivate
    fi
fi

# Create or recreate Python virtual environment
if [ ! -d "bin" ] || [ ! -f "bin/activate" ] || [ $VENV_BROKEN -eq 1 ]; then
    echo "=================================="
    echo "Creating Python virtual environment..."
    echo "=================================="
    
    # Remove broken virtual environment if it exists
    if [ $VENV_BROKEN -eq 1 ]; then
        rm -rf bin include lib pyvenv.cfg
    fi
    
    python3 -m venv .
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Virtual environment created${NC}"
    else
        echo -e "${RED}❌ Failed to create virtual environment${NC}"
        exit 1
    fi
    echo ""
fi

# Activate virtual environment and install Python dependencies
echo "=================================="
echo "Installing Python API dependencies..."
echo "=================================="

# Activate the virtual environment
source bin/activate

# Upgrade pip using python -m pip
echo "Upgrading pip..."
python3 -m pip install --upgrade pip

# Install requirements using python -m pip
pwd
echo "Installing ib-insync and pytz..."
python3 -m pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Python dependencies installed successfully${NC}"
else
    echo -e "${RED}❌ Failed to install Python dependencies${NC}"
    deactivate
    exit 1
fi

# Deactivate virtual environment
deactivate

echo ""
echo "=================================="
echo -e "${GREEN}✓ Installation Complete!${NC}"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Make sure TWS or IB Gateway is running"
echo "2. Run the application with: ./run.sh"
echo ""
