#!/bin/bash

# RefServerLite - Development Environment Setup Script
# Sets up the development environment without Docker

set -e  # Exit on any error

echo "🔧 RefServerLite Development Environment Setup"
echo "=============================================="

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: Please run this script from the RefServerLite root directory"
    echo "   Expected to find requirements.txt in current directory"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "🐍 Python version: $PYTHON_VERSION"

if [ "$(echo "$PYTHON_VERSION < 3.8" | bc -l)" -eq 1 ]; then
    echo "❌ Error: Python 3.8+ required, found $PYTHON_VERSION"
    exit 1
fi

# Check if virtual environment is recommended
if [ -z "$VIRTUAL_ENV" ]; then
    echo ""
    echo "⚠️  WARNING: No virtual environment detected"
    echo "   It's recommended to use a virtual environment:"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate"
    echo ""
    read -p "Continue without virtual environment? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled. Please set up a virtual environment first."
        exit 1
    fi
fi

# Install system dependencies
echo "🏗️  Checking system dependencies..."

# Check for tesseract
if ! command -v tesseract &> /dev/null; then
    echo "📥 Installing Tesseract OCR..."
    if command -v apt &> /dev/null; then
        sudo apt update
        sudo apt install -y tesseract-ocr tesseract-ocr-eng build-essential python3-dev
    elif command -v yum &> /dev/null; then
        sudo yum install -y tesseract tesseract-langpack-eng gcc gcc-c++ python3-devel
    elif command -v brew &> /dev/null; then
        brew install tesseract
    else
        echo "❌ Error: Could not detect package manager"
        echo "   Please install tesseract-ocr manually"
        exit 1
    fi
else
    echo "✅ Tesseract OCR already installed"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Run the server: ./run_server.sh"
echo "2. Open browser: http://localhost:8000"
echo "3. Login with: admin / admin123"
echo ""