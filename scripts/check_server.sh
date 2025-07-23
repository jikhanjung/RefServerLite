#!/bin/bash

# RefServerLite - Server Status Check Script
# Checks if the server is running and healthy

echo "🔍 RefServerLite Server Status Check"
echo "===================================="

# Check if uvicorn process is running
PIDS=$(pgrep -f "uvicorn.*app.main:app" 2>/dev/null || true)

if [ -z "$PIDS" ]; then
    echo "❌ Server process: NOT RUNNING"
    echo ""
    echo "To start the server:"
    echo "  scripts/run_server.sh"
    exit 1
else
    echo "✅ Server process: RUNNING (PID: $PIDS)"
fi

# Check if port 8000 is listening
if lsof -i:8000 >/dev/null 2>&1; then
    echo "✅ Port 8000: LISTENING"
else
    echo "❌ Port 8000: NOT LISTENING"
fi

# Test HTTP response
echo "🌐 Testing HTTP connection..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ 2>/dev/null || echo "ERROR")

if [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ HTTP response: OK (200)"
elif [ "$HTTP_STATUS" = "ERROR" ]; then
    echo "❌ HTTP response: CONNECTION FAILED"
else
    echo "⚠️  HTTP response: $HTTP_STATUS"
fi

# Check database file
if [ -f "refdata/refserver.db" ]; then
    DB_SIZE=$(stat -c%s "refdata/refserver.db" 2>/dev/null || echo "0")
    echo "✅ Database: EXISTS (${DB_SIZE} bytes)"
else
    echo "❌ Database: NOT FOUND"
fi

# Check ChromaDB directory
if [ -d "refdata/chromadb" ]; then
    CHROMA_FILES=$(find refdata/chromadb -type f | wc -l)
    echo "✅ ChromaDB: EXISTS ($CHROMA_FILES files)"
else
    echo "❌ ChromaDB: NOT FOUND"
fi

# Show recent log entries if server.log exists
if [ -f "logs/server.log" ]; then
    echo ""
    echo "📝 Recent server logs (last 5 lines):"
    echo "------------------------------------"
    tail -5 logs/server.log
elif [ -f "server.log" ]; then
    echo ""
    echo "📝 Recent server logs (last 5 lines) - old location:"
    echo "------------------------------------"
    tail -5 server.log
fi

echo ""
echo "Server URL: http://localhost:8000"
echo "Admin login: admin / admin123"