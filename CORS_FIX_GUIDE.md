# CORS Configuration Fix Guide

## ✅ Changes Made

### 1. Backend CORS Configuration Updated
**File:** `app/main.py`

Added the production frontend URL to allowed origins:
- `https://trade-panel.cryptoarth.in` (Main trading panel)
- `https://www.trade-panel.cryptoarth.in` (With www subdomain)

### 2. Frontend Already Configured Correctly
**File:** `src/services/aiStrategyApi.js`

The frontend is already properly configured with:
- ✅ Correct base URL: `https://aistrategy.cryptoarth.in`
- ✅ Retry logic for network errors (2 retries)
- ✅ Increased timeout (120 seconds for AI generation)
- ✅ Authorization header support
- ✅ Better error messages

## 🔧 Backend CORS Configuration (Current)

```python
# Production CORS allowed origins:
allowed_origins = [
    FRONTEND_URL,  # From environment variable
    BASE_API_URL,  # From environment variable
    "https://aistrategy.cryptoarth.in",
    "https://cryptoarth.in",
    "https://panel.cryptoarth.in",
    "https://trade-panel.cryptoarth.in",  # ✅ ADDED
    "https://www.trade-panel.cryptoarth.in",  # ✅ ADDED
]
```

## 📋 Environment Variables Required

### Backend (.env file)
Make sure these are set:
```env
STRATEGY_ENGINE_FRONTEND_URL=https://trade-panel.cryptoarth.in
STRATEGY_ENGINE_BASE_URL=https://aistrategy.cryptoarth.in
```

### Frontend (.env file)
Make sure these are set:
```env
VITE_STRATEGY_ENGINE_URL=https://aistrategy.cryptoarth.in
VITE_API_BASE_URL=https://trade-api.cryptoarth.in
```

## 🚀 How to Apply the Fix

### Step 1: Update Backend CORS
The backend CORS configuration has been updated in `app/main.py`. 

**Restart the Strategy Engine backend:**
```bash
# If using systemd
sudo systemctl restart strategy-engine

# If using Docker
docker-compose restart strategy-engine

# If running manually
# Stop the current process and restart
```

### Step 2: Verify CORS Headers
Test the CORS configuration:
```bash
curl -H "Origin: https://trade-panel.cryptoarth.in" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type,Authorization" \
     -X OPTIONS \
     https://aistrategy.cryptoarth.in/auth/ai-strategy/generate \
     -v
```

Expected response headers:
```
Access-Control-Allow-Origin: https://trade-panel.cryptoarth.in
Access-Control-Allow-Methods: *
Access-Control-Allow-Headers: *
Access-Control-Allow-Credentials: true
```

### Step 3: Test from Browser
1. Open browser console on `https://trade-panel.cryptoarth.in`
2. Try generating a strategy
3. Check Network tab for CORS errors
4. Should see successful API calls

## 🔍 Troubleshooting

### If CORS errors still occur:

1. **Check Backend Logs:**
   ```bash
   # Check if backend is receiving requests
   tail -f /var/log/strategy-engine/app.log
   ```

2. **Verify Environment Variables:**
   ```bash
   # On backend server
   echo $STRATEGY_ENGINE_FRONTEND_URL
   # Should output: https://trade-panel.cryptoarth.in
   ```

3. **Check Browser Console:**
   - Look for specific CORS error messages
   - Check the `Access-Control-Allow-Origin` header in Network tab
   - Verify the request Origin matches allowed origins

4. **Test with curl:**
   ```bash
   # Test actual API call
   curl -X POST https://aistrategy.cryptoarth.in/auth/ai-strategy/generate \
        -H "Content-Type: application/json" \
        -H "Origin: https://trade-panel.cryptoarth.in" \
        -d '{"prompt":"test","symbol":"BTCUSD"}' \
        -v
   ```

## ✅ Verification Checklist

- [ ] Backend CORS includes `https://trade-panel.cryptoarth.in`
- [ ] Backend environment variable `STRATEGY_ENGINE_FRONTEND_URL` is set
- [ ] Backend has been restarted after changes
- [ ] Frontend environment variable `VITE_STRATEGY_ENGINE_URL` is set to `https://aistrategy.cryptoarth.in`
- [ ] Frontend has been rebuilt and deployed
- [ ] Browser console shows no CORS errors
- [ ] API calls succeed from production frontend

## 📝 Additional Notes

- The frontend already has retry logic (2 retries) for network errors
- Timeout is set to 120 seconds for AI generation
- Authorization header is automatically added if token is available
- Error messages are user-friendly and specific

## 🆘 If Issues Persist

1. **Check Nginx/Proxy Configuration:**
   - Ensure proxy passes CORS headers correctly
   - No CORS headers being stripped

2. **Check Firewall:**
   - Port 443 (HTTPS) should be open
   - No blocking of requests from frontend domain

3. **Check SSL Certificates:**
   - Both domains should have valid SSL certificates
   - No certificate errors in browser

4. **Contact Support:**
   - Share browser console errors
   - Share backend logs
   - Share Network tab request/response headers

