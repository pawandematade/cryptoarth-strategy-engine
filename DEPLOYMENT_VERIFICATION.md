# Payment Service Deployment Verification Guide

## CRITICAL: Code Deployment Verification

This document provides steps to verify that the updated payment service code is running in production.

## Diagnostic Logs Added

The following diagnostic logs have been added to confirm which code is running:

### Module Load Logs (on service startup):
- `🔧 PAYMENT ROUTES MODULE LOADED: file=<path>, loaded_at=<timestamp>`
- `🔧 PAYMENT SERVICE MODULE LOADED: file=<path>, loaded_at=<timestamp>`

### Payment Verification Logs (on each payment):
- `🔧 PAYMENT VERIFY ENDPOINT CALLED: file=<path>, loaded_at=<timestamp>`
- `🔐 PAYMENT VERIFY START: current_user.id=<id>, email=<email>, phone=<phone>, order_id=<order_id>`
- `🔐 JWT AUTHENTICATED USER_ID: <id> (MUST NOT be 1 unless admin is paying)`
- `🚀 PAYMENT PROCESS START: user_id=<id>, order_id=<order_id>, payment_id=<payment_id>`
- `🔍 BEFORE user_credits UPSERT: querying for user_id=<id>`
- `📝 CREATING NEW user_credits record: user_id=<id> (NOT admin user_id=1)`
- `✅ NEW user_credits record created: id=<id>, user_id=<id>, total_credits=<credits>`
- `🔄 BEFORE DB COMMIT: user_id=<id>, credits=<credits>`
- `✅ DB FLUSH SUCCESS: All objects flushed to session`
- `✅ DB COMMIT SUCCESS: payment_id=<id>, user_id=<id>, credits=<credits>`
- `🔍 POST-COMMIT VERIFICATION: Querying user_credits for user_id=<id>`
- `✅ POST-COMMIT VERIFIED: user_credits found in DB - id=<id>, user_id=<id>, total_credits=<credits>`

## Verification Steps

### Step 1: Check Service Status
```bash
# Check which service is running
sudo systemctl status cryptoarth-strategy

# Check all uvicorn/gunicorn processes
ps aux | grep -E "uvicorn|gunicorn|python.*app.main"

# Check which Python process is serving the API
sudo netstat -tlnp | grep :8000
# or
sudo ss -tlnp | grep :8000
```

### Step 2: Verify Code Path
```bash
# Check the service file to see which code path it's using
sudo cat /etc/systemd/system/cryptoarth-strategy.service

# Check the working directory
sudo systemctl show cryptoarth-strategy | grep WorkingDirectory

# Verify the code path exists and has the updated files
ls -la /path/to/Cryptoarth-strategy-engine/app/api/routes_payment.py
ls -la /path/to/Cryptoarth-strategy-engine/app/services/payment_service.py
```

### Step 3: Check Startup Logs
```bash
# Check for module load logs
sudo journalctl -u cryptoarth-strategy -n 100 | grep "PAYMENT.*MODULE LOADED"

# Check for any errors during startup
sudo journalctl -u cryptoarth-strategy -n 200 | grep -i error
```

### Step 4: Restart Service (if needed)
```bash
# Stop the service
sudo systemctl stop cryptoarth-strategy

# Kill any remaining processes
sudo pkill -9 -f "uvicorn.*app.main"
sudo pkill -9 -f "python.*app.main"

# Clear Python cache
find /path/to/Cryptoarth-strategy-engine -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find /path/to/Cryptoarth-strategy-engine -name "*.pyc" -delete

# Start the service
sudo systemctl start cryptoarth-strategy

# Check status
sudo systemctl status cryptoarth-strategy

# Watch logs in real-time
sudo journalctl -u cryptoarth-strategy -f
```

### Step 5: Test Payment and Verify Logs
```bash
# Make a test payment, then check logs
sudo journalctl -u cryptoarth-strategy -n 500 | grep -E "PAYMENT|user_credits|user_id"

# Look for the diagnostic logs
sudo journalctl -u cryptoarth-strategy -n 500 | grep "🔧\|🔐\|🚀\|🔍\|📝\|✅"
```

### Step 6: Verify Database
```sql
-- After a test payment, check user_credits table
SELECT * FROM user_credits ORDER BY id DESC LIMIT 10;

-- Should see a NEW row for the paying user (not just admin user_id=1)
-- Verify user_id matches the JWT-authenticated user
```

## Expected Behavior

### If Code is Deployed Correctly:
1. **Startup logs** will show:
   - `🔧 PAYMENT ROUTES MODULE LOADED: file=/path/to/routes_payment.py`
   - `🔧 PAYMENT SERVICE MODULE LOADED: file=/path/to/payment_service.py`

2. **Payment logs** will show:
   - `🔐 PAYMENT VERIFY START: current_user.id=<non-admin-id>`
   - `📝 CREATING NEW user_credits record: user_id=<non-admin-id>`
   - `✅ POST-COMMIT VERIFIED: user_credits found in DB`

3. **Database** will have:
   - New row in `user_credits` table for paying user
   - Admin `user_id=1` row unchanged

### If Code is NOT Deployed:
- No diagnostic logs will appear
- Old behavior continues (credits go to admin)
- Database shows only admin row

## Troubleshooting

### If logs don't appear:
1. **Check file paths**: Verify the service is using the correct code directory
2. **Check Python cache**: Clear `__pycache__` directories
3. **Check service restart**: Ensure service was restarted after code changes
4. **Check multiple processes**: Kill all Python processes and restart service
5. **Check log level**: Ensure ERROR level logs are enabled (using `logger.error()`)

### If wrong file path appears:
1. **Check service file**: Verify `WorkingDirectory` in systemd service file
2. **Check PYTHONPATH**: Verify Python can find the app module
3. **Check symlinks**: Verify no symlinks pointing to old code

## Critical Files Modified

1. `app/api/routes_payment.py`
   - Added `get_current_user` dependency
   - Added diagnostic logging
   - Uses JWT-authenticated user

2. `app/services/payment_service.py`
   - Explicit user_credits UPSERT logic
   - Post-commit verification
   - Extensive diagnostic logging

## Deployment Checklist

- [ ] Code files updated in production directory
- [ ] Python cache cleared (`__pycache__` removed)
- [ ] Service restarted (`sudo systemctl restart cryptoarth-strategy`)
- [ ] All Python processes killed and restarted
- [ ] Startup logs show module load messages
- [ ] Test payment made
- [ ] Payment logs show diagnostic messages
- [ ] Database shows new user_credits row for paying user
- [ ] Admin user_id=1 row unchanged

## BLOCKER RESOLUTION

**DO NOT proceed with testing until:**
1. Startup logs show `🔧 PAYMENT.*MODULE LOADED`
2. Payment logs show `🔐 PAYMENT VERIFY START`
3. Payment logs show `📝 CREATING NEW user_credits record`
4. Payment logs show `✅ POST-COMMIT VERIFIED`

If these logs do NOT appear, the fix is NOT deployed and testing is invalid.

