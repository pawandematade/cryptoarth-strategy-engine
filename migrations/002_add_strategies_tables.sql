-- Migration: 002_add_strategies_tables.sql
-- Description: Add strategies and strategy_versions tables for TEMP → SAVED strategy transition
-- Created: Strategy save feature
-- Notes:
--   - TEMP strategies (TEMP-xxx) are NOT stored in these tables
--   - Only explicitly saved strategies are persisted
--   - All timestamps stored in UTC

-- Create strategies table
CREATE TABLE IF NOT EXISTS `strategies` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL COMMENT 'Foreign key to users.id',
    `strategy_code` VARCHAR(50) NOT NULL UNIQUE COMMENT 'Generated unique code (e.g., STRG-XXXX)',
    `name` VARCHAR(255) NOT NULL COMMENT 'Strategy name',
    `description` TEXT NULL COMMENT 'Optional strategy description',
    `status` ENUM('draft', 'active', 'paused', 'archived') NOT NULL DEFAULT 'draft',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC timestamp',
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'UTC timestamp',
    
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_strategy_code` (`strategy_code`),
    INDEX `idx_status` (`status`),
    
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Saved strategies. TEMP strategies (TEMP-xxx) are NOT stored here.';

-- Create strategy_versions table
CREATE TABLE IF NOT EXISTS `strategy_versions` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `strategy_id` INT NOT NULL COMMENT 'Foreign key to strategies.id',
    `version` INT NOT NULL DEFAULT 1 COMMENT 'Version number, starts from 1',
    `strategy_payload` JSON NOT NULL COMMENT 'Full strategy JSON payload',
    `backtest_snapshot` JSON NULL COMMENT 'Optional backtest snapshot JSON',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC timestamp',
    
    INDEX `idx_strategy_id` (`strategy_id`),
    INDEX `idx_version` (`strategy_id`, `version`),
    
    FOREIGN KEY (`strategy_id`) REFERENCES `strategies`(`id`) ON DELETE CASCADE,
    UNIQUE KEY `unique_strategy_version` (`strategy_id`, `version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Strategy versions. Each edit creates a new version.';
