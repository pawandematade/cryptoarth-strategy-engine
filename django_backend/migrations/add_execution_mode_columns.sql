-- Migration: Add execution_mode and related columns to strategy_executions
-- Also create paper_trades table

-- Step 1: Add new columns to strategy_executions
ALTER TABLE strategy_executions
ADD COLUMN strategy_name VARCHAR(255) NOT NULL DEFAULT '' AFTER strategy_version,
ADD COLUMN strategy_code VARCHAR(50) NOT NULL DEFAULT '' AFTER strategy_name,
ADD COLUMN execution_mode ENUM('template', 'paper', 'live') NOT NULL DEFAULT 'live' AFTER strategy_code,
ADD COLUMN trades INT NOT NULL DEFAULT 0 AFTER status,
ADD COLUMN pnl VARCHAR(50) NOT NULL DEFAULT '0.0' AFTER trades;

-- Update run_source to allow new values
ALTER TABLE strategy_executions
MODIFY COLUMN run_source VARCHAR(30) NOT NULL DEFAULT 'live';

-- Update status enum to include 'running' and 'completed'
-- Note: MySQL doesn't support ALTER ENUM directly, so we'll use MODIFY
ALTER TABLE strategy_executions
MODIFY COLUMN status ENUM('inactive', 'active', 'paused', 'stopped', 'running', 'completed') NOT NULL DEFAULT 'running';

-- Add indexes
CREATE INDEX ix_strategy_executions_strategy_code ON strategy_executions(strategy_code);
CREATE INDEX ix_strategy_executions_execution_mode ON strategy_executions(execution_mode);

-- Step 2: Create paper_trades table
CREATE TABLE IF NOT EXISTS paper_trades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    execution_id INT NOT NULL,
    symbol VARCHAR(50) NOT NULL COMMENT 'Trading symbol (e.g., BTCUSD)',
    side VARCHAR(10) NOT NULL COMMENT 'BUY or SELL',
    lot_size VARCHAR(50) NOT NULL COMMENT 'Lot size as string (supports large numbers)',
    contract_value VARCHAR(50) NOT NULL COMMENT 'Contract value as string',
    entry_price VARCHAR(50) NULL COMMENT 'Entry price as string',
    exit_price VARCHAR(50) NULL COMMENT 'Exit price as string (null for open positions)',
    leverage INT NOT NULL COMMENT 'Leverage used',
    usable_capital VARCHAR(50) NOT NULL COMMENT 'Usable capital as string',
    margin_used VARCHAR(50) NOT NULL COMMENT 'Margin used as string',
    pnl VARCHAR(50) NOT NULL DEFAULT '0.0' COMMENT 'Trade PnL as string',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (execution_id) REFERENCES strategy_executions(id) ON DELETE CASCADE,
    INDEX ix_paper_trades_execution_id (execution_id),
    INDEX ix_paper_trades_symbol (symbol),
    INDEX ix_paper_trades_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Paper trade records. Tracks virtual trades for paper trading.';

