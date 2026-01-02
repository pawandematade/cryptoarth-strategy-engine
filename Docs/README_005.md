# Migration 005: Sync strategy_executions Schema

## Problem
Runtime error: `Unknown column 'strategy_executions.strategy_name'`

The backend code expects new columns in `strategy_executions` table, but the database schema is outdated.

## Solution
This migration adds all missing columns to match the `StrategyExecution` model in `app/models.py`.

## Columns Added

1. **strategy_name** - VARCHAR(255) NOT NULL DEFAULT ''
2. **strategy_code** - VARCHAR(50) NOT NULL DEFAULT ''
3. **execution_mode** - ENUM('template', 'paper', 'live') NOT NULL DEFAULT 'paper'
4. **trades** - INT NOT NULL DEFAULT 0
5. **pnl** - VARCHAR(50) NOT NULL DEFAULT '0.0'
6. **activated_at** - DATETIME NULL
7. **deactivated_at** - DATETIME NULL

## Columns Updated

1. **run_source** - Modified to VARCHAR(30) NOT NULL DEFAULT 'live'
2. **status** - Modified ENUM to include 'running' and 'completed', default 'running'

## Indexes Added

1. **ix_strategy_executions_strategy_code** - Index on strategy_code
2. **ix_strategy_executions_execution_mode** - Index on execution_mode

## How to Run

### Option 1: Python Script (Recommended)
```bash
cd Cryptoarth-strategy-engine
python migrations/run_strategy_executions_migration.py
```

### Option 2: Manual SQL
Execute the SQL file directly in MySQL:
```bash
mysql -u <user> -p <database> < migrations/005_sync_strategy_executions_schema_simple.sql
```

## After Migration

1. **Restart FastAPI server** to ensure it picks up the new schema
2. **Test POST /strategy-runs/live** endpoint
3. **Verify History tab** shows new execution rows

## Verification

The migration script will:
- Check if columns exist before adding them
- Skip existing columns/indexes gracefully
- Log all operations for debugging

## Expected Result

- ✅ No 'Unknown column' DB errors
- ✅ POST /strategy-runs/live works
- ✅ History tab shows new execution rows
- ✅ All columns match StrategyExecution model

