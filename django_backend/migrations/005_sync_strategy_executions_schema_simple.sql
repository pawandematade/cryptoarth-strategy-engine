-- Migration: 005_sync_strategy_executions_schema.sql
-- Description: Add missing columns to strategy_executions table to match backend model
-- This fixes "Unknown column" errors when creating strategy runs

-- Add strategy_name column (if not exists - check manually before running)
ALTER TABLE strategy_executions
ADD COLUMN IF NOT EXISTS strategy_name VARCHAR(255) NOT NULL DEFAULT '' AFTER strategy_version;

-- Add strategy_code column
ALTER TABLE strategy_executions
ADD COLUMN IF NOT EXISTS strategy_code VARCHAR(50) NOT NULL DEFAULT '' AFTER strategy_name;

-- Add execution_mode column
ALTER TABLE strategy_executions
ADD COLUMN IF NOT EXISTS execution_mode ENUM('template', 'paper', 'live') NOT NULL DEFAULT 'paper' AFTER strategy_code;

-- Update run_source column (ensure it's VARCHAR with default)
-- Note: If column doesn't exist, it will be added. If it exists, it will be modified.
ALTER TABLE strategy_executions
MODIFY COLUMN run_source VARCHAR(30) NOT NULL DEFAULT 'live';

-- Update status ENUM to include 'running' and 'completed'
ALTER TABLE strategy_executions
MODIFY COLUMN status ENUM('inactive', 'active', 'paused', 'stopped', 'running', 'completed') NOT NULL DEFAULT 'running';

-- Add trades column
ALTER TABLE strategy_executions
ADD COLUMN IF NOT EXISTS trades INT NOT NULL DEFAULT 0 AFTER status;

-- Add pnl column
ALTER TABLE strategy_executions
ADD COLUMN IF NOT EXISTS pnl VARCHAR(50) NOT NULL DEFAULT '0.0' AFTER trades;

-- Add activated_at column (if not exists)
ALTER TABLE strategy_executions
ADD COLUMN IF NOT EXISTS activated_at DATETIME NULL AFTER pnl;

-- Add deactivated_at column (if not exists)
ALTER TABLE strategy_executions
ADD COLUMN IF NOT EXISTS deactivated_at DATETIME NULL AFTER activated_at;

-- Add indexes (if not exists - will fail gracefully if already exist)
CREATE INDEX IF NOT EXISTS ix_strategy_executions_strategy_code ON strategy_executions(strategy_code);
CREATE INDEX IF NOT EXISTS ix_strategy_executions_execution_mode ON strategy_executions(execution_mode);

