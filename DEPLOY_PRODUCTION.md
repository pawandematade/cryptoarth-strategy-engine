# Production Server Deployment Guide (AWS)

## Quick Start on AWS Linux Server

### 1. SSH into your AWS server
```bash
ssh -i your-key.pem ubuntu@your-aws-ip
# or
ssh -i your-key.pem ec2-user@your-aws-ip
```

### 2. Navigate to project directory
```bash
cd /path/to/Cryptoarth-strategy-engine
# or wherever your project is deployed
```

### 3. Activate virtual environment
```bash
source venv/bin/activate
# or if using conda
conda activate strategy-engine
```

### 4. Start the server with PM2 (Recommended for Production)

#### Install PM2 (if not installed)
```bash
npm install -g pm2
```

#### Start server with PM2
```bash
pm2 start "uvicorn app.main:app --host 0.0.0.0 --port 8000" --name strategy-engine
```

#### Save PM2 configuration
```bash
pm2 save
pm2 startup  # Follow instructions to enable auto-start on reboot
```

### 5. Alternative: Start with systemd (Linux Service)

#### Create service file
```bash
sudo nano /etc/systemd/system/strategy-engine.service
```

#### Add this content:
```ini
[Unit]
Description=CryptoArth Strategy Engine API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/Cryptoarth-strategy-engine
Environment="PATH=/path/to/Cryptoarth-strategy-engine/venv/bin"
ExecStart=/path/to/Cryptoarth-strategy-engine/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Enable and start service
```bash
sudo systemctl daemon-reload
sudo systemctl enable strategy-engine
sudo systemctl start strategy-engine
sudo systemctl status strategy-engine
```

### 6. Check if server is running
```bash
# Check PM2 status
pm2 status

# Check systemd status
sudo systemctl status strategy-engine

# Test endpoint
curl http://localhost:8000/
# Should return: {"status":"ok"}

# Check if accessible from outside
curl https://aistrategy.cryptoarth.in/
```

### 7. View logs
```bash
# PM2 logs
pm2 logs strategy-engine

# Systemd logs
sudo journalctl -u strategy-engine -f
```

## Environment Variables

Make sure your `.env` file on production has:
```env
APP_ENV=production
OPENAI_API_KEY=your_production_key
OPENAI_MODEL=gpt-4o-mini
DELTA_BASE_URL=https://api.india.delta.exchange
REDIS_HOST=your_redis_host
REDIS_PORT=6379
BASE_API_URL=https://aistrategy.cryptoarth.in
FRONTEND_URL=https://panel.cryptoarth.in
```

## Nginx Configuration (if using reverse proxy)

```nginx
server {
    listen 80;
    server_name aistrategy.cryptoarth.in;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Troubleshooting

### Server not accessible
1. Check AWS Security Groups - allow ports 80, 443, 8000
2. Check firewall: `sudo ufw status`
3. Check if process is running: `ps aux | grep uvicorn`
4. Check logs for errors

### Port already in use
```bash
# Find process using port 8000
sudo lsof -i :8000
# Kill it
sudo kill -9 <PID>
```

### Redis connection issues
```bash
# Check Redis is running
redis-cli ping
# Should return: PONG
```

## Quick Commands Reference

```bash
# Start server
pm2 start strategy-engine
# or
sudo systemctl start strategy-engine

# Stop server
pm2 stop strategy-engine
# or
sudo systemctl stop strategy-engine

# Restart server
pm2 restart strategy-engine
# or
sudo systemctl restart strategy-engine

# View logs
pm2 logs strategy-engine
# or
sudo journalctl -u strategy-engine -f

# Check status
pm2 status
# or
sudo systemctl status strategy-engine
```
