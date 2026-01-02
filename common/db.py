"""
Database Connection and Session Management
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError
import logging
import os

logger = logging.getLogger(__name__)

# Construct database URL
# CRITICAL: SQLAlchemy ONLY reads DATABASE_URL from environment
# DATABASE_URL is the single source of truth - hard fail if missing
# NO fallback logic, NO postgres, NO localhost defaults
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# CRITICAL: Explicitly validate DATABASE_URL is MySQL - block PostgreSQL
if not DATABASE_URL.startswith("mysql+pymysql://"):
    error_msg = (
        f"CRITICAL: DATABASE_URL must use MySQL (mysql+pymysql://). "
        f"Found: {DATABASE_URL[:30]}... "
        f"PostgreSQL and other databases are NOT supported."
    )
    logger.error(error_msg)
    raise ValueError(error_msg)

logger.info("Using DATABASE_URL from environment variable (MySQL only)")

# Create engine with safe configuration
# CRITICAL: Only ONE engine in entire project - uses DATABASE_URL directly
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
# DO NOT import models here - this creates circular import (models import Base from here)
Base = declarative_base()


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
            logger.info("âœ… Database connection successful")
            return True
    except OperationalError as e:
        logger.error(f"âŒ Database connection failed (OperationalError): {e}")
        return False
    except SQLAlchemyError as e:
        logger.error(f"âŒ Database connection failed (SQLAlchemyError): {e}")
        return False
    except Exception as e:
        logger.error(f"âŒ Database connection failed (Unexpected error): {e}")
        return False


def init_db() -> bool:
    """
    Initialize database - create all tables if they don't exist.
    Safe version that doesn't raise exceptions.
    
    NOTE: Models must be imported BEFORE calling this function to register with Base.metadata.
    This function does NOT import models to avoid circular import.
    
    Returns:
        bool: True if tables were created/verified successfully, False otherwise
    """
    try:
        # Test connection first
        if not test_db_connection():
            logger.error("Cannot initialize database - connection test failed")
            return False
        
        # CRITICAL: Models must be imported BEFORE this function is called
        # (in main.py or wherever init_db() is called)
        # This avoids circular import: models import Base from database.py
        
        # Verify models are registered with Base.metadata
        tables = list(Base.metadata.tables.keys())
        if not tables:
            logger.warning("âš ï¸  No tables found in Base.metadata. Models may not be imported yet.")
            logger.warning("   Make sure all models are imported before calling init_db()")
            return False
        
        logger.info(f"Creating tables: {', '.join(tables)}")
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("âœ… Database tables initialized successfully")
        logger.info(f"   Created/verified {len(tables)} table(s): {', '.join(tables)}")
        return True
    except OperationalError as e:
        logger.error(f"âŒ Database initialization failed (OperationalError): {e}")
        logger.warning("   Make sure MySQL/MariaDB is running and database exists")
        return False
    except SQLAlchemyError as e:
        logger.error(f"âŒ Database initialization failed (SQLAlchemyError): {e}")
        return False
    except Exception as e:
        logger.error(f"âŒ Database initialization failed (Unexpected error): {e}")
        return False
