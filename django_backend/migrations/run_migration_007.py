#!/usr/bin/env python3
"""
Migration Script: 007_add_credit_correction_fields
Run this script to add the missing columns to credit_transactions table.

Usage:
    python migrations/run_migration_007.py
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Run migration 007 to add credit correction fields."""
    
    migration_sql = """
-- Add original_transaction_id field
ALTER TABLE `credit_transactions`
ADD COLUMN `original_transaction_id` BIGINT NULL COMMENT 'ID of original transaction if this is a correction' AFTER `reference_id`;

-- Add admin_name field
ALTER TABLE `credit_transactions`
ADD COLUMN `admin_name` VARCHAR(100) NULL COMMENT 'Admin name who created this transaction (for corrections)' AFTER `original_transaction_id`;

-- Add index for original_transaction_id
CREATE INDEX `idx_original_transaction_id` ON `credit_transactions` (`original_transaction_id`);

-- Add foreign key constraint
ALTER TABLE `credit_transactions`
ADD CONSTRAINT `fk_credit_transactions_original`
FOREIGN KEY (`original_transaction_id`) REFERENCES `credit_transactions`(`id`) ON DELETE SET NULL;
"""
    
    # Split into individual statements
    statements = [s.strip() for s in migration_sql.split(';') if s.strip() and not s.strip().startswith('--')]
    
    try:
        with engine.connect() as conn:
            for statement in statements:
                if statement:
                    try:
                        logger.info(f"Executing: {statement[:50]}...")
                        conn.execute(text(statement))
                        conn.commit()
                        logger.info("✅ Success")
                    except Exception as e:
                        error_msg = str(e)
                        # Check if error is because column/index/constraint already exists
                        if "Duplicate column name" in error_msg or "Duplicate key name" in error_msg or "Duplicate foreign key" in error_msg:
                            logger.warning(f"⚠️  Already exists, skipping: {error_msg[:100]}")
                        else:
                            logger.error(f"❌ Error: {error_msg}")
                            raise
            logger.info("✅ Migration 007 completed successfully!")
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    logger.info("Starting Migration 007: Add credit correction fields")
    run_migration()

