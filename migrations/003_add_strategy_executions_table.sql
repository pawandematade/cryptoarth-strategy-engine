-- Migration: 003_add_strategy_executions_table.sql
-- Description: Add strategy_executions table for version-bound execution activation
-- Created: Strategy execution activation feature
-- Notes:
--   - Tracks which version of a strategy is active for execution
--   - Only one ACTIVE execution per strategy_id allowed
--   - TEMP strategies cannot have executions (enforced at API level)
--   - All timestamps stored in UTC

-- Create strategy_executions table
CREATE TABLE IF NOT EXISTS `strategy_executions` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `strategy_id` INT NOT NULL COMMENT 'Foreign key to strategies.id',
    `strategy_version` INT NOT NULL COMMENT 'Version number from strategy_versions',
    `status` ENUM('inactive', 'active', 'paused', 'stopped') NOT NULL DEFAULT 'inactive',
    `activated_at` TIMESTAMP NULL COMMENT 'UTC timestamp when activated',
    `deactivated_at` TIMESTAMP NULL COMMENT 'UTC timestamp when deactivated',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC timestamp',
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'UTC timestamp',
    
    INDEX `idx_strategy_id` (`strategy_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_strategy_status` (`strategy_id`, `status`),
    
    FOREIGN KEY (`strategy_id`) REFERENCES `strategies`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Strategy execution activation. Only one ACTIVE execution per strategy_id allowed.';
