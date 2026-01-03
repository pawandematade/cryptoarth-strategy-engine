"""
Daily Backtest Cron - Updates backtest candle data daily

CRON NAME FORMAT: DAILY_BACKTEST_<SYMBOL>
Examples: DAILY_BACKTEST_BTCUSD, DAILY_BACKTEST_ETHUSD

WHAT THIS CRON DOES:
1. Finds last available candle in DB for symbol
2. Fetches missing candles from Delta Exchange till today
3. Inserts using backtest_candle_storage service
4. Updates cron_master status

MUST be idempotent (re-run should not duplicate data).
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from engine.core.services.backtest_candle_storage import (
    get_candles,
    insert_candles,
    create_table_if_not_exists,
    get_table_name,
    get_last_candle
)
from engine.core.feed.delta_history import fetch_ohlcv

logger = logging.getLogger(__name__)

# Default timeframe for daily backtest updates
DEFAULT_TIMEFRAME = "1h"


def get_last_candle_time(symbol: str) -> Optional[int]:
    """
    Get the timestamp of the last available candle in database.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSD")
    
    Returns:
        Unix timestamp of last candle, or None if no candles exist
    """
    try:
        # Get last candle directly (more efficient)
        last_candle = get_last_candle(symbol)
        
        if not last_candle:
            return None
        
        return last_candle.get('time')
        
    except Exception as e:
        logger.error(f"Error getting last candle time for {symbol}: {e}")
        return None


def run_daily_backtest_cron(symbol: str, timeframe: str = DEFAULT_TIMEFRAME) -> Dict[str, Any]:
    """
    Execute daily backtest cron for a symbol.
    
    CRITICAL: This function is called by cron_service.execute_cron().
    It follows the lifecycle contract (RUNNING → SUCCESS/FAILED).
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSD")
        timeframe: Timeframe for candles (default: "1h")
    
    Returns:
        Dict with execution result
    
    Raises:
        Exception: If cron execution fails (will be caught by cron_service)
    """
    logger.info(f"🔄 Starting daily backtest cron for {symbol} (timeframe: {timeframe})")
    
    # Ensure table exists
    if not create_table_if_not_exists(symbol):
        raise Exception(f"Failed to create table for symbol {symbol}")
    
    # Get last candle timestamp from DB
    last_candle_time = get_last_candle_time(symbol)
    
    # Calculate time range
    now = datetime.now(timezone.utc)
    end_time = int(now.timestamp())
    
    if last_candle_time:
        # Start from last candle + 1 interval to avoid duplicates
        # For 1h timeframe, add 3600 seconds
        from engine.core.feed.delta_history import _get_timeframe_seconds
        interval_seconds = _get_timeframe_seconds(timeframe)
        if interval_seconds > 0:
            start_time = last_candle_time + interval_seconds
        else:
            # Fallback: add 1 hour if interval cannot be determined
            start_time = last_candle_time + 3600
        
        logger.info(
            f"📊 Last candle found: {datetime.fromtimestamp(last_candle_time)} "
            f"(fetching from {datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)})"
        )
    else:
        # No candles in DB - fetch last 7 days as initial load
        start_time = int((now - timedelta(days=7)).timestamp())
        logger.info(
            f"📊 No existing candles - initial load: "
            f"fetching last 7 days ({datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)})"
        )
    
    # Validate time range
    if start_time >= end_time:
        logger.info(f"✅ No new candles to fetch for {symbol} (already up to date)")
        return {
            "symbol": symbol,
            "candles_inserted": 0,
            "message": "No new candles to fetch - already up to date"
        }
    
    # Fetch candles from Delta Exchange
    logger.info(f"📥 Fetching candles from Delta Exchange: {symbol} {timeframe}")
    candles = fetch_ohlcv(
        symbol=symbol,
        resolution=timeframe,
        start=start_time,
        end=end_time,
        auto_map=True
    )
    
    if not candles:
        logger.warning(f"⚠️ No candles fetched from Delta Exchange for {symbol}")
        return {
            "symbol": symbol,
            "candles_inserted": 0,
            "message": "No candles available from Delta Exchange"
        }
    
    logger.info(f"📥 Fetched {len(candles)} candles from Delta Exchange")
    
    # Filter out candles that might already exist (idempotency check)
    existing_candles = get_candles(symbol, start_time=start_time, end_time=end_time)
    existing_times = {candle['time'] for candle in existing_candles}
    
    new_candles = [c for c in candles if c['time'] not in existing_times]
    skipped_count = len(candles) - len(new_candles)
    
    if skipped_count > 0:
        logger.info(f"⏭️ Skipping {skipped_count} candles that already exist (idempotency)")
    
    if not new_candles:
        logger.info(f"✅ No new candles to insert for {symbol} (all already exist)")
        return {
            "symbol": symbol,
            "candles_inserted": 0,
            "candles_skipped": skipped_count,
            "message": "No new candles to insert - all already exist"
        }
    
    # Insert new candles
    logger.info(f"💾 Inserting {len(new_candles)} new candles into database")
    inserted_count = insert_candles(symbol, new_candles)
    
    logger.info(
        f"✅ Daily backtest cron completed for {symbol}: "
        f"inserted {inserted_count} candles, skipped {skipped_count}"
    )
    
    return {
        "symbol": symbol,
        "candles_inserted": inserted_count,
        "candles_skipped": skipped_count,
        "total_fetched": len(candles),
        "message": f"Successfully inserted {inserted_count} candles"
    }


def get_daily_backtest_cron_name(symbol: str) -> str:
    """
    Generate cron name for daily backtest.
    
    Format: DAILY_BACKTEST_<SYMBOL>
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSD")
    
    Returns:
        Cron name (e.g., "DAILY_BACKTEST_BTCUSD")
    """
    return f"DAILY_BACKTEST_{symbol.upper()}"

