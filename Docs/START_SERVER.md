# 🚀 Quick Start Commands for Strategy Engine Server

## Option 1: Using PowerShell Script (Recommended)
```powershell
cd "C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine"
.\start_server.ps1
```

## Option 2: Direct Command (Manual)
```powershell
cd "C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine"
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Option 3: Using Python Directly (If venv not working)
```powershell
cd "C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## ✅ Verify Server is Running
Open a new terminal and run:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/" -Method GET
```

Expected response: `{"status":"ok"}`

## 📡 Server Endpoints
- Health Check: http://127.0.0.1:8000/
- API Docs: http://127.0.0.1:8000/docs
- WebSocket: ws://127.0.0.1:8000/auth/ws/live-prices
- AI Strategy: http://127.0.0.1:8000/auth/api/ai-strategy/generate

## 🛑 Stop Server
Press `CTRL+C` in the terminal where server is running
