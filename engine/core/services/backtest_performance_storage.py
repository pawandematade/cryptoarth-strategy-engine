"""
Backtest Performance Storage Service

CRITICAL: Stores precomputed backtest results.
No on-call computation - UI reads stored data only.

Data is written ONLY when:
- Admin triggers backtest
- Cron runs daily backtest

FLOW:
1. Backtest engine computes results
2. Generate unique backtest_run_id
3. Split output into: Summary, Daily, Trades
4. Insert into respective tables with same backtest_run_id
5. Commit transaction

UI reads later - no recalculation.
"""
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, date
from sqlalchemy.orm import Session
from sqlalchemy import and_
from common.db import SessionLocal
from engine.models import (
    StrategyBacktestSummary,
    StrategyBacktestDaily,
    StrategyBacktestTrades,
    TradeSide
)

logger = logging.getLogger(__name__)


def store_backtest_summary(
    db: Session,
    backtest_run_id: str,
    strategy_id: int,
    symbol: str,
    timeframe: str,
    from_time: int,
    to_time: int,
    summary: Dict[str, Any],
    overwrite: bool = True
) -> StrategyBacktestSummary:
    """
    Store backtest summary (one row per completed backtest run).
    
    CRITICAL: Precomputed data only - no on-call computation.
    
    Args:
        db: Database session
        strategy_id: Strategy ID
        symbol: Trading symbol (e.g., "BTCUSD")
        timeframe: Timeframe (e.g., "1h", "15m")
        from_time: Start timestamp (Unix seconds)
        to_time: End timestamp (Unix seconds)
        summary: Summary dict from backtest engine with keys:
            - total_trades, wins, losses, win_rate, net_pnl, max_drawdown, profit_factor
        overwrite: If True, update existing record; if False, create new
    
    Returns:
        Created/Updated StrategyBacktestSummary record
    """
    try:
        # Check if summary already exists
        existing = db.query(StrategyBacktestSummary).filter(
            and_(
                StrategyBacktestSummary.strategy_id == strategy_id,
                StrategyBacktestSummary.symbol == symbol,
                StrategyBacktestSummary.timeframe == timeframe,
                StrategyBacktestSummary.from_time == from_time,
                StrategyBacktestSummary.to_time == to_time
            )
        ).first()
        
        if existing and overwrite:
            # Update existing record
            existing.backtest_run_id = backtest_run_id
            existing.total_trades = summary.get('total_trades', 0)
            existing.winning_trades = summary.get('wins', 0)
            existing.losing_trades = summary.get('losses', 0)
            existing.net_pnl = summary.get('net_pnl')
            existing.max_drawdown = summary.get('max_drawdown')
            existing.win_rate = summary.get('win_rate')
            existing.profit_factor = summary.get('profit_factor')
            
            db.flush()
            logger.debug(f"Updated backtest summary for strategy {strategy_id} {symbol} (run_id: {backtest_run_id})")
            return existing
        elif existing and not overwrite:
            # Skip if exists and overwrite=False
            logger.debug(f"Backtest summary already exists for strategy {strategy_id} {symbol}, skipping")
            return existing
        else:
            # Create new record
            summary_record = StrategyBacktestSummary(
                backtest_run_id=backtest_run_id,
                strategy_id=strategy_id,
                symbol=symbol,
                timeframe=timeframe,
                from_time=from_time,
                to_time=to_time,
                total_trades=summary.get('total_trades', 0),
                winning_trades=summary.get('wins', 0),
                losing_trades=summary.get('losses', 0),
                net_pnl=summary.get('net_pnl'),
                max_drawdown=summary.get('max_drawdown'),
                win_rate=summary.get('win_rate'),
                profit_factor=summary.get('profit_factor')
            )
            
            db.add(summary_record)
            db.flush()
            logger.debug(f"Created backtest summary for strategy {strategy_id} {symbol}")
            return summary_record
            
    except Exception as e:
        logger.error(f"❌ Failed to store backtest summary: {e}", exc_info=True)
        raise


def store_backtest_daily(
    db: Session,
    backtest_run_id: str,
    strategy_id: int,
    symbol: str,
    daily_data: List[Dict[str, Any]],
    overwrite: bool = True
) -> int:
    """
    Store daily performance data (one row per strategy per day).
    
    CRITICAL: Precomputed data only - no on-call computation.
    
    Args:
        db: Database session
        strategy_id: Strategy ID
        symbol: Trading symbol (e.g., "BTCUSD")
        daily_data: List of daily performance dicts with keys:
            - date (datetime or date), daily_pnl, cumulative_pnl, drawdown
        overwrite: If True, update existing records; if False, skip existing
    
    Returns:
        Number of records inserted/updated
    """
    try:
        inserted_count = 0
        
        for day_data in daily_data:
            # Extract date
            day_date = day_data.get('date')
            if isinstance(day_date, datetime):
                day_date_obj = day_date.date() if hasattr(day_date, 'date') else day_date
            elif isinstance(day_date, date):
                day_date_obj = day_date
            elif isinstance(day_date, str):
                # Parse string date
                day_date_obj = datetime.fromisoformat(day_date.replace('Z', '+00:00')).date()
            else:
                logger.warning(f"Invalid date format in daily_data: {day_date}")
                continue
            
            # Check if record exists (date field is Date type, not DateTime)
            existing = db.query(StrategyBacktestDaily).filter(
                and_(
                    StrategyBacktestDaily.strategy_id == strategy_id,
                    StrategyBacktestDaily.symbol == symbol,
                    StrategyBacktestDaily.date == day_date_obj
                )
            ).first()
            
            if existing and overwrite:
                # Update existing record
                existing.backtest_run_id = backtest_run_id
                existing.daily_pnl = day_data.get('daily_pnl')
                existing.cumulative_pnl = day_data.get('cumulative_pnl')
                existing.drawdown = day_data.get('drawdown')
                inserted_count += 1
            elif existing and not overwrite:
                # Skip if exists and overwrite=False
                continue
            else:
                # Create new record (date field is Date type)
                daily_record = StrategyBacktestDaily(
                    backtest_run_id=backtest_run_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    date=day_date_obj,
                    daily_pnl=day_data.get('daily_pnl'),
                    cumulative_pnl=day_data.get('cumulative_pnl'),
                    drawdown=day_data.get('drawdown')
                )
                db.add(daily_record)
                inserted_count += 1
        
        db.flush()
        logger.debug(f"Stored {inserted_count} daily performance records for strategy {strategy_id} {symbol}")
        return inserted_count
        
    except Exception as e:
        logger.error(f"❌ Failed to store backtest daily data: {e}", exc_info=True)
        raise


def store_backtest_trades(
    db: Session,
    backtest_run_id: str,
    strategy_id: int,
    symbol: str,
    trades: List[Dict[str, Any]],
    candles_df=None,
    candles_list: Optional[List[Dict[str, Any]]] = None,
    overwrite: bool = True
) -> int:
    """
    Store trade-by-trade details.
    
    CRITICAL: Large table - must support pagination.
    Precomputed data only - no on-call computation.
    
    Args:
        db: Database session
        strategy_id: Strategy ID
        symbol: Trading symbol (e.g., "BTCUSD")
        trades: List of trade dicts from backtest engine with keys:
            - direction, entry_price, exit_price, entry_index, exit_index,
              pnl, result, entry_reason, exit_reason
        candles_df: Optional pandas DataFrame with candles (for timestamp conversion)
        candles_list: Optional list of candle dicts with 'time' field (preferred for timestamp extraction)
        overwrite: If True, delete old trades and insert new; if False, skip if exists
    
    Returns:
        Number of trades inserted
    """
    try:
        # If overwrite=True, delete existing trades for this strategy/symbol/date range
        if overwrite and trades:
            # Extract time range from trades
            # Note: We'll delete trades that overlap with the new trade time range
            # For simplicity, delete all trades for this strategy/symbol (can be optimized later)
            deleted_count = db.query(StrategyBacktestTrades).filter(
                and_(
                    StrategyBacktestTrades.strategy_id == strategy_id,
                    StrategyBacktestTrades.symbol == symbol
                )
            ).delete()
            
            if deleted_count > 0:
                logger.debug(f"Deleted {deleted_count} existing trades for strategy {strategy_id} {symbol}")
        
        inserted_count = 0
        
        for trade in trades:
            # Extract trade data
            direction = trade.get('direction', 'BUY')
            entry_price = trade.get('entry_price')
            exit_price = trade.get('exit_price')
            entry_index = trade.get('entry_index')
            exit_index = trade.get('exit_index')
            pnl = trade.get('pnl', 0.0)
            exit_reason = trade.get('exit_reason', '')
            
            # Convert entry/exit indices to timestamps
            entry_time = None
            exit_time = None
            
            if entry_index is not None and exit_index is not None:
                try:
                    # Priority 1: Try to get from candles_list (original candles with 'time' field)
                    if candles_list and isinstance(candles_list, list) and len(candles_list) > 0:
                        if entry_index < len(candles_list) and exit_index < len(candles_list):
                            entry_timestamp = candles_list[entry_index].get('time')
                            exit_timestamp = candles_list[exit_index].get('time')
                            
                            if entry_timestamp:
                                entry_time = datetime.fromtimestamp(entry_timestamp, tz=timezone.utc)
                            if exit_timestamp:
                                exit_time = datetime.fromtimestamp(exit_timestamp, tz=timezone.utc)
                    
                    # Priority 2: Try to get from candles_df if 'time' column exists
                    if (not entry_time or not exit_time) and candles_df is not None:
                        if 'time' in candles_df.columns:
                            if not entry_time:
                                entry_timestamp = candles_df.iloc[entry_index]['time']
                                if isinstance(entry_timestamp, (int, float)):
                                    entry_time = datetime.fromtimestamp(entry_timestamp, tz=timezone.utc)
                            
                            if not exit_time:
                                exit_timestamp = candles_df.iloc[exit_index]['time']
                                if isinstance(exit_timestamp, (int, float)):
                                    exit_time = datetime.fromtimestamp(exit_timestamp, tz=timezone.utc)
                    
                    # Fallback: use current time if timestamps not available
                    if not entry_time:
                        entry_time = datetime.now(timezone.utc)
                    if not exit_time:
                        exit_time = datetime.now(timezone.utc)
                        
                except Exception as e:
                    logger.warning(f"Could not convert trade indices to timestamps: {e}")
                    # Fallback: use current time
                    entry_time = datetime.now(timezone.utc)
                    exit_time = datetime.now(timezone.utc)
            else:
                # Fallback: use current time if indices not available
                entry_time = datetime.now(timezone.utc)
                exit_time = datetime.now(timezone.utc)
            
            # Calculate holding time
            holding_time_seconds = None
            if entry_time and exit_time:
                holding_time_seconds = int((exit_time - entry_time).total_seconds())
            
            # Calculate PnL percentage
            pnl_percent = None
            if entry_price and entry_price > 0:
                pnl_percent = (pnl / entry_price) * 100
            
            # Determine quantity (default to 1.0 if not provided)
            quantity = trade.get('quantity', 1.0)
            
            # Create trade record
            trade_record = StrategyBacktestTrades(
                backtest_run_id=backtest_run_id,
                strategy_id=strategy_id,
                symbol=symbol,
                entry_time=entry_time,
                exit_time=exit_time,
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=quantity,
                side=TradeSide.BUY if direction.upper() == 'BUY' else TradeSide.SELL,
                pnl=pnl,
                pnl_percent=pnl_percent,
                exit_reason=exit_reason,
                holding_time_seconds=holding_time_seconds
            )
            
            db.add(trade_record)
            inserted_count += 1
        
        db.flush()
        logger.debug(f"Stored {inserted_count} trades for strategy {strategy_id} {symbol}")
        return inserted_count
        
    except Exception as e:
        logger.error(f"❌ Failed to store backtest trades: {e}", exc_info=True)
        raise


def store_backtest_results(
    strategy_id: int,
    symbol: str,
    timeframe: str,
    from_time: int,
    to_time: int,
    backtest_results: Dict[str, Any],
    candles_df=None,
    candles_list: Optional[List[Dict[str, Any]]] = None,
    overwrite: bool = True,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Store complete backtest results (summary, daily, trades) in a single transaction.
    
    CRITICAL: This is the main entry point for storing backtest performance data.
    All writes happen in a single transaction for data consistency.
    
    Args:
        strategy_id: Strategy ID
        symbol: Trading symbol (e.g., "BTCUSD")
        timeframe: Timeframe (e.g., "1h", "15m")
        from_time: Start timestamp (Unix seconds)
        to_time: End timestamp (Unix seconds)
        backtest_results: Backtest results dict from BacktestEngine with keys:
            - summary: Dict with total_trades, wins, losses, win_rate, net_pnl, max_drawdown, profit_factor
            - trades: List of trade dicts
        candles_df: Optional pandas DataFrame with candles (for timestamp conversion in trades)
        candles_list: Optional list of candle dicts with 'time' field (preferred for timestamp extraction)
        overwrite: If True, update existing records; if False, skip existing
        db: Optional database session (creates new if not provided)
    
    Returns:
        Dict with storage results:
        {
            "summary_stored": bool,
            "daily_stored": int,  # count
            "trades_stored": int,  # count
            "success": bool
        }
    """
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    
    try:
        # Generate unique backtest_run_id for this run
        backtest_run_id = str(uuid.uuid4())
        logger.debug(f"Generated backtest_run_id: {backtest_run_id} for strategy {strategy_id} {symbol}")
        
        # Extract data from backtest results
        summary = backtest_results.get('summary', {})
        trades = backtest_results.get('trades', [])
        
        # Calculate daily performance from trades
        daily_data = _calculate_daily_performance(trades, candles_list or candles_df)
        
        # Store in transaction (all with same backtest_run_id)
        summary_record = store_backtest_summary(
            db, backtest_run_id, strategy_id, symbol, timeframe, from_time, to_time, summary, overwrite
        )
        
        daily_count = store_backtest_daily(
            db, backtest_run_id, strategy_id, symbol, daily_data, overwrite
        )
        
        trades_count = store_backtest_trades(
            db, backtest_run_id, strategy_id, symbol, trades, candles_df, candles_list, overwrite
        )
        
        # Commit transaction
        db.commit()
        
        logger.info(
            f"✅ Stored backtest results for strategy {strategy_id} {symbol} "
            f"(run_id: {backtest_run_id}): summary=1, daily={daily_count}, trades={trades_count}"
        )
        
        return {
            "backtest_run_id": backtest_run_id,
            "summary_stored": summary_record is not None,
            "daily_stored": daily_count,
            "trades_stored": trades_count,
            "success": True
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to store backtest results: {e}", exc_info=True)
        raise
    
    finally:
        if should_close:
            db.close()


def _calculate_daily_performance(
    trades: List[Dict[str, Any]],
    candles_data=None
) -> List[Dict[str, Any]]:
    """
    Calculate daily performance from trades.
    
    Args:
        trades: List of trade dicts
        candles_data: Optional pandas DataFrame or list of candle dicts (for date extraction)
    
    Returns:
        List of daily performance dicts with keys: date, daily_pnl, cumulative_pnl, drawdown
    """
    if not trades:
        return []
    
    # Group trades by date
    daily_pnl_map = {}  # date -> daily_pnl
    cumulative_pnl = 0.0
    peak_pnl = 0.0
    
    for trade in trades:
        # Extract trade date from exit_time or entry_time
        trade_date = None
        
        if candles_data is not None:
            exit_index = trade.get('exit_index')
            if exit_index is not None:
                try:
                    # Priority 1: Try candles_list (list of dicts with 'time' field)
                    if isinstance(candles_data, list) and len(candles_data) > exit_index:
                        trade_timestamp = candles_data[exit_index].get('time')
                        if trade_timestamp:
                            trade_date = datetime.fromtimestamp(trade_timestamp, tz=timezone.utc).date()
                    # Priority 2: Try candles_df (DataFrame with 'time' column)
                    elif hasattr(candles_data, 'columns') and 'time' in candles_data.columns:
                        trade_timestamp = candles_data.iloc[exit_index]['time']
                        if trade_timestamp:
                            trade_date = datetime.fromtimestamp(trade_timestamp, tz=timezone.utc).date()
                except Exception as e:
                    logger.debug(f"Could not extract trade date from candles_data: {e}")
                    pass
        
        # Fallback: use current date if date extraction fails
        if not trade_date:
            trade_date = datetime.now(timezone.utc).date()
        
        # Accumulate daily PnL
        pnl = trade.get('pnl', 0.0)
        if trade_date not in daily_pnl_map:
            daily_pnl_map[trade_date] = 0.0
        daily_pnl_map[trade_date] += pnl
    
    # Build daily performance list
    daily_data = []
    sorted_dates = sorted(daily_pnl_map.keys())
    
    for day_date in sorted_dates:
        daily_pnl = daily_pnl_map[day_date]
        cumulative_pnl += daily_pnl
        
        if cumulative_pnl > peak_pnl:
            peak_pnl = cumulative_pnl
        
        drawdown = peak_pnl - cumulative_pnl
        
        daily_data.append({
            'date': day_date,
            'daily_pnl': daily_pnl,
            'cumulative_pnl': cumulative_pnl,
            'drawdown': drawdown
        })
    
    return daily_data

