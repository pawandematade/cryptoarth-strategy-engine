# Database Implementation Summary

## Overview

This implementation adds database schema and user sync logic for the AI Strategy Builder backend. The database serves as a local cache/snapshot of user data from the auth backend, enabling admin control and reporting without modifying the auth backend.

## Files Created

### 1. Database Configuration
- **`app/database.py`**: SQLAlchemy engine, session factory, and connection utilities
- **`app/config.py`**: Updated with database and auth backend configuration

### 2. Database Models
- **`app/models.py`**: SQLAlchemy models for:
  - `User`: Local snapshot of auth backend users (ONLY table at this stage)

### 3. User Sync Service
- **`app/services/user_sync_service.py`**: Functions for:
  - Fetching user data from auth backend
  - Syncing user data to local database
  - Getting or syncing users on-demand

### 4. Database Migrations
- **`migrations/001_init.sql`**: Initial SQL migration creating all tables
- **`migrations/run_migration.py`**: Python script to run migrations
- **`migrations/README.md`**: Migration documentation

### 5. Documentation
- **`DATABASE_SETUP.md`**: Setup guide with examples
- **`DATABASE_IMPLEMENTATION_SUMMARY.md`**: This file

### 6. Dependencies
- **`requirements.txt`**: Updated with:
  - `sqlalchemy>=2.0.0`
  - `pymysql>=1.1.0`
  - `cryptography>=41.0.0`

## Database Schema

### Users Table (ONLY table at this stage)
- **Purpose**: Local snapshot of auth backend users
- **Key Fields**:
  - `external_user_id`: Unique ID from auth backend (indexed)
  - `raw_user_json`: Full user data snapshot
  - `timezone`: Default "Asia/Kolkata" (for display, not storage)
- **Source of Truth**: Auth backend (read-only sync)

### TEMP Strategies
- **Purpose**: Stateless, never touch the database
- **Behavior**: Fully DB-independent, no persistence
- **Implementation**: TEMP-xxx IDs remain in frontend only

## User Sync Logic

### Flow
1. API endpoint receives request with `Authorization` header
2. Extract `external_user_id` from header (or JWT token)
3. Check if user exists in local `users` table
4. If not exists:
   - Fetch user from auth backend: `GET /auth/user`
   - Create local snapshot in `users` table
5. If exists:
   - Optionally sync to update snapshot (future enhancement)
   - Return cached user
6. Use local `user.id` for all database operations

### Functions
- `get_or_sync_user()`: Main function to use in API endpoints
- `sync_user_to_local_db()`: Sync user from auth backend
- `fetch_user_from_auth_backend()`: Fetch user data from auth backend API
- `extract_external_user_id_from_auth()`: Extract user ID from auth header

## Timezone Handling

- **Storage**: All timestamps stored in UTC
- **Display**: `timezone` column (default "Asia/Kolkata") is metadata only
- **Conversion**: Admin panel/API responses can convert UTC → IST using `timezone` column

## TEMP Strategy Compatibility

- **TEMP Strategies**: Stateless, never touch the database
- **TEMP IDs**: Frontend generates `TEMP-{timestamp}` IDs
- **DB Independence**: TEMP strategies remain fully stateless
- **No Breaking Changes**: Existing TEMP logic remains intact

## Usage Example

```python
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from requests.exceptions import RequestException
from app.database import get_db
from app.services.user_sync_service import get_or_sync_user, extract_external_user_id_from_auth

@app.get("/api/example")
def example_endpoint(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    # Extract user ID from auth header
    external_user_id = extract_external_user_id_from_auth(authorization)
    if not external_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        # Get or sync user (FAILS FAST if auth backend unavailable)
        user = get_or_sync_user(db, external_user_id, authorization)
        
        # Use user.id for database operations
        return {
            "user_id": user.id,
            "external_user_id": user.external_user_id,
            "email": user.email
        }
    except RequestException as e:
        # Auth backend unavailable
        raise HTTPException(status_code=503, detail=f"Auth backend unavailable: {str(e)}")
    except ValueError as e:
        # User not found in auth backend
        raise HTTPException(status_code=404, detail=str(e))
    except SQLAlchemyError as e:
        # Database error
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
```

## Next Steps

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   - Add database credentials to `.env`
   - Set `AUTH_BACKEND_URL`

3. **Run Migration**:
   ```bash
   python migrations/run_migration.py migrations/001_init.sql
   ```

4. **Integrate User Sync**:
   - Update API endpoints to use `get_or_sync_user()`
   - Implement Save Strategy endpoint using Strategy model

5. **Testing**:
   - Test user sync with real auth backend
   - Verify TEMP strategy compatibility
   - Test timezone handling

## Notes

- **No Frontend Changes**: This implementation is backend-only
- **Backward Compatible**: TEMP strategies continue to work
- **Future-Safe**: Schema designed for extensibility
- **Clean Separation**: Auth backend remains source of truth
- **Production Ready**: Includes error handling, logging, indexes

## Architecture Principles

1. **Auth Backend is Source of Truth**: Never modify auth backend data
2. **Local Snapshot for Control**: Use local DB for admin/reporting
3. **UTC Storage**: All timestamps in UTC, convert for display
4. **TEMP Strategies are Stateless**: Never touch the database, fully DB-independent
5. **Fail Fast**: User sync raises exception if auth backend unavailable (no ghost users)
6. **On-Demand Sync**: Sync users only when needed (not on every request)
7. **Current Phase**: User snapshot sync only, no strategy/backtest persistence
