-- Migration: 007_add_credit_correction_fields_simple.sql
-- Description: Add fields to credit_transactions for admin credit correction flow
-- This is a simpler version that should work on all MySQL versions

-- Add original_transaction_id field (check if exists first)
-- If column already exists, this will fail gracefully - you can ignore the error
ALTER TABLE `credit_transactions`
ADD COLUMN `original_transaction_id` BIGINT NULL COMMENT 'ID of original transaction if this is a correction' AFTER `reference_id`;

-- Add admin_name field (check if exists first)
-- If column already exists, this will fail gracefully - you can ignore the error
ALTER TABLE `credit_transactions`
ADD COLUMN `admin_name` VARCHAR(100) NULL COMMENT 'Admin name who created this transaction (for corrections)' AFTER `original_transaction_id`;

-- Add index for original_transaction_id
-- If index already exists, this will fail gracefully - you can ignore the error
CREATE INDEX `idx_original_transaction_id` ON `credit_transactions` (`original_transaction_id`);

-- Add foreign key constraint (self-referencing)
-- If constraint already exists, this will fail gracefully - you can ignore the error
ALTER TABLE `credit_transactions`
ADD CONSTRAINT `fk_credit_transactions_original`
FOREIGN KEY (`original_transaction_id`) REFERENCES `credit_transactions`(`id`) ON DELETE SET NULL;

