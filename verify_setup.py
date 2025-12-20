"""
Quick verification script to check database setup.
Run this after setting up database to verify everything works.
"""
import sys
import os

def check_files():
    """Check if all required files exist."""
    files = [
        "app/database.py",
        "app/models.py",
        "app/services/user_sync_service.py",
        "migrations/001_init.sql",
        "migrations/run_migration.py",
    ]
    
    missing = []
    for file in files:
        if not os.path.exists(file):
            missing.append(file)
    
    if missing:
        print("❌ Missing files:")
        for f in missing:
            print(f"   - {f}")
        return False
    else:
        print("✅ All required files exist")
        return True


def check_imports():
    """Check if required packages can be imported."""
    try:
        import sqlalchemy
        print("✅ SQLAlchemy installed")
    except ImportError:
        print("❌ SQLAlchemy not installed. Run: pip install sqlalchemy")
        return False
    
    try:
        import pymysql
        print("✅ PyMySQL installed")
    except ImportError:
        print("❌ PyMySQL not installed. Run: pip install pymysql")
        return False
    
    try:
        from app.database import engine, Base
        print("✅ Database module imports successfully")
    except Exception as e:
        print(f"❌ Error importing database module: {e}")
        return False
    
    try:
        from app.models import User
        print("✅ Models import successfully (User model only)")
    except Exception as e:
        print(f"❌ Error importing models: {e}")
        return False
    
    try:
        from app.services.user_sync_service import get_or_sync_user
        print("✅ User sync service imports successfully")
    except Exception as e:
        print(f"❌ Error importing user sync service: {e}")
        return False
    
    return True


def check_config():
    """Check if config has database settings."""
    try:
        from app.config import DB_HOST, DB_NAME, AUTH_BACKEND_URL
        print(f"✅ Config loaded: DB_HOST={DB_HOST}, DB_NAME={DB_NAME}")
        print(f"   AUTH_BACKEND_URL={AUTH_BACKEND_URL}")
        return True
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("Database Setup Verification")
    print("=" * 50)
    print()
    
    all_ok = True
    
    print("1. Checking files...")
    if not check_files():
        all_ok = False
    print()
    
    print("2. Checking imports...")
    if not check_imports():
        all_ok = False
    print()
    
    print("3. Checking config...")
    if not check_config():
        all_ok = False
    print()
    
    if all_ok:
        print("=" * 50)
        print("✅ All checks passed!")
        print("=" * 50)
        print()
        print("Next steps:")
        print("1. Create database: CREATE DATABASE cryptoarth_strategy_engine;")
        print("2. Run migration: python migrations/run_migration.py migrations/001_init.sql")
        print("3. Test connection: Create a test script using get_db()")
    else:
        print("=" * 50)
        print("❌ Some checks failed. Please fix the issues above.")
        print("=" * 50)
        sys.exit(1)
