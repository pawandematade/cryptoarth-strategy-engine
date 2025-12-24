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
            logger.warning("⚠️  No tables found in Base.metadata. Models may not be imported yet.")
            logger.warning("   Make sure all models are imported before calling init_db()")
            return False
        
        logger.info(f"Creating tables: {', '.join(tables)}")
        
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
