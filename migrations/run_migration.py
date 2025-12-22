"""
Database Migration Script
Adds source tracking columns (created_by, run_source) to existing tables.

Usage:
    python migrations/run_migration.py

This script:
1. Connects to database using environment variables
2. Executes SQL migrations to add new columns
3. Verifies columns were added successfully
"""
import os
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from app.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment or config"""
    # Check for DATABASE_URL first
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        # Build from components
        if DB_PASSWORD:
            database_url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        else:
            database_url = f"mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    
    return database_url


def check_column_exists(engine, table_name, column_name):
    """Check if a column exists in a table"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
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


def run_migration():
    """Run database migration to add source tracking columns"""
    try:
        # Get database URL
        database_url = get_database_url()
        logger.info(f"Connecting to database: {DB_NAME} on {DB_HOST}:{DB_PORT}")
        
        # Create engine
        engine = create_engine(database_url, pool_pre_ping=True)
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful")
        
        # Migration SQL statements
        migrations = [
            {
                "name": "Add created_by to strategies",
                "table": "strategies",
                "column": "created_by",
                "sql": "ALTER TABLE strategies ADD COLUMN created_by VARCHAR(20) NOT NULL DEFAULT 'manual'",
                "check_exists": True
            },
            {
                "name": "Add index for strategies.created_by",
                "table": "strategies",
                "column": "created_by",
                "sql": "CREATE INDEX ix_strategies_created_by ON strategies(created_by)",
                "check_index": True,
                "index_name": "ix_strategies_created_by"
            },
            {
                "name": "Add created_by to strategy_versions",
                "table": "strategy_versions",
                "column": "created_by",
                "sql": "ALTER TABLE strategy_versions ADD COLUMN created_by VARCHAR(20) NOT NULL DEFAULT 'manual'",
                "check_exists": True
            },
            {
                "name": "Add index for strategy_versions.created_by",
                "table": "strategy_versions",
                "column": "created_by",
                "sql": "CREATE INDEX ix_strategy_versions_created_by ON strategy_versions(created_by)",
                "check_index": True,
                "index_name": "ix_strategy_versions_created_by"
            },
            {
                "name": "Add run_source to strategy_executions",
                "table": "strategy_executions",
                "column": "run_source",
                "sql": "ALTER TABLE strategy_executions ADD COLUMN run_source VARCHAR(30) NOT NULL DEFAULT 'live'",
                "check_exists": True
            },
            {
                "name": "Add index for strategy_executions.run_source",
                "table": "strategy_executions",
                "column": "run_source",
                "sql": "CREATE INDEX ix_strategy_executions_run_source ON strategy_executions(run_source)",
                "check_index": True,
                "index_name": "ix_strategy_executions_run_source"
            }
        ]
        
        def check_index_exists(engine, table_name, index_name):
            """Check if an index exists"""
            try:
                with engine.connect() as conn:
                    result = conn.execute(text(f"""
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
        
        # Execute migrations
        with engine.begin() as conn:  # Use begin() for transaction
            for migration in migrations:
                try:
                    # Check if column/index already exists before running
                    if migration.get("check_exists", False):
                        if check_column_exists(engine, migration["table"], migration["column"]):
                            logger.info(f"⏭️  Skipping {migration['name']} - column already exists")
                            continue
                    
                    if migration.get("check_index", False):
                        if check_index_exists(engine, migration["table"], migration["index_name"]):
                            logger.info(f"⏭️  Skipping {migration['name']} - index already exists")
                            continue
                    
                    # Execute migration
                    logger.info(f"🔄 Running: {migration['name']}")
                    conn.execute(text(migration["sql"]))
                    logger.info(f"✅ Completed: {migration['name']}")
                    
                except OperationalError as e:
                    error_msg = str(e)
                    # Check if it's a "duplicate column/index" error (MySQL/MariaDB)
                    if "Duplicate column name" in error_msg or "Duplicate key name" in error_msg or "already exists" in error_msg.lower():
                        logger.warning(f"⚠️  {migration['name']} - Already exists, skipping")
                        continue
                    else:
                        logger.error(f"❌ Failed: {migration['name']}: {error_msg}")
                        raise
                except Exception as e:
                    error_msg = str(e)
                    # Check if it's a duplicate error
                    if "Duplicate" in error_msg or "already exists" in error_msg.lower():
                        logger.warning(f"⚠️  {migration['name']} - Already exists, skipping")
                        continue
                    else:
                        logger.error(f"❌ Failed: {migration['name']}: {error_msg}")
                        raise
        
        # Verify migrations
        logger.info("\n🔍 Verifying migrations...")
        with engine.connect() as conn:
            # Check strategies.created_by
            if check_column_exists(engine, "strategies", "created_by"):
                logger.info("✅ strategies.created_by exists")
            else:
                logger.error("❌ strategies.created_by NOT found")
            
            # Check strategy_versions.created_by
            if check_column_exists(engine, "strategy_versions", "created_by"):
                logger.info("✅ strategy_versions.created_by exists")
            else:
                logger.error("❌ strategy_versions.created_by NOT found")
            
            # Check strategy_executions.run_source
            if check_column_exists(engine, "strategy_executions", "run_source"):
                logger.info("✅ strategy_executions.run_source exists")
            else:
                logger.error("❌ strategy_executions.run_source NOT found")
        
        logger.info("\n✅ Migration completed successfully!")
        logger.info("📝 Next steps:")
        logger.info("   1. Restart the backend server")
        logger.info("   2. Test Save Strategy API")
        logger.info("   3. Verify Template and History tabs show data")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run_migration()

