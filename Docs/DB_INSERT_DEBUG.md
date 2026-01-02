# 🔍 DB Insert Debug - Strategy Save

## ✅ Debug Logs Added

### STEP 1: Active Database Confirmation
- Added in `save_strategy()`: `print(f"🔥 ACTIVE DB: HOST={DB_HOST}, NAME={DB_NAME}")`
- Added in `save_strategy_endpoint()`: `print(f"🔥 [ENDPOINT] ACTIVE DB: HOST={DB_HOST}, NAME={DB_NAME}")`

**Expected Output:**
```
🔥 ACTIVE DB: HOST=139.59.78.109, NAME=tradearth_db
```

### STEP 2: Verify Actual Save Call
- Added logs before/after `db.add()` calls
- Added logs before/after `db.commit()`
- Added verification query after commit

**Expected Output:**
```
✅ Strategy object created: id=<id>, code=<code>
✅ StrategyVersion object created: strategy_id=<id>, version=1
🔥 Attempting db.commit()...
✅ db.commit() completed successfully
✅ VERIFIED: Strategy <id> EXISTS in DB: code=<code>
```

### STEP 3: Transaction Rollback Check
- Wrapped `db.commit()` in try-except to catch commit failures
- Added rollback logging if commit fails

### STEP 4: StrategyVersion Insert Check
- Added log: `print(f"✅ StrategyVersion object created: strategy_id={strategy.id}, version=1")`
- If this log doesn't appear, code path is not executing

### STEP 5: Model save() Override / Signals
- ✅ Verified: No custom `save()` methods found
- ✅ Verified: No signals found

### STEP 6: Response Uses Real DB ID
- Added validation: `if not strategy.id or strategy.id <= 0: raise ValueError(...)`
- Added log: `print(f"✅ Strategy ID verified: {strategy.id}")`

## 🔧 Additional Debugging

### SQL Query Logging Enabled
- Set `echo=True` in `database.py` (TEMP - remove after debug)
- All SQL queries will be logged to console

### Exception Tracing
- Added `traceback.print_exc()` in exception handlers
- Full stack traces will be printed

## 📋 Next Steps

1. **Run the API** and check console output for:
   - Active DB host and name
   - Commit success/failure
   - Verification query results

2. **Check for these issues:**
   - Wrong database connection (HOST/NAME mismatch)
   - Commit failure (exception during commit)
   - Verification query fails (data not actually inserted)
   - Session closed before commit

3. **After identifying the issue:**
   - Fix root cause
   - Remove TEMP debug logs
   - Set `echo=False` in database.py

## 🚨 Common Issues to Check

1. **Wrong Database**: If HOST/NAME is not `139.59.78.109` / `tradearth_db` → Fix `.env.local`
2. **Commit Failure**: If `db.commit() FAILED` appears → Check database constraints/permissions
3. **Verification Fails**: If `Strategy NOT FOUND in DB after commit` → Transaction rollback issue
4. **No Logs**: If logs don't appear → Code path not executing (check endpoint routing)

