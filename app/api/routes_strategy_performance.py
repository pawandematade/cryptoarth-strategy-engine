"""
Strategy Performance API

Read-only API for fetching strategy performance metrics.
Uses StrategyRunner and BacktestEngine - does NOT modify them.

Supports:
- BACKTEST mode: Runs BacktestEngine on historical candles
- LIVE mode: Reads runtime performance metrics
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging
import pandas as pd
from datetime import datetime, timedelta
import json
import copy

from app.engine.backtest_engine import BacktestEngine
from app.store.redis_client import redis_client
from app.strategies.loader import load_strategies
from app.feed.delta_history import fetch_ohlcv

logger = logging.getLogger(__name__)

router = APIRouter()

# Timeframe mapping: strategy timeframe -> Delta Exchange resolution
TIMEFRAME_MAP = {
    '1MIN': '1',
    '3M': '3',
    '5MIN': '5',
    '15MIN': '15',
    '30MIN': '30',
    '1H': '60',
    '4H': '240',
    '1D': '1D',
    '1W': '1W',
    '1M': '1M'
}

# Cache TTL (15 minutes)
CACHE_TTL = 900  # seconds


class PerformanceResponse(BaseModel):
    """Response model for strategy performance"""
    success: bool
    mode: str  # "BACKTEST" | "LIVE"
    summary: Dict[str, Any]
    trades: List[Dict[str, Any]]
    monthly_performance: Optional[Dict[str, Any]] = None  # Year → Month → Day grouping


def _group_trades_by_date(trades: List[Dict[str, Any]], candles_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Group trades by Year → Month → Day.
    
    Args:
        trades: List of trade dicts with entry_index and exit_index
        candles_list: List of candle dicts with 'time' field (Unix timestamp)
    
    Returns:
        Nested dict structure:
        {
            "2024": {
                "01": {  # January
                    "01": [trade1, trade2, ...],  # Day 1
                    "02": [trade3, ...],
                    ...
                    "summary": {
                        "total_trades": int,
                        "wins": int,
                        "losses": int,
                        "net_pnl": float
                    }
                },
                "02": { ... },  # February
                ...
            }
        }
    """
    if not trades or not candles_list:
        return {}
    
    # Create index to timestamp mapping
    index_to_timestamp = {}
    for idx, candle in enumerate(candles_list):
        if idx < len(candles_list):
            index_to_timestamp[idx] = candle.get('time', 0)
    
    # Group trades by date
    grouped = {}
    
    for trade in trades:
        # Get entry timestamp (use entry_index to map to candle time)
        entry_index = trade.get('entry_index', 0)
        entry_timestamp = index_to_timestamp.get(entry_index, 0)
        
        if entry_timestamp == 0:
            # Skip trades without valid timestamp
            continue
        
        # Convert timestamp to datetime
        try:
            entry_dt = datetime.fromtimestamp(entry_timestamp)
        except (ValueError, OSError):
            continue
        
        # Extract year, month, day
        year = str(entry_dt.year)
        month = entry_dt.strftime('%m')  # 01-12
        day = entry_dt.strftime('%d')    # 01-31
        
        # Initialize nested structure
        if year not in grouped:
            grouped[year] = {}
        if month not in grouped[year]:
            grouped[year][month] = {}
        if day not in grouped[year][month]:
            grouped[year][month][day] = []
        
        # Add trade to day
        grouped[year][month][day].append(trade)
    
    # Compute month-level summaries
    for year in grouped:
        for month in grouped[year]:
            month_trades = []
            # Collect all trades from all days in this month
            for day in grouped[year][month]:
                if day != 'summary':  # Skip summary key
                    month_trades.extend(grouped[year][month][day])
            
            # Compute month summary
            wins = sum(1 for t in month_trades if t.get('result') == 'WIN')
            losses = sum(1 for t in month_trades if t.get('result') == 'LOSS')
            net_pnl = sum(float(t.get('pnl', 0)) for t in month_trades)
            
            grouped[year][month]['summary'] = {
                'total_trades': len(month_trades),
                'wins': wins,
                'losses': losses,
                'net_pnl': round(net_pnl, 2)
            }
    
    return grouped


def _convert_candles_to_dataframe(candles: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Convert candles list to pandas DataFrame.
    
    Args:
        candles: List of candle dicts with keys: time, open, high, low, close, volume
    
    Returns:
        DataFrame with columns: open, high, low, close, volume (sorted ascending by time)
    """
    if not candles:
        return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
    
    # Sort candles by time (ascending) to ensure correct order
    # Do NOT trust exchange ordering blindly
    sorted_candles = sorted(candles, key=lambda c: c.get('time', 0))
    
    # Extract OHLCV data
    data = {
        'open': [float(c['open']) for c in sorted_candles],
        'high': [float(c['high']) for c in sorted_candles],
        'low': [float(c['low']) for c in sorted_candles],
        'close': [float(c['close']) for c in sorted_candles],
        'volume': [float(c.get('volume', 0)) for c in sorted_candles]
    }
    
    df = pd.DataFrame(data)
    # Reset index to ensure clean 0-based sequential index
    df = df.reset_index(drop=True)
    
    return df


def _get_strategy_by_id(strategy_id: int) -> Optional[Dict[str, Any]]:
    """
    Load strategy by ID from strategies.json.
    
    Args:
        strategy_id: Strategy ID
    
    Returns:
        Strategy dict or None if not found
    """
    try:
        strategies = load_strategies()
        strategy = next((s for s in strategies if s.get("id") == strategy_id), None)
        return strategy
    except Exception as e:
        logger.error(f"Error loading strategy {strategy_id}: {e}")
        return None


def _fetch_historical_candles(
    symbol: str,
    timeframe: str,
    days: int = 30
) -> List[Dict[str, Any]]:
    """
    Fetch historical candles for backtesting.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD')
        timeframe: Strategy timeframe (e.g., '15MIN', '1H')
        days: Number of days of history to fetch
    
    Returns:
        List of candle dictionaries
    """
    try:
        # Map strategy timeframe to Delta Exchange resolution
        resolution = TIMEFRAME_MAP.get(timeframe, '60')  # Default to 1H
        
        # Calculate timestamps
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        start_timestamp = int(start_time.timestamp())
        end_timestamp = int(end_time.timestamp())
        
        logger.info(f"Fetching candles for {symbol}: {timeframe} ({resolution}) from {start_time} to {end_time}")
        
        # Fetch candles
        candles = fetch_ohlcv(symbol, resolution, start_timestamp, end_timestamp)
        
        if not candles:
            logger.warning(f"No candles returned for {symbol} {timeframe}")
            return []
        
        logger.info(f"Fetched {len(candles)} candles for {symbol}")
        return candles
        
    except Exception as e:
        logger.error(f"Error fetching historical candles: {e}", exc_info=True)
        return []


def _get_cached_performance(strategy_id: int) -> Optional[Dict[str, Any]]:
    """
    Get cached performance from Redis.
    
    Args:
        strategy_id: Strategy ID
    
    Returns:
        Cached performance dict with mode, summary, trades or None
    """
    try:
        cache_key = f"STRATEGY_PERF:{strategy_id}"
        cached_data = redis_client.get(cache_key)
        if cached_data:
            cached_perf = json.loads(cached_data)
            # Ensure cached data has mode field
            if 'mode' not in cached_perf:
                cached_perf['mode'] = 'BACKTEST'  # Default for legacy cache entries
            return cached_perf
        return None
    except Exception as e:
        logger.warning(f"Error reading cache for strategy {strategy_id}: {e}")
        return None


def _cache_performance(strategy_id: int, performance: Dict[str, Any]) -> None:
    """
    Cache performance result in Redis.
    
    Args:
        strategy_id: Strategy ID
        performance: Performance dict to cache
    """
    try:
        cache_key = f"STRATEGY_PERF:{strategy_id}"
        redis_client.setex(
            cache_key,
            CACHE_TTL,
            json.dumps(performance)
        )
        logger.info(f"Cached performance for strategy {strategy_id}")
    except Exception as e:
        logger.warning(f"Error caching performance for strategy {strategy_id}: {e}")


def _get_live_performance(strategy_id: int) -> Optional[Dict[str, Any]]:
    """
    Get live performance metrics from runtime store.
    
    Args:
        strategy_id: Strategy ID
    
    Returns:
        Live performance dict or None if not available
    """
    try:
        # Check Redis for live metrics
        metrics_key = f"STRATEGY_METRICS:{strategy_id}"
        metrics_data = redis_client.get(metrics_key)
        
        if metrics_data:
            return json.loads(metrics_data)
        
        # If no live metrics found, return None (will fall back to backtest)
        return None
    except Exception as e:
        logger.warning(f"Error reading live metrics for strategy {strategy_id}: {e}")
        return None


def _run_backtest(strategy: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run BacktestEngine on strategy.
    
    Args:
        strategy: Strategy JSON (single source of truth)
    
    Returns:
        Backtest results dict with mode field and monthly_performance
    """
    try:
        # STRATEGY IMMUTABILITY: Deep copy strategy before passing to BacktestEngine
        # Never allow mutation of original strategy object
        strategy_copy = copy.deepcopy(strategy)
        
        # Extract symbol and timeframe
        symbol = strategy_copy.get('symbol', 'BTCUSD')
        meta = strategy_copy.get('meta', {})
        
        # Get timeframe from multiple possible locations
        timeframe = (
            meta.get('timeframe') or
            strategy_copy.get('userParams', {}).get('timeframe') or
            strategy_copy.get('timeframe') or
            '15MIN'  # Default fallback
        )
        
        # Validate timeframe is present (even if defaulted)
        if not timeframe or (timeframe == '15MIN' and not meta.get('timeframe') and not strategy_copy.get('userParams', {}).get('timeframe')):
            logger.warning(f"Strategy missing explicit timeframe, using default: {timeframe}")
        
        # Ensure timeframe is in meta for consistency
        if not meta.get('timeframe'):
            meta['timeframe'] = timeframe
            strategy_copy['meta'] = meta
        
        # Fetch historical candles (keep original list for timestamp mapping)
        candles_list = _fetch_historical_candles(symbol, timeframe, days=365)  # 1 year for monthly view
        
        if not candles_list:
            # Log detailed error for debugging (backend only) - WARNING, not ERROR
            logger.warning(f"No historical candles available for {symbol} {timeframe} - Delta Exchange returned empty response")
            # Return structured error response (broker-agnostic) - DO NOT raise exception
            return {
                "success": False,
                "error": {
                    "code": "NO_HISTORICAL_DATA",
                    "message": "Backtest data is not available for the selected symbol and timeframe. Please try a different timeframe or symbol."
                }
            }
        
        # Convert to DataFrame (with order safety)
        candles_df = _convert_candles_to_dataframe(candles_list)
        
        if len(candles_df) == 0:
            # Log detailed error for debugging (backend only) - WARNING, not ERROR
            logger.warning(f"Empty candles DataFrame for {symbol} {timeframe} after conversion")
            # Return structured error response (broker-agnostic) - DO NOT raise exception
            return {
                "success": False,
                "error": {
                    "code": "NO_HISTORICAL_DATA",
                    "message": "Backtest data is not available for the selected symbol and timeframe. Please try a different timeframe or symbol."
                }
            }
        
        # Run BacktestEngine (immutable - doesn't modify strategy_copy or candles_df)
        try:
            engine = BacktestEngine(strategy_copy)
            results = engine.run(candles_df)
        except Exception as e:
            # BacktestEngine error - log but return structured error response (don't crash)
            logger.error(f"BacktestEngine error for {symbol} {timeframe}: {e}", exc_info=True)
            return {
                "success": False,
                "error": {
                    "code": "BACKTEST_ENGINE_ERROR",
                    "message": "An error occurred while running the backtest. Please try again or contact support."
                }
            }
        
        # Group trades by date (Year → Month → Day)
        # Use original candles_list to map indices to timestamps
        monthly_perf = _group_trades_by_date(results.get('trades', []), candles_list)
        
        # Add mode and monthly_performance to results
        results['mode'] = 'BACKTEST'
        results['monthly_performance'] = monthly_perf
        results['success'] = True  # Mark as successful
        
        return results
        
    except Exception as e:
        # Catch any unexpected errors and return structured response (don't crash server)
        logger.error(f"Unexpected error running backtest: {e}", exc_info=True)
        return {
            "success": False,
            "error": {
                "code": "UNEXPECTED_ERROR",
                "message": "An unexpected error occurred. Please try again or contact support."
            }
        }


class BacktestSettingsRequest(BaseModel):
    """Request model for backtest settings"""
    backtest_settings: Optional[Dict[str, Any]] = None


def _apply_brokerage_to_performance(
    performance: Dict[str, Any],
    backtest_settings: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Apply brokerage and capital calculations to performance results.
    
    This is a TRANSFORMER - it modifies the display values only.
    Does NOT modify StrategyRunner or BacktestEngine outputs.
    
    Calculates BOTH Maker and Taker brokerage scenarios.
    
    Args:
        performance: Performance dict with summary and trades
        backtest_settings: Dict with initialCapital, leverage, capitalPerTrade (NO orderType)
    
    Returns:
        Transformed performance dict with brokerage applied (both maker and taker)
    """
    if not backtest_settings:
        return performance
    
    initial_capital = float(backtest_settings.get('initialCapital', 100000))
    leverage = float(backtest_settings.get('leverage', 1))
    capital_per_trade_pct = float(backtest_settings.get('capitalPerTrade', 10)) / 100.0
    
    # Brokerage rates
    maker_rate = 0.0002  # 0.02%
    taker_rate = 0.0005  # 0.05%
    
    # Capital per trade
    capital_per_trade = initial_capital * capital_per_trade_pct
    
    # Transform trades - calculate for both maker and taker
    transformed_trades = []
    total_brokerage_maker = 0.0
    total_brokerage_taker = 0.0
    gross_pnl_currency = 0.0
    
    for trade in performance.get('trades', []):
        entry_price = float(trade.get('entry_price', 0))
        exit_price = float(trade.get('exit_price', 0))
        direction = trade.get('direction', 'BUY')
        pnl_points = float(trade.get('pnl', 0))
        
        # Calculate position size (in units)
        # Position size = capital × leverage × (capital_percent / 100)
        leveraged_capital = capital_per_trade * leverage
        position_size = leveraged_capital / entry_price if entry_price > 0 else 0
        
        # Calculate gross PnL in currency (before brokerage)
        gross_pnl_trade = pnl_points * position_size
        gross_pnl_currency += gross_pnl_trade
        
        # Calculate brokerage for Maker (0.02%)
        entry_brokerage_maker = leveraged_capital * maker_rate
        exit_brokerage_maker = position_size * exit_price * maker_rate
        trade_brokerage_maker = entry_brokerage_maker + exit_brokerage_maker
        total_brokerage_maker += trade_brokerage_maker
        
        # Calculate brokerage for Taker (0.05%)
        entry_brokerage_taker = leveraged_capital * taker_rate
        exit_brokerage_taker = position_size * exit_price * taker_rate
        trade_brokerage_taker = entry_brokerage_taker + exit_brokerage_taker
        total_brokerage_taker += trade_brokerage_taker
        
        # Calculate Net PnL for both scenarios
        net_pnl_maker = gross_pnl_trade - trade_brokerage_maker
        net_pnl_taker = gross_pnl_trade - trade_brokerage_taker
        
        # Create transformed trade
        transformed_trade = trade.copy()
        transformed_trade['pnl_points'] = pnl_points  # Keep original points
        transformed_trade['gross_pnl_currency'] = round(gross_pnl_trade, 2)
        transformed_trade['brokerage_maker'] = round(trade_brokerage_maker, 2)
        transformed_trade['brokerage_taker'] = round(trade_brokerage_taker, 2)
        transformed_trade['net_pnl_maker'] = round(net_pnl_maker, 2)
        transformed_trade['net_pnl_taker'] = round(net_pnl_taker, 2)
        transformed_trade['position_size'] = round(position_size, 4)
        
        transformed_trades.append(transformed_trade)
    
    # Transform summary
    summary = performance.get('summary', {}).copy()
    
    # Calculate net PnL in currency for both scenarios
    net_pnl_currency_maker = gross_pnl_currency - total_brokerage_maker
    net_pnl_currency_taker = gross_pnl_currency - total_brokerage_taker
    
    # Update summary with currency values
    summary['gross_pnl_currency'] = round(gross_pnl_currency, 2)
    summary['net_pnl_currency_maker'] = round(net_pnl_currency_maker, 2)
    summary['net_pnl_currency_taker'] = round(net_pnl_currency_taker, 2)
    summary['total_brokerage_maker'] = round(total_brokerage_maker, 2)
    summary['total_brokerage_taker'] = round(total_brokerage_taker, 2)
    summary['net_pnl_points'] = summary.get('net_pnl', 0)  # Keep original points
    summary['initial_capital'] = initial_capital
    summary['final_capital_maker'] = round(initial_capital + net_pnl_currency_maker, 2)
    summary['final_capital_taker'] = round(initial_capital + net_pnl_currency_taker, 2)
    summary['return_pct_maker'] = round((net_pnl_currency_maker / initial_capital) * 100, 2) if initial_capital > 0 else 0
    summary['return_pct_taker'] = round((net_pnl_currency_taker / initial_capital) * 100, 2) if initial_capital > 0 else 0
    
    return {
        'summary': summary,
        'trades': transformed_trades,
        'monthly_performance': performance.get('monthly_performance')  # Keep monthly performance as-is (points only)
    }


@router.get("/strategy/{strategy_id}/performance", response_model=PerformanceResponse)
def get_strategy_performance(strategy_id: int):
    """
    Get strategy performance (GET - no settings).
    """
    return _get_strategy_performance_internal(strategy_id, None)


@router.post("/strategy/{strategy_id}/performance", response_model=PerformanceResponse)
def post_strategy_performance(strategy_id: int, request: BacktestSettingsRequest):
    """
    Get strategy performance with backtest settings (POST - with settings).
    """
    return _get_strategy_performance_internal(strategy_id, request.backtest_settings if request else None)


def _get_strategy_performance_internal(strategy_id: int, backtest_settings: Optional[Dict[str, Any]]):
    """
    Internal function to get strategy performance metrics.
    
    Behavior:
    - If strategy is LIVE (deployed): Return LIVE performance from runtime store
    - If strategy is NOT live: Run BacktestEngine ONCE, cache result, return cached performance
    - If backtest_settings provided: Apply brokerage and capital calculations
    
    Args:
        strategy_id: Strategy ID
        backtest_settings: Optional dict with backtest settings
    
    Returns:
        PerformanceResponse with summary and trades
    """
    try:
        # Load strategy by ID
        strategy = _get_strategy_by_id(strategy_id)
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy with ID {strategy_id} not found"
            )
        
        # Check strategy status
        strategy_status = strategy.get('status', 'DRAFT')  # Default to DRAFT if not specified
        
        # LIVE MODE: Strategy is deployed
        if strategy_status == 'DEPLOYED':
            logger.info(f"Strategy {strategy_id} is LIVE - fetching runtime metrics")
            
            live_performance = _get_live_performance(strategy_id)
            
            if live_performance:
                # Apply brokerage if settings provided
                if backtest_settings:
                    transformed = _apply_brokerage_to_performance(live_performance, backtest_settings)
                    return PerformanceResponse(
                        success=True,
                        mode="LIVE",
                        summary=transformed.get('summary', {}),
                        trades=transformed.get('trades', []),
                        monthly_performance=transformed.get('monthly_performance')
                    )
                
                return PerformanceResponse(
                    success=True,
                    mode="LIVE",
                    summary=live_performance.get('summary', {}),
                    trades=live_performance.get('trades', []),
                    monthly_performance=live_performance.get('monthly_performance')
                )
            else:
                # No live metrics available - fall back to backtest
                logger.warning(f"No live metrics for strategy {strategy_id}, falling back to backtest")
                strategy_status = 'DRAFT'  # Force backtest mode
        
        # BACKTEST MODE: Strategy is not live or no live metrics
        if strategy_status != 'DEPLOYED':
            logger.info(f"Strategy {strategy_id} is NOT live - running backtest")
            
            # Check cache first
            cached_performance = _get_cached_performance(strategy_id)
            
            if cached_performance:
                logger.info(f"Returning cached performance for strategy {strategy_id}")
                # Extract mode from cache (defaults to BACKTEST if not present)
                cached_mode = cached_performance.get('mode', 'BACKTEST')
                
                # Apply brokerage if settings provided
                if backtest_settings:
                    transformed = _apply_brokerage_to_performance(cached_performance, backtest_settings)
                    return PerformanceResponse(
                        success=True,
                        mode=cached_mode,
                        summary=transformed.get('summary', {}),
                        trades=transformed.get('trades', []),
                        monthly_performance=transformed.get('monthly_performance')
                    )
                
                return PerformanceResponse(
                    success=True,
                    mode=cached_mode,
                    summary=cached_performance.get('summary', {}),
                    trades=cached_performance.get('trades', []),
                    monthly_performance=cached_performance.get('monthly_performance')
                )
            
            # Cache miss - run backtest
            logger.info(f"Cache miss for strategy {strategy_id} - running backtest")
            
            # Validate strategy has required structure
            if 'logic' not in strategy:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Strategy missing required 'logic' section"
                )
            
            if 'risk' not in strategy:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Strategy missing required 'risk' section"
                )
            
            # Run BacktestEngine (immutable - doesn't modify strategy)
            backtest_results = _run_backtest(strategy)
            
            # Check if backtest returned an error response (missing data or other errors)
            if not backtest_results.get('success', True):
                # Return error response with 200 status for business logic errors to prevent server crashes
                # Frontend will check success=false to display error
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=backtest_results
                )
            
            # Cache results (without brokerage - cache raw results)
            _cache_performance(strategy_id, backtest_results)
            
            # Apply brokerage if settings provided
            if backtest_settings:
                transformed = _apply_brokerage_to_performance(backtest_results, backtest_settings)
                return PerformanceResponse(
                    success=True,
                    mode="BACKTEST",
                    summary=transformed.get('summary', {}),
                    trades=transformed.get('trades', []),
                    monthly_performance=transformed.get('monthly_performance')
                )
            
            return PerformanceResponse(
                success=True,
                mode="BACKTEST",
                summary=backtest_results.get('summary', {}),
                trades=backtest_results.get('trades', []),
                monthly_performance=backtest_results.get('monthly_performance')
            )
        
        # Should not reach here, but handle gracefully
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error processing strategy performance"
        )
        
    except HTTPException:
        # Re-raise HTTPException as-is (validation errors, etc.)
        raise
    except Exception as e:
        # Catch any unexpected errors and return structured response (don't crash server)
        logger.error(f"Unexpected error getting strategy performance for {strategy_id}: {e}", exc_info=True)
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Please try again or contact support."
                }
            }
        )
