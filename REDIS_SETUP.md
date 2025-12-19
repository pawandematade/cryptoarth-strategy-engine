# Redis Local Setup Guide

## ✅ Current Status

Redis is already running on **localhost:6379** and configured for local testing.

## 🔧 Configuration

### Backend Configuration (`.env` file)
```env
REDIS_HOST=localhost
REDIS_PORT=6379
```

### How It Works

The backend automatically uses these settings from `.env`:
- **REDIS_HOST**: `localhost` (local Redis)
- **REDIS_PORT**: `6379` (default Redis port)

## 🧪 Testing Redis Connection

### Test from Python:
```powershell
cd "C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine"
.\venv\Scripts\python.exe -c "from app.store.redis_client import test_connection; print('Connected!' if test_connection() else 'Failed!')"
```

### Test from Redis CLI (if installed):
```bash
redis-cli ping
# Should return: PONG
```

### Test from Backend API:
```powershell
curl http://localhost:8000/test-redis
# Should return: {"Redis test output": true}
```

## 🚀 Starting Redis (If Not Running)

### Option 1: Using Docker (Recommended)
```powershell
docker run -d -p 6379:6379 --name redis redis:latest
```

### Option 2: Using WSL (Windows Subsystem for Linux)
```bash
wsl
sudo apt-get update
sudo apt-get install redis-server
sudo service redis-server start
```

### Option 3: Using Memurai (Windows Native)
1. Download from: https://www.memurai.com/
2. Install and start the service
3. It runs on localhost:6379 by default

### Option 4: Using Chocolatey
```powershell
choco install redis-64
redis-server
```

## 📝 Verify Redis is Running

### Check if Redis is listening:
```powershell
netstat -ano | findstr :6379
```

### Test connection:
```powershell
$tcp = New-Object System.Net.Sockets.TcpClient
$tcp.Connect("localhost", 6379)
$tcp.Close()
Write-Host "Redis is running!"
```

## 🔄 Switching Between Local and Production Redis

### For Local Testing (Current):
```env
REDIS_HOST=localhost
REDIS_PORT=6379
```

### For Production:
```env
REDIS_HOST=your-production-redis-host
REDIS_PORT=6379
# Or if using Redis Cloud/AWS ElastiCache:
# REDIS_HOST=your-redis-endpoint.cache.amazonaws.com
```

## 🐛 Troubleshooting

### Redis Connection Errors

1. **Check if Redis is running:**
   ```powershell
   netstat -ano | findstr :6379
   ```

2. **Check backend logs** for Redis connection errors

3. **Verify .env file** has correct Redis configuration

4. **Test connection manually:**
   ```python
   import redis
   r = redis.Redis(host='localhost', port=6379)
   r.ping()  # Should return True
   ```

### Common Issues

- **Port 6379 already in use**: Another Redis instance might be running
- **Firewall blocking**: Check Windows Firewall settings
- **Wrong host**: Ensure REDIS_HOST=localhost in .env

## ✅ Current Setup

- ✅ Redis running on localhost:6379
- ✅ Backend configured to use local Redis
- ✅ Ready for local testing

No additional setup needed! Your backend will automatically connect to local Redis.
