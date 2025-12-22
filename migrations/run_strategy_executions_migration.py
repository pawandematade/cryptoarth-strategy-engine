"""
Run migration to sync strategy_executions table schema with backend model.

This script adds missing columns to strategy_executions table:
- strategy_name
- strategy_code
- execution_mode
- trades
- pnl
- activated_at
- deactivated_at

And updates:
- run_source (ensure VARCHAR with default)
- status (ensure ENUM includes 'running' and 'completed')
"""
import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
from app.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Construct database URL
if DB_PASSWORD:
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
else:
    DATABASE_URL = f"mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

def column_exists(engine, table_name, column_name):
    """Check if a column exists in a table."""
    try:
        with engine.connect() as connection:
            result = connection.execute(text(f"""
                SELECT COUNT(*) as count
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = :table_name
                AND COLUMN_NAME = :column_name
            """), {"table_name": table_name, "column_name": column_name})
            row = result.fetchone()
            return row[0] > 0
    except Exception as e:
        logger.error(f"Error checking column existence: {e}")
        return False

def index_exists(engine, table_name, index_name):
    """Check if an index exists."""
    try:
        with engine.connect() as connection:
            result = connection.execute(text(f"""
                SELECT COUNT(*) as count
                FROM INFORMATION_SCHEMA.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = :table_name
                AND INDEX_NAME = :index_name
            """), {"table_name": table_name, "index_name": index_name})
            row = result.fetchone()
            return row[0] > 0
    except Exception as e:
        logger.error(f"Error checking index existence: {e}")
        return False

def run_migration():
    """Run the migration to add missing columns."""
    try:
        logger.info(f"Connecting to database: {DB_NAME} on {DB_HOST}:{DB_PORT}")
        
        # Create engine
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        
        with engine.connect() as connection:
            # Start transaction
            trans = connection.begin()
            
            try:
                # 1. Add strategy_name column
                if not column_exists(engine, "strategy_executions", "strategy_name"):
                    logger.info("Adding strategy_name column...")
                    connection.execute(text("""
                        ALTER TABLE strategy_executions
                        ADD COLUMN strategy_name VARCHAR(255) NOT NULL DEFAULT '' AFTER strategy_version
                    """))
                    logger.info("  ✅ strategy_name added")
                else:
                    logger.info("  ⚠️  strategy_name already exists, skipping")
                
                # 2. Add strategy_code column
                if not column_exists(engine, "strategy_executions", "strategy_code"):
                    logger.info("Adding strategy_code column...")
                    connection.execute(text("""
                        ALTER TABLE strategy_executions
                        ADD COLUMN strategy_code VARCHAR(50) NOT NULL DEFAULT '' AFTER strategy_name
                    """))
                    logger.info("  ✅ strategy_code added")
                else:
                    logger.info("  ⚠️  strategy_code already exists, skipping")
                
                # 3. Add execution_mode column
                if not column_exists(engine, "strategy_executions", "execution_mode"):
                    logger.info("Adding execution_mode column...")
                    connection.execute(text("""
                        ALTER TABLE strategy_executions
                        ADD COLUMN execution_mode ENUM('template', 'paper', 'live') NOT NULL DEFAULT 'paper' AFTER strategy_code
                    """))
                    logger.info("  ✅ execution_mode added")
                else:
                    logger.info("  ⚠️  execution_mode already exists, skipping")
                
                # 4. Update run_source column
                logger.info("Updating run_source column...")
                connection.execute(text("""
                    ALTER TABLE strategy_executions
                    MODIFY COLUMN run_source VARCHAR(30) NOT NULL DEFAULT 'live'
                """))
                logger.info("  ✅ run_source updated")
                
                # 5. Update status ENUM
                logger.info("Updating status ENUM to include 'running' and 'completed'...")
                connection.execute(text("""
                    ALTER TABLE strategy_executions
                    MODIFY COLUMN status ENUM('inactive', 'active', 'paused', 'stopped', 'running', 'completed') NOT NULL DEFAULT 'running'
                """))
                logger.info("  ✅ status ENUM updated")
                
                # 6. Add trades column
                if not column_exists(engine, "strategy_executions", "trades"):
                    logger.info("Adding trades column...")
                    connection.execute(text("""
                        ALTER TABLE strategy_executions
                        ADD COLUMN trades INT NOT NULL DEFAULT 0 AFTER status
                    """))
                    logger.info("  ✅ trades added")
                else:
                    logger.info("  ⚠️  trades already exists, skipping")
                
                # 7. Add pnl column
                if not column_exists(engine, "strategy_executions", "pnl"):
                    logger.info("Adding pnl column...")
                    connection.execute(text("""
                        ALTER TABLE strategy_executions
                        ADD COLUMN pnl VARCHAR(50) NOT NULL DEFAULT '0.0' AFTER trades
                    """))
                    logger.info("  ✅ pnl added")
                else:
                    logger.info("  ⚠️  pnl already exists, skipping")
                
                # 8. Add activated_at column
                if not column_exists(engine, "strategy_executions", "activated_at"):
                    logger.info("Adding activated_at column...")
                    connection.execute(text("""
                        ALTER TABLE strategy_executions
                        ADD COLUMN activated_at DATETIME NULL AFTER pnl
                    """))
                    logger.info("  ✅ activated_at added")
                else:
                    logger.info("  ⚠️  activated_at already exists, skipping")
                
                # 9. Add deactivated_at column
                if not column_exists(engine, "strategy_executions", "deactivated_at"):
                    logger.info("Adding deactivated_at column...")
                    connection.execute(text("""
                        ALTER TABLE strategy_executions
                        ADD COLUMN deactivated_at DATETIME NULL AFTER activated_at
                    """))
                    logger.info("  ✅ deactivated_at added")
                else:
                    logger.info("  ⚠️  deactivated_at already exists, skipping")
                
                # 10. Add indexes
                if not index_exists(engine, "strategy_executions", "ix_strategy_executions_strategy_code"):
                    logger.info("Adding index for strategy_code...")
                    connection.execute(text("""
                        CREATE INDEX ix_strategy_executions_strategy_code ON strategy_executions(strategy_code)
                    """))
                    logger.info("  ✅ index ix_strategy_executions_strategy_code added")
                else:
                    logger.info("  ⚠️  index ix_strategy_executions_strategy_code already exists, skipping")
                
                if not index_exists(engine, "strategy_executions", "ix_strategy_executions_execution_mode"):
                    logger.info("Adding index for execution_mode...")
                    connection.execute(text("""
                        CREATE INDEX ix_strategy_executions_execution_mode ON strategy_executions(execution_mode)
                    """))
                    logger.info("  ✅ index ix_strategy_executions_execution_mode added")
                else:
                    logger.info("  ⚠️  index ix_strategy_executions_execution_mode already exists, skipping")
                
                # Commit transaction
                trans.commit()
                logger.info("✅ Migration completed successfully!")
                return True
                
            except Exception as e:
                trans.rollback()
                raise
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Running migration: Sync strategy_executions schema")
    logger.info("=" * 60)
    
    success = run_migration()
    
    if success:
        logger.info("=" * 60)
        logger.info("✅ Migration completed successfully!")
        logger.info("Please restart the FastAPI server to apply changes.")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        logger.error("=" * 60)
        logger.error("❌ Migration failed!")
        logger.error("=" * 60)
        sys.exit(1)
