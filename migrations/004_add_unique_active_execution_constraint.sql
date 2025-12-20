-- Migration: 004_add_unique_active_execution_constraint.sql
-- Description: Add unique constraint to ensure only one ACTIVE execution per strategy_id
-- Created: Fix race condition in strategy execution activation
-- Notes:
--   - Prevents concurrent requests from creating multiple ACTIVE executions
--   - Uses generated column workaround for MySQL (MySQL 5.7.6+ supports generated columns)
--   - MySQL doesn't support partial unique indexes directly, so we use a generated column
--   - The unique constraint applies only when status='active'
--   - Row-level locking (SELECT FOR UPDATE) in application code provides additional protection

-- Check if column already exists (idempotent migration)
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'strategy_executions'
    AND COLUMN_NAME = 'unique_active_strategy_id'
);

-- Add a generated column that contains strategy_id only when status='active', NULL otherwise
-- This allows us to create a unique index that effectively enforces "only one active per strategy_id"
-- The column will be NULL for inactive/paused/stopped rows, allowing multiple rows
-- But only one row per strategy_id can have a non-NULL value (when status='active')
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE `strategy_executions`
    ADD COLUMN `unique_active_strategy_id` INT GENERATED ALWAYS AS (
        CASE WHEN `status` = ''active'' THEN `strategy_id` ELSE NULL END
    ) STORED NULL',
    'SELECT ''Column unique_active_strategy_id already exists, skipping.'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Check if index already exists (idempotent migration)
SET @idx_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.STATISTICS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'strategy_executions'
    AND INDEX_NAME = 'idx_unique_active_strategy'
);

-- Create unique index on the generated column
-- This ensures only one row can have status='active' for each strategy_id
-- MySQL allows NULL values in unique indexes, so multiple NULLs are allowed
SET @sql = IF(@idx_exists = 0,
    'CREATE UNIQUE INDEX `idx_unique_active_strategy` ON `strategy_executions` (`unique_active_strategy_id`)',
    'SELECT ''Index idx_unique_active_strategy already exists, skipping.'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
