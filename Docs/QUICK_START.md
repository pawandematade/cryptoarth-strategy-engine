# 🚀 Quick Start Guide

## Start the Strategy Engine API Server

### Easiest Way (PowerShell):
```powershell
.\start_server.ps1
```

### Alternative (Batch File):
```cmd
start_server.bat
```

### Start All Services (WebSocket + Engine + API):
```powershell
.\start_services.ps1
```

## ✅ Verify It's Working

1. **Open in browser**: http://localhost:8000/
   - Should show: `{"status":"ok"}`

2. **API Docs**: http://localhost:8000/docs
   - Interactive API documentation

3. **Test AI Endpoint**: http://localhost:8000/auth/ai-strategy/list
   - Should return strategies list

## 🔧 Setup Checklist

- [ ] Virtual environment created and activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created with `OPENAI_API_KEY`
- [ ] Server started successfully
- [ ] Frontend can connect (check browser console)

## 📝 Environment Variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini
DELTA_BASE_URL=https://api.india.delta.exchange
REDIS_HOST=localhost
REDIS_PORT=6379
```

## 🐛 Troubleshooting

**"Network error" in frontend?**
- ✅ Make sure server is running: `.\start_server.ps1`
- ✅ Check CORS is configured (already done in `app/main.py`)
- ✅ Verify frontend URL matches: `http://localhost:5173`

**"Connection refused"?**
- ✅ Server not running - start it with `.\start_server.ps1`
- ✅ Port 8000 already in use - change port in script

**"OpenAI API key error"?**
- ✅ Check `.env` file has `OPENAI_API_KEY=your_key`
- ✅ Verify key is valid and has credits

## 📚 More Help

See `README_STARTUP.md` for detailed documentation.

