-- Migration: 006_credit_system.sql
-- Description: Credit system tables for AI Strategy Builder
-- Created: Credit management system
-- Notes:
--   - All credit rules are DB-driven (no hardcoding)
--   - Credit costs stored in credit_config table
--   - User credits tracked in user_credits table
--   - All transactions logged in credit_transactions
--   - Strategy usage limits tracked in strategy_usage
--   - Payment transactions stored in payment_transactions

-- 1. credit_config (GLOBAL CREDIT RULES)
CREATE TABLE IF NOT EXISTS `credit_config` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `action_key` VARCHAR(50) UNIQUE NOT NULL COMMENT 'Action identifier (e.g., ai_strategy_generate)',
    `credit_cost` INT NOT NULL COMMENT 'Credit cost for this action',
    `is_active` BOOLEAN DEFAULT TRUE COMMENT 'Whether this rule is active',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX `idx_action_key` (`action_key`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Global credit rules and costs for all actions';

-- 2. user_credits (USER WALLET)
CREATE TABLE IF NOT EXISTS `user_credits` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `user_id` BIGINT UNIQUE NOT NULL COMMENT 'Foreign key to users.id (local user ID)',
    `total_credits` INT DEFAULT 0 COMMENT 'Total credits available',
    `used_credits` INT DEFAULT 0 COMMENT 'Total credits used',
    `is_active` BOOLEAN DEFAULT TRUE,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_is_active` (`is_active`),
    
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='User credit wallet - tracks total and used credits';

-- 3. credit_transactions (AUDIT LOG)
CREATE TABLE IF NOT EXISTS `credit_transactions` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `user_id` BIGINT NOT NULL COMMENT 'Foreign key to users.id (local user ID)',
    `type` ENUM('debit','credit') NOT NULL COMMENT 'Transaction type',
    `credits` INT NOT NULL COMMENT 'Credit amount',
    `reason` VARCHAR(100) NULL COMMENT 'Reason for transaction',
    `reference_id` VARCHAR(100) NULL COMMENT 'Reference ID (e.g., payment_id, strategy_code)',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_type` (`type`),
    INDEX `idx_created_at` (`created_at`),
    INDEX `idx_reference_id` (`reference_id`),
    
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Audit log for all credit transactions';

-- 4. strategy_usage (BACKTEST LIMIT)
CREATE TABLE IF NOT EXISTS `strategy_usage` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `user_id` BIGINT NOT NULL COMMENT 'Foreign key to users.id (local user ID)',
    `strategy_code` VARCHAR(50) NOT NULL COMMENT 'Strategy code (e.g., STRG-XXXX)',
    `action_key` VARCHAR(50) NOT NULL COMMENT 'Action identifier (e.g., backtest)',
    `usage_count` INT DEFAULT 0 COMMENT 'Number of times this action was performed',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    UNIQUE KEY `unique_user_strategy_action` (`user_id`, `strategy_code`, `action_key`),
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_strategy_code` (`strategy_code`),
    INDEX `idx_action_key` (`action_key`),
    
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Tracks usage count per strategy per action (for free limits)';

-- 5. payment_transactions (RAZORPAY)
CREATE TABLE IF NOT EXISTS `payment_transactions` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `user_id` BIGINT NOT NULL COMMENT 'Foreign key to users.id (local user ID)',
    `provider` VARCHAR(20) DEFAULT 'razorpay' COMMENT 'Payment provider',
    `amount` DECIMAL(10,2) NOT NULL COMMENT 'Payment amount in INR',
    `credits_added` INT NOT NULL COMMENT 'Credits added to user wallet',
    `status` ENUM('created','success','failed') DEFAULT 'created' COMMENT 'Payment status',
    `gateway_order_id` VARCHAR(100) NULL COMMENT 'Razorpay order ID',
    `gateway_payment_id` VARCHAR(100) NULL COMMENT 'Razorpay payment ID',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_gateway_order_id` (`gateway_order_id`),
    INDEX `idx_gateway_payment_id` (`gateway_payment_id`),
    INDEX `idx_created_at` (`created_at`),
    
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Payment transactions from Razorpay';

-- Insert initial credit config data
INSERT INTO `credit_config` (`action_key`, `credit_cost`, `is_active`) VALUES
('ai_strategy_generate', 1, TRUE),
('backtest_after_free_limit', 1, TRUE),
('ai_help_optimization', 2, TRUE),
('default_free_credit', 10, TRUE),
('rupee_to_credit_ratio', 10, TRUE)
ON DUPLICATE KEY UPDATE `credit_cost` = VALUES(`credit_cost`), `is_active` = VALUES(`is_active`);

