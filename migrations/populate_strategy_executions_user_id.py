"""
Migration Script: Populate user_id in strategy_executions table

This script populates the user_id column in strategy_executions table
by copying user_id from the associated strategy in the strategies table.

Run this script ONCE after adding the user_id column to strategy_executions.

Usage:
    python migrations/populate_strategy_executions_user_id.py
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get DATABASE_URL from environment
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    logger.error("DATABASE_URL environment variable is required")
    sys.exit(1)

# Create engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def populate_user_id():
    """
    Populate user_id in strategy_executions from strategies.user_id
    """
    db = SessionLocal()
    try:
        # SQL query to update strategy_executions.user_id from strategies.user_id
        update_query = text("""
            UPDATE strategy_executions se
            INNER JOIN strategies s ON se.strategy_id = s.id
            SET se.user_id = s.user_id
            WHERE se.user_id IS NULL OR se.user_id = 0
        """)
        
        result = db.execute(update_query)
        rows_updated = result.rowcount
        db.commit()
        
        logger.info(f"✅ Successfully updated {rows_updated} rows in strategy_executions")
        
        # Verify update
        verify_query = text("""
            SELECT COUNT(*) as count
            FROM strategy_executions
            WHERE user_id IS NULL OR user_id = 0
        """)
        
        result = db.execute(verify_query)
        remaining_null = result.fetchone()[0]
        
        if remaining_null > 0:
            logger.warning(f"⚠️  {remaining_null} rows still have NULL or 0 user_id")
        else:
            logger.info("✅ All rows have valid user_id")
            
    except Exception as e:
        logger.error(f"❌ Error populating user_id: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("Starting migration: Populate user_id in strategy_executions")
    populate_user_id()
    logger.info("Migration completed")

