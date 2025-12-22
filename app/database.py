"""
Database Connection and Session Management
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from app.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, APP_ENV
import logging

logger = logging.getLogger(__name__)

# Construct database URL
# Priority: 1) DATABASE_URL from .env, 2) Build from components
import os
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Build DATABASE_URL from individual components
    # Handle empty password for XAMPP (local development)
    if DB_PASSWORD:
        DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    else:
        # Empty password - XAMPP default
        DATABASE_URL = f"mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
else:
    logger.info(f"Using DATABASE_URL from environment variable")

# Create engine with safe configuration
# TEMP: Enable SQL logging to debug insert issues
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_size=5,  # Connection pool size
    max_overflow=10,  # Max overflow connections
    echo=True  # TEMP: Set to True for SQL query logging (REMOVE AFTER DEBUG)
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
# CRITICAL: SINGLE Base definition - all models must use this Base
# This is the ONLY place where declarative_base() is called
Base = declarative_base()

# CRITICAL: Import models IMMEDIATELY after Base is defined
# This ensures all models are registered with Base.metadata before any queries
# Models import Base from this module, so import happens after Base is defined
# This is safe because Python handles the circular import correctly
from app.models import User, Strategy, StrategyVersion, StrategyExecution, PaperTrade  # noqa: F401
logger.info("✅ Models imported at module level: User, Strategy, StrategyVersion, StrategyExecution, PaperTrade")


def get_db() -> Session:
    """
    Dependency function for FastAPI to get database session.
    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_db_connection() -> bool:
    """
    Test database connection safely.
    Returns True if connection is successful, False otherwise.
    Does not raise exceptions - safe to call on startup.
    """
    try:
        with engine.connect() as connection:
            # Simple query to test connection
            result = connection.execute(text("SELECT 1"))
            result.fetchone()
            logger.info(f"✅ Database connection successful (APP_ENV={APP_ENV}, DB={DB_NAME})")
            return True
    except OperationalError as e:
        logger.error(f"❌ Database connection failed (OperationalError): {e}")
        logger.warning(f"   Database: {DB_NAME} on {DB_HOST}:{DB_PORT}")
        logger.warning(f"   User: {DB_USER}")
        return False
    except SQLAlchemyError as e:
        logger.error(f"❌ Database connection failed (SQLAlchemyError): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Database connection failed (Unexpected error): {e}")
        return False


def init_db() -> bool:
    """
    Initialize database - create all tables if they don't exist.
    Safe version that doesn't raise exceptions.
    
    Returns:
        bool: True if tables were created/verified successfully, False otherwise
    """
    try:
        # Test connection first
        if not test_db_connection():
            logger.error("Cannot initialize database - connection test failed")
            return False
        
        # Models should already be imported at module level (after Base definition)
        # But import again here to ensure they're registered before create_all()
        from app.models import User, Strategy, StrategyVersion, StrategyExecution, PaperTrade  # noqa: F401
        
        # CRITICAL: Verify models are registered with Base.metadata
        # Log which tables will be created
        tables = list(Base.metadata.tables.keys())
        logger.info(f"Creating tables: {', '.join(tables)}")
        
        # Verify expected tables are present
        expected_tables = ['users', 'strategies', 'strategy_versions', 'strategy_executions', 'paper_trades']
        missing_tables = [t for t in expected_tables if t not in tables]
        if missing_tables:
            logger.error(f"❌ CRITICAL: Missing tables in Base.metadata: {missing_tables}")
            logger.error(f"   Available tables: {tables}")
            raise ValueError(f"Models not properly registered: missing tables {missing_tables}")
        else:
            logger.info(f"✅ All expected tables registered: {expected_tables}")
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info(f"✅ Database tables initialized successfully (DB={DB_NAME})")
        logger.info(f"   Created/verified {len(tables)} table(s): {', '.join(tables)}")
        return True
    except OperationalError as e:
        logger.error(f"❌ Database initialization failed (OperationalError): {e}")
        logger.warning("   Make sure MySQL/MariaDB is running and database exists")
        return False
    except SQLAlchemyError as e:
        logger.error(f"❌ Database initialization failed (SQLAlchemyError): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Database initialization failed (Unexpected error): {e}")
        return False
