#!/bin/bash
# Restart script for CryptoArth FastAPI backend
# Ensures uvicorn stays alive with proper logging

# Get script directory (works even when called from elsewhere)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Default paths (can be overridden by environment)
VENV_DIR="${VENV_DIR:-venv}"
LOG_FILE="${LOG_FILE:-uvicorn.log}"
PYTHON_BIN="$VENV_DIR/bin/python"

# Check if virtual environment exists
if [ ! -f "$PYTHON_BIN" ]; then
    echo "Error: Virtual environment not found at $VENV_DIR"
    echo "Expected Python binary: $PYTHON_BIN"
    exit 1
fi

# Kill any existing uvicorn processes for this app
echo "Stopping existing uvicorn processes..."
pkill -f "uvicorn app.main:app" || true
sleep 2

# Check if port is still in use
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Warning: Port 8000 is still in use. Attempting to kill..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Load environment variables if .env file exists
if [ -f ".env.production" ]; then
    echo "Loading .env.production..."
    export $(grep -v '^#' .env.production | xargs)
elif [ -f ".env.local" ]; then
    echo "Loading .env.local..."
    export $(grep -v '^#' .env.local | xargs)
elif [ -f ".env" ]; then
    echo "Loading .env..."
    export $(grep -v '^#' .env | xargs)
fi

# Start uvicorn with nohup in background
echo "Starting uvicorn backend..."
echo "Working directory: $SCRIPT_DIR"
echo "Python: $PYTHON_BIN"
echo "Log file: $LOG_FILE"
echo ""

# Use nohup to ensure process stays alive after script exits
# Redirect both stdout and stderr to log file
# Run in background with &
nohup "$PYTHON_BIN" -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    > "$LOG_FILE" 2>&1 &

# Get the process ID
UVICORN_PID=$!

# Wait a moment to check if process started successfully
sleep 2

# Check if process is still running
if ps -p $UVICORN_PID > /dev/null 2>&1; then
    echo "✅ Backend started successfully"
    echo "   PID: $UVICORN_PID"
    echo "   Log file: $LOG_FILE"
    echo "   Health check: curl http://127.0.0.1:8000/health"
    echo ""
    echo "To view logs: tail -f $LOG_FILE"
    echo "To check process: ps aux | grep uvicorn"
else
    echo "❌ Backend failed to start"
    echo "   Check log file for errors: $LOG_FILE"
    if [ -f "$LOG_FILE" ]; then
        echo ""
        echo "Last 20 lines of log:"
        tail -20 "$LOG_FILE"
    fi
    exit 1
fi

