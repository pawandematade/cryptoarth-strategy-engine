# FastAPI Database Configuration Fix

## ✅ Changes Made

### 1. DATABASE_URL Support
- **Priority**: Uses `DATABASE_URL` from `.env` if available
- **Fallback**: Builds from individual components if `DATABASE_URL` not set
- **Format**: `mysql+pymysql://root:@127.0.0.1:3306/tradearth_db_local?charset=utf8mb4`

### 2. Explicit Model Imports
- Updated `init_db()` to explicitly import all models:
  - `User`
  - `Strategy`
  - `StrategyVersion`
  - `StrategyExecution`
- Ensures all tables are registered before `create_all()`

### 3. Table Creation Logging
- Logs which tables are being created
- Shows count of tables created/verified

## 📋 Setup Instructions

### Step 1: Create `.env.local` File

Create `.env.local` in project root:

```env
# Option 1: Use DATABASE_URL directly (recommended)
DATABASE_URL=mysql+pymysql://root:@127.0.0.1:3306/tradearth_db_local?charset=utf8mb4

# Option 2: Use individual components (alternative)
STRATEGY_DB_HOST=127.0.0.1
STRATEGY_DB_PORT=3306
STRATEGY_DB_USER=root
STRATEGY_DB_PASSWORD=
STRATEGY_DB_NAME=tradearth_db_local

# App Environment
APP_ENV=local

# API Configuration
STRATEGY_ENGINE_BASE_URL=http://127.0.0.1:8000
STRATEGY_ENGINE_FRONTEND_URL=http://localhost:5173

# Redis Configuration
STRATEGY_REDIS_HOST=127.0.0.1
STRATEGY_REDIS_PORT=6379

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini

# Auth Backend
AUTH_BACKEND_URL=https://trade-api.cryptoarth.in
```

### Step 2: Create Database

In phpMyAdmin or MySQL CLI:

```sql
CREATE DATABASE IF NOT EXISTS tradearth_db_local CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### Step 3: Start Server

```powershell
cd "C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 4: Verify Tables Created

Check server logs for:
```
✅ Database connection successful
Creating tables: users, strategies, strategy_versions, strategy_executions
✅ Database tables initialized successfully
   Created/verified 4 table(s)
```

Or check in phpMyAdmin:
- Navigate to `tradearth_db_local` database
- Should see tables: `users`, `strategies`, `strategy_versions`, `strategy_executions`

## 🔍 Verification

### Test Database Connection
```powershell
curl http://127.0.0.1:8000/test-db
```

Expected response:
```json
{
  "database_test": true,
  "environment": "local",
  "database": "tradearth_db_local",
  "host": "127.0.0.1:3306",
  "status": "connected"
}
```

### Check Tables in phpMyAdmin
1. Open phpMyAdmin
2. Select `tradearth_db_local` database
3. Check "Structure" tab
4. Should see 4 tables:
   - `users`
   - `strategies`
   - `strategy_versions`
   - `strategy_executions`

## ⚠️ Important Notes

1. **No Django Settings**: This is FastAPI/SQLAlchemy, NOT Django
2. **DATABASE_URL Format**: Must use `mysql+pymysql://` (not `django.db.backends.mysql`)
3. **Empty Password**: Use `root:@` for XAMPP default (empty password)
4. **Table Auto-Creation**: Tables are created automatically on server startup via `init_db()`
5. **Model Imports**: All models must be imported before `create_all()` - this is now explicit

## 🐛 Troubleshooting

### Issue: Tables not created
**Check:**
- Database exists
- Connection successful (check logs)
- Models imported correctly
- No import errors in logs

### Issue: Connection failed
**Check:**
- MySQL/XAMPP is running
- Database exists
- Credentials correct
- DATABASE_URL format correct

### Issue: "Unknown database"
**Fix:**
```sql
CREATE DATABASE tradearth_db_local;
```

## ✅ Expected Result

After fix:
- ✅ Tables auto-create on server startup
- ✅ Inserts work correctly
- ✅ phpMyAdmin shows all 4 tables
- ✅ No Django-related errors
- ✅ SQLAlchemy engine uses correct DATABASE_URL

