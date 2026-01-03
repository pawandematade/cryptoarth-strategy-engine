-- Migration: 005_sync_strategy_executions_schema.sql
-- Description: Add missing columns to strategy_executions table to match backend model
-- This fixes "Unknown column" errors when creating strategy runs

-- Step 1: Add strategy_name column (if not exists)
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'strategy_executions' 
    AND COLUMN_NAME = 'strategy_name'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE strategy_executions ADD COLUMN strategy_name VARCHAR(255) NOT NULL DEFAULT \'\' AFTER strategy_version',
    'SELECT "Column strategy_name already exists" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 2: Add strategy_code column (if not exists)
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'strategy_executions' 
    AND COLUMN_NAME = 'strategy_code'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE strategy_executions ADD COLUMN strategy_code VARCHAR(50) NOT NULL DEFAULT \'\' AFTER strategy_name',
    'SELECT "Column strategy_code already exists" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 3: Add execution_mode column (if not exists)
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'strategy_executions' 
    AND COLUMN_NAME = 'execution_mode'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE strategy_executions ADD COLUMN execution_mode ENUM(\'template\', \'paper\', \'live\') NOT NULL DEFAULT \'paper\' AFTER strategy_code',
    'SELECT "Column execution_mode already exists" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 4: Update run_source column (ensure it's VARCHAR and has default)
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'strategy_executions' 
    AND COLUMN_NAME = 'run_source'
);

SET @sql = IF(@col_exists > 0,
    'ALTER TABLE strategy_executions MODIFY COLUMN run_source VARCHAR(30) NOT NULL DEFAULT \'live\'',
    'ALTER TABLE strategy_executions ADD COLUMN run_source VARCHAR(30) NOT NULL DEFAULT \'live\' AFTER execution_mode'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 5: Update status ENUM to include 'running' and 'completed'
-- Note: MySQL doesn't support ALTER ENUM directly, so we check current type first
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'strategy_executions' 
    AND COLUMN_NAME = 'status'
);

SET @sql = IF(@col_exists > 0,
    'ALTER TABLE strategy_executions MODIFY COLUMN status ENUM(\'inactive\', \'active\', \'paused\', \'stopped\', \'running\', \'completed\') NOT NULL DEFAULT \'running\'',
    'ALTER TABLE strategy_executions ADD COLUMN status ENUM(\'inactive\', \'active\', \'paused\', \'stopped\', \'running\', \'completed\') NOT NULL DEFAULT \'running\''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 6: Add trades column (if not exists)
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'strategy_executions' 
    AND COLUMN_NAME = 'trades'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE strategy_executions ADD COLUMN trades INT NOT NULL DEFAULT 0 AFTER status',
    'SELECT "Column trades already exists" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 7: Add pnl column (if not exists)
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'strategy_executions' 
    AND COLUMN_NAME = 'pnl'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE strategy_executions ADD COLUMN pnl VARCHAR(50) NOT NULL DEFAULT \'0.0\' AFTER trades',
    'SELECT "Column pnl already exists" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 8: Add activated_at column (if not exists)
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'strategy_executions' 
    AND COLUMN_NAME = 'activated_at'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE strategy_executions ADD COLUMN activated_at DATETIME NULL AFTER pnl',
    'SELECT "Column activated_at already exists" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 9: Add deactivated_at column (if not exists)
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'strategy_executions' 
    AND COLUMN_NAME = 'deactivated_at'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE strategy_executions ADD COLUMN deactivated_at DATETIME NULL AFTER activated_at',
    'SELECT "Column deactivated_at already exists" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 10: Add indexes (if not exists)
-- Index for strategy_code
SET @idx_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.STATISTICS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'strategy_executions' 
    AND INDEX_NAME = 'ix_strategy_executions_strategy_code'
);

SET @sql = IF(@idx_exists = 0,
    'CREATE INDEX ix_strategy_executions_strategy_code ON strategy_executions(strategy_code)',
    'SELECT "Index ix_strategy_executions_strategy_code already exists" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Index for execution_mode
SET @idx_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.STATISTICS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'strategy_executions' 
    AND INDEX_NAME = 'ix_strategy_executions_execution_mode'
);

SET @sql = IF(@idx_exists = 0,
    'CREATE INDEX ix_strategy_executions_execution_mode ON strategy_executions(execution_mode)',
    'SELECT "Index ix_strategy_executions_execution_mode already exists" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Success message
SELECT "Migration 005 completed: strategy_executions schema synced" AS result;

