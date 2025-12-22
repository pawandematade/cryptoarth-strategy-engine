"""
Verify Migration Script
Checks that all new columns were added successfully.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from app.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
import os

def get_database_url():
    """Get database URL"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        if DB_PASSWORD:
            database_url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        else:
            database_url = f"mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    return database_url

engine = create_engine(get_database_url(), pool_pre_ping=True)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT 
            TABLE_NAME,
            COLUMN_NAME, 
            DATA_TYPE, 
            IS_NULLABLE, 
            COLUMN_DEFAULT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME IN ('strategies', 'strategy_versions', 'strategy_executions')
            AND COLUMN_NAME IN ('created_by', 'run_source')
        ORDER BY TABLE_NAME, COLUMN_NAME
    """))
    
    rows = result.fetchall()
    
    print("\n✅ Migration Verification:")
    print("=" * 60)
    for row in rows:
        table, column, data_type, nullable, default = row
        print(f"  {table}.{column}:")
        print(f"    Type: {data_type}")
        print(f"    Nullable: {nullable}")
        print(f"    Default: {default}")
        print()
    
    if len(rows) == 3:
        print("✅ All 3 columns added successfully!")
    else:
        print(f"⚠️  Expected 3 columns, found {len(rows)}")

