# Strategy Save Implementation

## Overview

This implementation adds the TEMP → SAVED strategy transition feature. TEMP strategies remain stateless and never touch the database. Only explicitly saved strategies are persisted.

## API Endpoint

**POST /strategies/save**

### Request

```json
{
  "temp_strategy_id": "TEMP-1234567890",
  "name": "My Strategy Name",
  "description": "Optional description",
  "strategy_payload": {
    // Full strategy JSON object
  },
  "backtest_snapshot": {
    // Optional backtest snapshot JSON
  }
}
```

**Headers:**
```
Authorization: Bearer <token>
```

### Response (Success)

```json
{
  "success": true,
  "strategy_id": 123,
  "strategy_code": "STRG-ABCD",
  "version": 1,
  "message": "Strategy saved successfully"
}
```

### Response (Error)

```json
{
  "detail": "Error message"
}
```

Status codes:
- `400`: Validation error
- `401`: Authorization required
- `503`: Auth backend unavailable
- `500`: Database error

## Flow (Strict Order)

1. Extract Authorization token from header
2. Call auth backend user API: `GET https://trade-api.cryptoarth.in/auth/user/`
   - **FAIL FAST**: If auth backend returns non-200, raise exception immediately
   - Do NOT save anything if auth backend unavailable
3. Sync user into local DB:
   - Match using `external_user_id = auth_user.id`
   - Insert if not exists
   - Update user snapshot if exists
   - Default timezone = "Asia/Kolkata"
   - Store timestamps in UTC
4. Validate `temp_strategy_id`:
   - Must start with "TEMP-"
   - Reject otherwise
5. Validate `strategy_payload` schema:
   - Must be a JSON object
   - Cannot be empty
   - (Additional validations can be added)
6. Generate unique `strategy_code` (e.g., "STRG-ABCD")
7. Create strategy and first version in database transaction:
   - Insert into `strategies` table
   - Insert into `strategy_versions` table (version=1)
8. If ANY error occurs:
   - Rollback transaction
   - Return error
   - TEMP strategy remains untouched

## Database Schema

### strategies Table

- `id` (PK, auto-increment)
- `user_id` (FK → users.id)
- `strategy_code` (unique, e.g., "STRG-ABCD")
- `name` (required)
- `description` (optional)
- `status` (ENUM: 'draft', 'active', 'paused', 'archived')
- `created_at` (UTC timestamp)
- `updated_at` (UTC timestamp, auto-update)

### strategy_versions Table

- `id` (PK, auto-increment)
- `strategy_id` (FK → strategies.id)
- `version` (INT, starts from 1)
- `strategy_payload` (JSON)
- `backtest_snapshot` (JSON, nullable)
- `created_at` (UTC timestamp)

## Key Rules

1. **TEMP strategies are NOT stored** in `strategies` table
2. **Strategy persistence happens ONLY** inside `/strategies/save` endpoint
3. **Never overwrite strategy_payload** - each edit creates a new version
4. **Fail fast** if auth backend unavailable (no ghost users/strategies)
5. **Use transactions** for safety (rollback on error)
6. **TEMP strategy remains intact** if save fails

## Migration

Run migration:
```bash
mysql -u strategy_user -p cryptoarth_strategy_engine < migrations/002_add_strategies_tables.sql
```

## Testing

1. Test with valid TEMP strategy ID
2. Test with invalid TEMP strategy ID (should reject)
3. Test with auth backend unavailable (should fail fast)
4. Test with invalid strategy_payload (should reject)
5. Test transaction rollback on error

## Files Created/Modified

1. `migrations/002_add_strategies_tables.sql` - Database schema
2. `app/models.py` - Added Strategy and StrategyVersion models
3. `app/services/strategy_save_service.py` - Save logic
4. `app/api/routes_strategy_save.py` - API endpoint
5. `app/main.py` - Added router
6. `app/services/user_sync_service.py` - Updated to support auth backend API format
7. `app/config.py` - Updated AUTH_BACKEND_URL default

## Notes

- TEMP strategies continue to work as before (fully stateless)
- No changes to existing TEMP generation or backtest logic
- User sync always fetches from auth backend at save time
- All timestamps stored in UTC
- Strategy codes are unique (4-character random suffix)
