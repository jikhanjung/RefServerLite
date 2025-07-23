#!/bin/bash

# RefServerLite - Server Stop Script
# Stops the running server gracefully

echo "🛑 Stopping RefServerLite server..."

# Find and kill uvicorn processes
PIDS=$(pgrep -f "uvicorn.*app.main:app" 2>/dev/null || true)

if [ -z "$PIDS" ]; then
    echo "ℹ️  No RefServerLite server process found"
else
    echo "🔍 Found server process(es): $PIDS"
    
    # Send SIGTERM first (graceful shutdown)
    kill $PIDS 2>/dev/null || true
    
    # Wait up to 10 seconds for graceful shutdown
    for i in {1..10}; do
        if ! pgrep -f "uvicorn.*app.main:app" > /dev/null; then
            echo "✅ Server stopped gracefully"
            exit 0
        fi
        sleep 1
    done
    
    # Force kill if still running
    echo "⚠️  Server didn't stop gracefully, forcing shutdown..."
    pkill -9 -f "uvicorn.*app.main:app" 2>/dev/null || true
    
    if ! pgrep -f "uvicorn.*app.main:app" > /dev/null; then
        echo "✅ Server stopped (forced)"
    else
        echo "❌ Failed to stop server"
        exit 1
    fi
fi

# Show log file locations
if [ -f "logs/server.log" ]; then
    echo "📝 Server log available in: logs/server.log"
elif [ -f "server.log" ]; then
    echo "📝 Server log available in: server.log (old location)"
fi