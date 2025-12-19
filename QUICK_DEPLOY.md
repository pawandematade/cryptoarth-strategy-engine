# Quick Deployment Guide

## 🚀 For AWS Production Server (Linux)

### Option 1: Using PM2 (Recommended)
```bash
# SSH into your server
ssh user@your-aws-server

# Navigate to project
cd /path/to/Cryptoarth-strategy-engine

# Activate venv
source venv/bin/activate

# Start with PM2
pm2 start "uvicorn app.main:app --host 0.0.0.0 --port 8000" --name strategy-engine
pm2 save
pm2 startup  # Enable auto-start

# Check status
pm2 status
pm2 logs strategy-engine
```

### Option 2: Using systemd
```bash
# Create service (see DEPLOY_PRODUCTION.md for full config)
sudo systemctl start strategy-engine
sudo systemctl enable strategy-engine
sudo systemctl status strategy-engine
```

## 💻 For Local Testing (Windows)

### Quick Start
```powershell
cd "C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine"
.\start_server.ps1
```

### Or manually:
```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## ✅ Verify Server is Running

### Test locally:
```powershell
curl http://localhost:8000/
# Should return: {"status":"ok"}
```

### Test production:
```bash
curl https://aistrategy.cryptoarth.in/
# Should return: {"status":"ok"}
```

## 🔧 Troubleshooting

### Production server not accessible:
1. Check AWS Security Groups (ports 80, 443, 8000)
2. Check if server process is running: `ps aux | grep uvicorn`
3. Check firewall: `sudo ufw status`
4. Check Nginx/load balancer configuration

### Local server issues:
1. Check if port 8000 is in use: `netstat -ano | findstr :8000`
2. Check virtual environment is activated
3. Check .env file exists with correct configuration

## 📝 Environment Configuration

### Production (.env on AWS):
```env
APP_ENV=production
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4o-mini
DELTA_BASE_URL=https://api.india.delta.exchange
REDIS_HOST=your_redis_host
REDIS_PORT=6379
```

### Local (.env.local in frontend):
```env
VITE_STRATEGY_ENGINE_URL=https://aistrategy.cryptoarth.in
VITE_STRATEGY_ENGINE_WS_URL=wss://aistrategy.cryptoarth.in
```

## 🎯 Next Steps

1. **Start production server** on AWS using PM2 or systemd
2. **Verify** server is accessible: `curl https://aistrategy.cryptoarth.in/`
3. **Test** from frontend - the "Server Offline" message should disappear
4. **Monitor** logs: `pm2 logs strategy-engine` or `sudo journalctl -u strategy-engine -f`
