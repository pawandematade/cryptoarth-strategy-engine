#!/bin/bash
# Production Server Startup Script for AWS/Linux
# Usage: ./start_production.sh

echo "========================================"
echo "  CryptoArth Strategy Engine (Production)"
echo "========================================"
echo ""

# Check if virtual environment exists
if [ ! -f "venv/bin/activate" ]; then
    echo "Error: Virtual environment not found!"
    echo "Please create a virtual environment first:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found!"
    echo "Please create a .env file with your configuration"
    echo ""
fi

# Check if PM2 is installed
if command -v pm2 &> /dev/null; then
    echo "Starting server with PM2..."
    pm2 start "uvicorn app.main:app --host 0.0.0.0 --port 8000" --name strategy-engine
    pm2 save
    echo ""
    echo "Server started with PM2!"
    echo "View logs: pm2 logs strategy-engine"
    echo "View status: pm2 status"
else
    echo "PM2 not found. Starting server directly..."
    echo "Server will be available at: http://0.0.0.0:8000"
    echo "Press CTRL+C to stop the server"
    echo ""
    uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
