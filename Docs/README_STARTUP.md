# Strategy Engine Startup Guide

## Quick Start

### Option 1: PowerShell Script (Recommended for Windows)
```powershell
.\start_server.ps1
```

### Option 2: Batch File
```cmd
start_server.bat
```

### Option 3: Manual Start
```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Prerequisites

1. **Virtual Environment**: Make sure you have activated the virtual environment
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

2. **Dependencies**: Install all required packages
   ```powershell
   pip install -r requirements.txt
   ```

3. **Environment Variables**: Create a `.env` file in the project root:
   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   OPENAI_MODEL=gpt-4o-mini
   DELTA_BASE_URL=https://api.india.delta.exchange
   REDIS_HOST=localhost
   REDIS_PORT=6379
   ```

## Verify Server is Running

1. **Health Check**: Open http://localhost:8000/ in your browser
   - Should return: `{"status":"ok"}`

2. **API Documentation**: Open http://localhost:8000/docs
   - Should show the FastAPI interactive documentation

3. **Test AI Endpoint**: 
   - GET http://localhost:8000/auth/ai-strategy/list
   - Should return a list of strategies (may be empty)

## Troubleshooting

### Port Already in Use
If port 8000 is already in use, change the port:
```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```
Then update `VITE_STRATEGY_ENGINE_URL` in your frontend `.env` file.

### CORS Errors
CORS is already configured in `app/main.py`. If you still get CORS errors:
1. Check that your frontend URL is in the `allow_origins` list
2. Make sure the server is running on the correct host (0.0.0.0)

### OpenAI API Key Not Working
1. Verify your API key is correct in the `.env` file
2. Check that the key has sufficient credits
3. Verify the model name is correct (default: `gpt-4o-mini`)

## Running Multiple Services

If you need to run both the WebSocket feed and the API server:

1. **Terminal 1** - WebSocket Feed:
   ```powershell
   .\venv\Scripts\python.exe -m app.feed.delta_ws_live
   ```

2. **Terminal 2** - Strategy Engine:
   ```powershell
   .\start_server.ps1
   ```

3. **Terminal 3** - Engine:
   ```powershell
   .\venv\Scripts\python.exe -m app.engine.engine
   ```

Or use the `start_services.ps1` script to start everything in separate windows.

## Production Deployment

For production, use a process manager like:
- **PM2** (Node.js)
- **Supervisor** (Python)
- **systemd** (Linux)
- **Windows Service** (Windows)

Example with uvicorn workers:
```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

