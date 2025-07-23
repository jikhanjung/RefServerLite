#!/bin/bash

# RefServerLite - Native Server Startup Script
# Runs the server without Docker for faster development

set -e  # Exit on any error

echo "🚀 Starting RefServerLite (Native Mode)..."

# Check if we're in the right directory
if [ ! -f "app/main.py" ]; then
    echo "❌ Error: Please run this script from the RefServerLite root directory"
    echo "   Expected to find app/main.py in current directory"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "🐍 Using Python $PYTHON_VERSION"

# Check if tesseract is installed
if ! command -v tesseract &> /dev/null; then
    echo "❌ Error: Tesseract OCR is not installed"
    echo "   Please install it with: sudo apt install tesseract-ocr tesseract-ocr-eng"
    exit 1
fi
echo "✅ Tesseract OCR found: $(tesseract --version | head -1)"

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Warning: No virtual environment detected"
    echo "   Consider activating a virtual environment first"
fi

# Create data and log directories
echo "📁 Creating data and log directories..."
mkdir -p refdata/pdfs refdata/chromadb logs
echo "✅ Data and log directories created"

# Check if dependencies are installed
echo "📦 Checking Python dependencies..."
python3 -c "import fastapi, uvicorn, peewee, chromadb" 2>/dev/null || {
    echo "❌ Error: Required Python packages not installed"
    echo "   Run: pip install -r requirements.txt"
    exit 1
}
echo "✅ Required packages found"

# Run database migrations
echo "🗄️  Running database migrations..."
python3 -m peewee_migrate migrate --database sqlite:///refdata/refserver.db --directory migrations
echo "✅ Database migrations completed"

# Initialize database (create admin user if needed)
echo "👤 Initializing database..."
python3 -c "from app.models import init_database; init_database('refdata/refserver.db')"
echo "✅ Database initialized"

# Set Python path
export PYTHONPATH=$(pwd)
echo "🔧 PYTHONPATH set to: $PYTHONPATH"

# Kill any existing server on port 8000
echo "🔍 Checking for existing server on port 8000..."
if lsof -ti:8000 >/dev/null 2>&1; then
    echo "⚠️  Found existing server on port 8000, stopping it..."
    pkill -f "uvicorn.*app.main:app" || true
    sleep 2
fi

echo ""
echo "🎉 Starting RefServerLite server..."
echo "📍 Server will be available at: http://localhost:8000"
echo "👤 Default admin login: admin / admin123"
echo "📝 Server logs will be saved to: logs/server.log"
echo ""
echo "Press Ctrl+C to stop the server"
echo "----------------------------------------"

# Start the server with logging
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload 2>&1 | tee logs/server.log