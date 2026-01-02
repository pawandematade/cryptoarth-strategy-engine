# 🔧 Troubleshooting Network Errors

## Problem: "Network error. Please check: 1. Strategy Engine is running..."

### ✅ Solution Steps:

#### Step 1: Check if Server is Running
```powershell
.\check_server.ps1
```

Or manually check:
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/" -UseBasicParsing
```

#### Step 2: Start the Server

**Option A - Use the startup script (Easiest):**
```powershell
.\start_server.ps1
```

**Option B - Manual start:**
```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**You should see:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

#### Step 3: Verify Server is Accessible

1. **Open in browser**: http://localhost:8000/
   - Should show: `{"status":"ok"}`

2. **Check API docs**: http://localhost:8000/docs
   - Should show FastAPI documentation

3. **Test AI endpoint**: http://localhost:8000/auth/ai-strategy/list
   - Should return JSON (may be empty array)

#### Step 4: Check Frontend Configuration

Make sure your frontend `.env` file has:
```env
VITE_STRATEGY_ENGINE_URL=http://localhost:8000
```

Or check `src/config/env.js` - it should default to `http://localhost:8000`

#### Step 5: Check CORS

CORS is already configured in `app/main.py`. If you still get CORS errors:

1. Make sure your frontend URL is in the allowed origins
2. Check browser console for specific CORS error messages
3. Verify the server is running on `0.0.0.0` (not just `127.0.0.1`)

## Common Issues:

### Issue 1: Port 8000 Already in Use
**Error**: `Address already in use`

**Solution**:
```powershell
# Find what's using port 8000
netstat -ano | findstr :8000

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F

# Or use a different port
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Then update frontend `.env`:
```env
VITE_STRATEGY_ENGINE_URL=http://localhost:8001
```

### Issue 2: Virtual Environment Not Activated
**Error**: `ModuleNotFoundError` or `python: command not found`

**Solution**:
```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Then start server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Issue 3: Missing Dependencies
**Error**: `ModuleNotFoundError: No module named 'fastapi'`

**Solution**:
```powershell
.\venv\Scripts\Activate.ps1
pip install fastapi uvicorn openai python-dotenv redis websocket-client
```

### Issue 4: Firewall Blocking Connection
**Error**: Connection timeout

**Solution**:
1. Check Windows Firewall settings
2. Allow Python through firewall
3. Or temporarily disable firewall for testing

### Issue 5: CORS Still Not Working
**Error**: CORS policy error in browser console

**Solution**:
1. Check `app/main.py` has CORS middleware (already added)
2. Make sure `allow_origins` includes your frontend URL
3. Restart the server after making changes
4. Clear browser cache

## Quick Diagnostic Commands:

```powershell
# Check if server is running
.\check_server.ps1

# Check what's on port 8000
netstat -ano | findstr :8000

# Test connection
Invoke-WebRequest -Uri "http://localhost:8000/" -UseBasicParsing

# Check Python version
.\venv\Scripts\python.exe --version

# Check if modules are installed
.\venv\Scripts\python.exe -c "import fastapi; import uvicorn; print('OK')"
```

## Still Having Issues?

1. **Check server logs** - Look at the terminal where you started the server
2. **Check browser console** - Open DevTools (F12) and check for errors
3. **Verify .env file** - Make sure `OPENAI_API_KEY` is set
4. **Test with curl/Postman** - Try the API directly:
   ```powershell
   Invoke-WebRequest -Uri "http://localhost:8000/auth/ai-strategy/list" -Method GET
   ```

## Need More Help?

- Check `README_STARTUP.md` for detailed setup
- Check `QUICK_START.md` for quick reference
- Verify all files are in the correct locations

