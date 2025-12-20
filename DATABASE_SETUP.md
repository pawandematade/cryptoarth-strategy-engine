# Database Setup Guide

This guide explains how to set up the database for the AI Strategy Builder backend.

## Prerequisites

1. MySQL server installed and running
2. Python dependencies installed (`pip install -r requirements.txt`)

## Environment Variables

Add the following to your `.env` file:

```env
# Database Configuration
# IMPORTANT: Use a limited database user, not root
# Create user: CREATE USER 'strategy_user'@'localhost' IDENTIFIED BY 'secure_password';
# Grant permissions: GRANT SELECT, INSERT, UPDATE ON cryptoarth_strategy_engine.* TO 'strategy_user'@'localhost';
DB_HOST=localhost
DB_PORT=3306
DB_USER=strategy_user
DB_PASSWORD=secure_password
DB_NAME=cryptoarth_strategy_engine

# Auth Backend Configuration
AUTH_BACKEND_URL=http://localhost:8001
```

## Step 1: Create Database

```sql
CREATE DATABASE IF NOT EXISTS cryptoarth_strategy_engine CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## Step 2: Run Migration

### Option A: Using Python Script (Recommended)

```bash
cd migrations
python run_migration.py 001_init.sql
```

### Option B: Using MySQL Command Line

```bash
mysql -u root -p cryptoarth_strategy_engine < migrations/001_init.sql
```

### Option C: Using MySQL Workbench

1. Open MySQL Workbench
2. Connect to your database
3. Open `migrations/001_init.sql`
4. Execute the SQL script

## Step 3: Verify Tables

```sql
USE cryptoarth_strategy_engine;
SHOW TABLES;
```

You should see:
- `users` (only table at this stage)

## Step 4: Test Database Connection

Create a test script:

```python
from app.database import engine, Base
from app.models import User, Strategy, Backtest

# Test connection
try:
    with engine.connect() as conn:
        print("✅ Database connection successful")
except Exception as e:
    print(f"❌ Database connection failed: {e}")
```

## Using User Sync Service

### Example API Endpoint

```python
from fastapi import Depends, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.user_sync_service import get_or_sync_user, extract_external_user_id_from_auth

@app.post("/api/example")
def example_endpoint(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    # Extract user ID from auth header
    external_user_id = extract_external_user_id_from_auth(authorization)
    if not external_user_id:
        raise HTTPException(status_code=401, detail="Invalid authorization")
    
    # Get or sync user from auth backend
    user = get_or_sync_user(db, external_user_id, authorization)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Use user.local_id for database operations
    return {"user_id": user.id, "external_user_id": user.external_user_id}
```

## Architecture Notes

1. **Users Table**: Local snapshot of auth backend users. Auth backend is the source of truth.
2. **Timezone**: All timestamps stored in UTC. `timezone` column is metadata for display.
3. **TEMP Strategies**: Stateless, never touch the database. DB-independent.
4. **User Sync**: On any request requiring user context, sync user from auth backend.
5. **Fail Fast**: User sync raises exception if auth backend unavailable (no ghost users).

## Troubleshooting

### Connection Error

- Verify MySQL server is running: `mysqladmin ping`
- Check credentials in `.env`
- Ensure database exists

### Migration Errors

- Ensure database is empty or backup existing data
- Check MySQL user has CREATE TABLE privileges
- Verify SQL syntax is valid

### User Sync Not Working

- Check `AUTH_BACKEND_URL` is correct
- Verify auth backend API endpoint: `GET /auth/user`
- Check authorization header format
- Review logs for detailed error messages
