"""
Backtest Candle Storage Service
Stores backtest candle data in database tables dynamically generated from Python schema.

CRITICAL: Schema is defined ONLY in Python code (delta_history.py, backtest_engine.py).
This service derives table structure from that schema - NO duplicate definitions.
"""
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import text, inspect
from sqlalchemy.engine import Engine
from app.database import engine

logger = logging.getLogger(__name__)

# ✅ SOURCE OF TRUTH: Candle schema from Python code
# Derived from:
# - app/feed/delta_history.py (lines 243-248): candle dict structure
# - app/engine/backtest_engine.py (line 239): required DataFrame columns
# - app/engine/strategy_runner.py (line 381): required DataFrame columns
CANDLE_SCHEMA = {
    'time': {
        'type': 'BIGINT',
        'nullable': False,
        'primary_key': True,
        'comment': 'Unix timestamp in seconds'
    },
    'open': {
        'type': 'DECIMAL(20, 8)',
        'nullable': False,
        'comment': 'Opening price'
    },
    'high': {
        'type': 'DECIMAL(20, 8)',
        'nullable': False,
        'comment': 'Highest price'
    },
    'low': {
        'type': 'DECIMAL(20, 8)',
        'nullable': False,
        'comment': 'Lowest price'
    },
    'close': {
        'type': 'DECIMAL(20, 8)',
        'nullable': False,
        'comment': 'Closing price'
    },
    'volume': {
        'type': 'DECIMAL(20, 8)',
        'nullable': False,
        'comment': 'Trading volume'
    }
}


def get_table_name(symbol: str) -> str:
    """
    Generate table name from symbol.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD')
    
    Returns:
        Table name: 'aibacktest_<SYMBOL>' (lowercase, sanitized)
    """
    # Sanitize symbol: lowercase, remove special characters
    sanitized = symbol.upper().replace('-', '').replace('_', '').replace(' ', '')
    return f"aibacktest_{sanitized.lower()}"


def generate_create_table_sql(table_name: str) -> str:
    """
    Generate CREATE TABLE SQL from Python schema definition.
    
    CRITICAL: This function derives SQL from CANDLE_SCHEMA - NO hardcoded columns.
    If Python schema changes, this function automatically reflects those changes.
    
    Args:
        table_name: Table name (e.g., 'aibacktest_btcusd')
    
    Returns:
        CREATE TABLE SQL statement
    """
    # Build column definitions from schema
    columns = []
    primary_keys = []
    
    for column_name, column_def in CANDLE_SCHEMA.items():
        col_sql = f"`{column_name}` {column_def['type']}"
        
        if not column_def.get('nullable', True):
            col_sql += " NOT NULL"
        
        if column_def.get('comment'):
            col_sql += f" COMMENT '{column_def['comment']}'"
        
        columns.append(col_sql)
        
        if column_def.get('primary_key', False):
            primary_keys.append(f"`{column_name}`")
    
    # Build full CREATE TABLE statement
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
        {', '.join(columns)},
        PRIMARY KEY ({', '.join(primary_keys)})
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    COMMENT='Backtest candle data for {table_name.replace('aibacktest_', '').upper()}';
    """
    
    return create_sql.strip()


def table_exists(table_name: str, engine_instance: Engine = engine) -> bool:
    """
    Check if table exists in database.
    
    Args:
        table_name: Table name to check
        engine_instance: SQLAlchemy engine (default: app.database.engine)
    
    Returns:
        True if table exists, False otherwise
    """
    try:
        inspector = inspect(engine_instance)
        return table_name in inspector.get_table_names()
    except Exception as e:
        logger.error(f"Error checking if table {table_name} exists: {e}")
        return False


def create_table_if_not_exists(symbol: str, engine_instance: Engine = engine) -> bool:
    """
    Create table for symbol if it doesn't exist.
    
    CRITICAL: Table structure is derived from CANDLE_SCHEMA (Python schema).
    No hardcoded SQL columns - schema is single source of truth.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD')
        engine_instance: SQLAlchemy engine (default: app.database.engine)
    
    Returns:
        True if table was created or already exists, False on error
    """
    table_name = get_table_name(symbol)
    
    # Check if table already exists
    if table_exists(table_name, engine_instance):
        logger.debug(f"Table {table_name} already exists, skipping creation")
        return True
    
    try:
        # Generate CREATE TABLE SQL from Python schema
        create_sql = generate_create_table_sql(table_name)
        
        logger.info(f"Creating table {table_name} from Python schema...")
        logger.debug(f"Generated SQL:\n{create_sql}")
        
        # Execute CREATE TABLE
        with engine_instance.connect() as connection:
            connection.execute(text(create_sql))
            connection.commit()
        
        logger.info(f"✅ Table {table_name} created successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to create table {table_name}: {e}", exc_info=True)
        return False


def insert_candles(
    symbol: str,
    candles: List[Dict[str, Any]],
    engine_instance: Engine = engine,
    batch_size: int = 1000
) -> int:
    """
    Insert candles into database table.
    
    CRITICAL: Candle structure must match CANDLE_SCHEMA (Python definition).
    Expected keys: 'time', 'open', 'high', 'low', 'close', 'volume'
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD')
        candles: List of candle dictionaries matching CANDLE_SCHEMA
        engine_instance: SQLAlchemy engine (default: app.database.engine)
        batch_size: Number of candles to insert per batch (default: 1000)
    
    Returns:
        Number of candles successfully inserted
    """
    if not candles:
        logger.warning(f"No candles to insert for {symbol}")
        return 0
    
    table_name = get_table_name(symbol)
    
    # Ensure table exists
    if not create_table_if_not_exists(symbol, engine_instance):
        logger.error(f"Cannot insert candles - table creation failed for {symbol}")
        return 0
    
    # Validate candle structure matches schema
    required_keys = set(CANDLE_SCHEMA.keys())
    invalid_candles = []
    
    for i, candle in enumerate(candles):
        candle_keys = set(candle.keys())
        if not required_keys.issubset(candle_keys):
            missing = required_keys - candle_keys
            invalid_candles.append((i, missing))
    
    if invalid_candles:
        logger.error(f"Invalid candle structure: {len(invalid_candles)} candles missing required keys")
        for idx, missing in invalid_candles[:5]:  # Log first 5
            logger.error(f"  Candle {idx} missing: {missing}")
        return 0
    
    try:
        # Build INSERT statement from schema
        column_names = list(CANDLE_SCHEMA.keys())
        columns_str = ', '.join([f"`{col}`" for col in column_names])
        placeholders = ', '.join([':{}'.format(col) for col in column_names])
        
        insert_sql = f"""
        INSERT INTO `{table_name}` ({columns_str})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE
            `open` = VALUES(`open`),
            `high` = VALUES(`high`),
            `low` = VALUES(`low`),
            `close` = VALUES(`close`),
            `volume` = VALUES(`volume`)
        """
        
        inserted_count = 0
        
        # Insert in batches
        with engine_instance.connect() as connection:
            for i in range(0, len(candles), batch_size):
                batch = candles[i:i + batch_size]
                
                # Prepare batch data
                batch_data = []
                for candle in batch:
                    row = {col: candle.get(col) for col in column_names}
                    batch_data.append(row)
                
                # Execute batch insert
                connection.execute(text(insert_sql), batch_data)
                connection.commit()
                
                inserted_count += len(batch)
                logger.debug(f"Inserted batch {i // batch_size + 1}: {len(batch)} candles")
        
        logger.info(f"✅ Inserted {inserted_count} candles into {table_name}")
        return inserted_count
        
    except Exception as e:
        logger.error(f"❌ Failed to insert candles into {table_name}: {e}", exc_info=True)
        return 0


def get_candles(
    symbol: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: Optional[int] = None,
    engine_instance: Engine = engine
) -> List[Dict[str, Any]]:
    """
    Retrieve candles from database table.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD')
        start_time: Optional start timestamp (Unix seconds)
        end_time: Optional end timestamp (Unix seconds)
        limit: Optional limit on number of candles
        engine_instance: SQLAlchemy engine (default: app.database.engine)
    
    Returns:
        List of candle dictionaries matching CANDLE_SCHEMA structure
    """
    table_name = get_table_name(symbol)
    
    if not table_exists(table_name, engine_instance):
        logger.warning(f"Table {table_name} does not exist")
        return []
    
    try:
        # Build SELECT query
        column_names = list(CANDLE_SCHEMA.keys())
        columns_str = ', '.join([f"`{col}`" for col in column_names])
        
        query = f"SELECT {columns_str} FROM `{table_name}`"
        conditions = []
        params = {}
        
        if start_time is not None:
            conditions.append("`time` >= :start_time")
            params['start_time'] = start_time
        
        if end_time is not None:
            conditions.append("`time` <= :end_time")
            params['end_time'] = end_time
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY `time` ASC"
        
        if limit is not None:
            query += f" LIMIT :limit"
            params['limit'] = limit
        
        # Execute query
        with engine_instance.connect() as connection:
            result = connection.execute(text(query), params)
            rows = result.fetchall()
            
            # Convert rows to dictionaries matching CANDLE_SCHEMA
            candles = []
            for row in rows:
                candle = {col: row[i] for i, col in enumerate(column_names)}
                candles.append(candle)
            
            logger.debug(f"Retrieved {len(candles)} candles from {table_name}")
            return candles
            
    except Exception as e:
        logger.error(f"❌ Failed to retrieve candles from {table_name}: {e}", exc_info=True)
        return []


def get_last_candle(symbol: str, engine_instance: Engine = engine) -> Optional[Dict[str, Any]]:
    """
    Get the last (most recent) candle from database table.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD')
        engine_instance: SQLAlchemy engine (default: app.database.engine)
    
    Returns:
        Last candle dictionary matching CANDLE_SCHEMA structure, or None if no candles exist
    """
    table_name = get_table_name(symbol)
    
    if not table_exists(table_name, engine_instance):
        logger.warning(f"Table {table_name} does not exist")
        return None
    
    try:
        # Build SELECT query for last candle (ORDER BY time DESC, LIMIT 1)
        column_names = list(CANDLE_SCHEMA.keys())
        columns_str = ', '.join([f"`{col}`" for col in column_names])
        
        query = f"SELECT {columns_str} FROM `{table_name}` ORDER BY `time` DESC LIMIT 1"
        
        # Execute query
        with engine_instance.connect() as connection:
            result = connection.execute(text(query))
            row = result.fetchone()
            
            if row:
                # Convert row to dictionary matching CANDLE_SCHEMA
                candle = {col: row[i] for i, col in enumerate(column_names)}
                logger.debug(f"Retrieved last candle from {table_name}: time={candle.get('time')}")
                return candle
            
            return None
            
    except Exception as e:
        logger.error(f"❌ Failed to retrieve last candle from {table_name}: {e}", exc_info=True)
        return None


def delete_candles(
    symbol: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    engine_instance: Engine = engine
) -> int:
    """
    Delete candles from database table within a time range.
    
    CRITICAL: Deletes only matching candles - does NOT drop table.
    Uses transactions for safety.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD')
        start_time: Optional start timestamp (Unix seconds) - if None, deletes all before end_time
        end_time: Optional end timestamp (Unix seconds) - if None, deletes all after start_time
        engine_instance: SQLAlchemy engine (default: app.database.engine)
    
    Returns:
        Number of candles deleted
    """
    table_name = get_table_name(symbol)
    
    if not table_exists(table_name, engine_instance):
        logger.warning(f"Table {table_name} does not exist, nothing to delete")
        return 0
    
    try:
        # Build DELETE query
        query = f"DELETE FROM `{table_name}`"
        conditions = []
        params = {}
        
        if start_time is not None and end_time is not None:
            conditions.append("`time` >= :start_time AND `time` <= :end_time")
            params['start_time'] = start_time
            params['end_time'] = end_time
        elif start_time is not None:
            conditions.append("`time` >= :start_time")
            params['start_time'] = start_time
        elif end_time is not None:
            conditions.append("`time` <= :end_time")
            params['end_time'] = end_time
        else:
            # Safety: Require at least one time constraint
            logger.error("delete_candles requires at least start_time or end_time")
            return 0
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        # Execute delete with transaction
        with engine_instance.connect() as connection:
            result = connection.execute(text(query), params)
            deleted_count = result.rowcount
            connection.commit()
        
        logger.info(f"✅ Deleted {deleted_count} candles from {table_name}")
        return deleted_count
        
    except Exception as e:
        logger.error(f"❌ Failed to delete candles from {table_name}: {e}", exc_info=True)
        return 0

