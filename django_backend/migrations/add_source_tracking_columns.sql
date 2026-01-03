-- Migration: Add source tracking columns for AI vs Manual distinction
-- Date: 2024
-- Description: Adds created_by to strategies and strategy_versions, run_source to strategy_executions
-- 
-- IMPORTANT: MySQL/MariaDB does NOT support IF NOT EXISTS in ALTER TABLE
-- Run these commands manually or use the Python migration script: python migrations/run_migration.py
--
-- Before running, check if columns exist:
-- SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS 
-- WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'strategies' AND COLUMN_NAME = 'created_by';

-- Add created_by column to strategies table
-- Default to 'manual' for existing records
ALTER TABLE strategies
ADD COLUMN created_by VARCHAR(20) NOT NULL DEFAULT 'manual';

-- Add index for created_by
CREATE INDEX ix_strategies_created_by ON strategies(created_by);

-- Add created_by column to strategy_versions table
-- Default to 'manual' for existing records
ALTER TABLE strategy_versions
ADD COLUMN created_by VARCHAR(20) NOT NULL DEFAULT 'manual';

-- Add index for created_by
CREATE INDEX ix_strategy_versions_created_by ON strategy_versions(created_by);

-- Add run_source column to strategy_executions table
-- Default to 'live' for existing records
ALTER TABLE strategy_executions
ADD COLUMN run_source VARCHAR(30) NOT NULL DEFAULT 'live';

-- Add index for run_source
CREATE INDEX ix_strategy_executions_run_source ON strategy_executions(run_source);

-- Verify columns were added
SELECT 
    COLUMN_NAME, 
    DATA_TYPE, 
    IS_NULLABLE, 
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME IN ('strategies', 'strategy_versions', 'strategy_executions')
    AND COLUMN_NAME IN ('created_by', 'run_source')
ORDER BY TABLE_NAME, COLUMN_NAME;
