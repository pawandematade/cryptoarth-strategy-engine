"""
Backtest API Routes
Direct endpoints on Strategy Engine (no /auth prefix)
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, Any
import logging
import copy
import pandas as pd
from datetime import datetime, timedelta
from core.engine.backtest_engine import BacktestEngine
from core.feed.delta_history import fetch_ohlcv, get_default_lookback_days

logger = logging.getLogger(__name__)

router = APIRouter()

# Timeframe mapping
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


def _calculate_max_indicator_period(strategy: Dict[str, Any]) -> int:
    """
    Calculate the maximum indicator period required for the strategy.
    
    Checks:
    - EMA periods (logic.emas)
    - SuperTrend period (logic.supertrend.period)
    - RSI period (logic.rsi.period)
    - MACD periods (logic.macd.fast_period, slow_period, signal_period)
    - Bollinger Bands period (logic.bollinger_bands.period)
    - Any other indicator periods
    
    Args:
        strategy: Strategy dictionary
    
    Returns:
        Maximum period required (default: 200 if no indicators found)
    """
    max_period = 0
    logic = strategy.get('logic', {})
    
    # Check EMA periods
    if 'emas' in logic and isinstance(logic['emas'], list):
        ema_periods = [int(p) for p in logic['emas'] if isinstance(p, (int, float)) and p > 0]
        if ema_periods:
            max_period = max(max_period, max(ema_periods))
    
    # Check SuperTrend period
    if 'supertrend' in logic and isinstance(logic['supertrend'], dict):
        period = logic['supertrend'].get('period')
        if isinstance(period, (int, float)) and period > 0:
            max_period = max(max_period, int(period))
    
    # Check RSI period
    if 'rsi' in logic and isinstance(logic['rsi'], dict):
        period = logic['rsi'].get('period')
        if isinstance(period, (int, float)) and period > 0:
            max_period = max(max_period, int(period))
    
    # Check MACD periods
    if 'macd' in logic and isinstance(logic['macd'], dict):
        fast = logic['macd'].get('fast_period')
        slow = logic['macd'].get('slow_period')
        signal = logic['macd'].get('signal_period')
        for period in [fast, slow, signal]:
            if isinstance(period, (int, float)) and period > 0:
                max_period = max(max_period, int(period))
    
    # Check Bollinger Bands period
    if 'bollinger_bands' in logic and isinstance(logic['bollinger_bands'], dict):
        period = logic['bollinger_bands'].get('period')
        if isinstance(period, (int, float)) and period > 0:
            max_period = max(max_period, int(period))
    
    # Default to 200 if no indicators found (safety buffer)
    if max_period == 0:
        max_period = 200
    
    return max_period


def _convert_candles_to_dataframe(candles):
    """Convert candles list to pandas DataFrame."""
    if not candles:
        return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
    
    sorted_candles = sorted(candles, key=lambda c: c.get('time', 0))
    
    data = {
        'open': [float(c['open']) for c in sorted_candles],
        'high': [float(c['high']) for c in sorted_candles],
        'low': [float(c['low']) for c in sorted_candles],
        'close': [float(c['close']) for c in sorted_candles],
        'volume': [float(c.get('volume', 0)) for c in sorted_candles]
    }
    
    df = pd.DataFrame(data)
    df = df.reset_index(drop=True)
    return df


def _group_trades_by_date(trades, candles_list):
    """Group trades by Year → Month → Day."""
    if not trades or not candles_list:
        return {}
    
    index_to_timestamp = {}
    for idx, candle in enumerate(candles_list):
        if idx < len(candles_list):
            index_to_timestamp[idx] = candle.get('time', 0)
    
    grouped = {}
    
    for trade in trades:
        entry_index = trade.get('entry_index', 0)
        entry_timestamp = index_to_timestamp.get(entry_index, 0)
        
        if entry_timestamp == 0:
            continue
        
        dt = datetime.fromtimestamp(entry_timestamp)
        year = str(dt.year)
        month = dt.strftime('%m')
        day = dt.strftime('%d')
        
        if year not in grouped:
            grouped[year] = {}
        if month not in grouped[year]:
            grouped[year][month] = {}
        if day not in grouped[year][month]:
            grouped[year][month][day] = []
        
        grouped[year][month][day].append(trade)
    
    # Calculate monthly summaries
    for year in grouped:
        for month in grouped[year]:
            month_trades = []
            for day in grouped[year][month]:
                month_trades.extend(grouped[year][month][day])
            
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


def _run_backtest(strategy: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run BacktestEngine on strategy.
    
    Returns:
        Dict with either:
        - Success: {'success': True, 'mode': 'BACKTEST', 'summary': {...}, 'trades': [...], 'monthly_performance': {...}}
        - Error: {'success': False, 'error_code': 'NO_HISTORICAL_DATA', 'message': '...'}
    """
    try:
        strategy_copy = copy.deepcopy(strategy)
        
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
        if not timeframe or timeframe == '15MIN' and not meta.get('timeframe') and not strategy_copy.get('userParams', {}).get('timeframe'):
            logger.warning(f"Strategy missing explicit timeframe, using default: {timeframe}")
        
        # Ensure timeframe is in meta for consistency
        if not meta.get('timeframe'):
            meta['timeframe'] = timeframe
            strategy_copy['meta'] = meta
        
        # Get lookback_days from strategy or use default based on timeframe
        lookback_days = strategy_copy.get('lookback_days')
        if lookback_days is None:
            lookback_days = get_default_lookback_days(timeframe)
        
        # Fetch historical candles with controlled lookback window
        # Note: fetch_ohlcv now handles UI → Delta mapping and chunked fetching automatically
        end_time = datetime.now()
        end_timestamp = int(end_time.timestamp())
        start_timestamp = int((end_time - timedelta(days=lookback_days)).timestamp())
        
        logger.info(f"Fetching historical candles for backtest: symbol={symbol}, timeframe={timeframe}, lookback_days={lookback_days}")
        candles_list = fetch_ohlcv(symbol, timeframe, start_timestamp, end_timestamp, auto_map=True, lookback_days=lookback_days)
        
        if not candles_list:
            # Log detailed error for debugging (backend only) - WARNING, not ERROR
            logger.warning(f"No historical data available for {symbol} {timeframe} - Delta Exchange returned empty response")
            # Return structured error response (broker-agnostic) - DO NOT raise exception
            return {
                "success": False,
                "error": {
                    "code": "NO_HISTORICAL_DATA",
                    "message": "Backtest data is not available for the selected symbol and timeframe. Please try a different timeframe or symbol."
                }
            }
        
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
        
        # Pre-backtest safety validation: Calculate required candles
        max_period = _calculate_max_indicator_period(strategy_copy)
        required_candles = max_period * 2  # Require 2x max period for reliable backtest
        
        candle_count = len(candles_df)
        
        logger.info(f"Pre-backtest validation: count={candle_count}, max_period={max_period}, required={required_candles} (max_period * 2)")
        
        if candle_count < required_candles:
            logger.warning(f"Insufficient historical data for {symbol} {timeframe}: {candle_count} candles < {required_candles} required (max indicator period: {max_period})")
            # Return structured error response (broker-agnostic) - DO NOT raise exception
            return {
                "success": False,
                "error": {
                    "code": "INSUFFICIENT_DATA",
                    "message": "Not enough historical data to run this strategy. Try a shorter timeframe or reduce indicators."
                }
            }
        
        # Run BacktestEngine
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
        
        # Group trades by date
        monthly_perf = _group_trades_by_date(results.get('trades', []), candles_list)
        
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


def _apply_brokerage(performance: Dict[str, Any], backtest_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Apply brokerage and capital calculations to performance results."""
    if not backtest_settings:
        return performance
    
    initial_capital = float(backtest_settings.get('initialCapital', 100000))
    leverage = float(backtest_settings.get('leverage', 1))
    capital_per_trade_pct = float(backtest_settings.get('capitalPerTrade', 10)) / 100.0
    
    maker_rate = 0.0002  # 0.02%
    taker_rate = 0.0005  # 0.05%
    
    capital_per_trade = initial_capital * capital_per_trade_pct
    
    transformed_trades = []
    total_brokerage_maker = 0.0
    total_brokerage_taker = 0.0
    gross_pnl_currency = 0.0
    
    for trade in performance.get('trades', []):
        entry_price = float(trade.get('entry_price', 0))
        exit_price = float(trade.get('exit_price', 0))
        pnl_points = float(trade.get('pnl', 0))
        
        leveraged_capital = capital_per_trade * leverage
        position_size = leveraged_capital / entry_price if entry_price > 0 else 0
        
        gross_pnl_trade = pnl_points * position_size
        gross_pnl_currency += gross_pnl_trade
        
        entry_brokerage_maker = leveraged_capital * maker_rate
        exit_brokerage_maker = position_size * exit_price * maker_rate
        trade_brokerage_maker = entry_brokerage_maker + exit_brokerage_maker
        total_brokerage_maker += trade_brokerage_maker
        
        entry_brokerage_taker = leveraged_capital * taker_rate
        exit_brokerage_taker = position_size * exit_price * taker_rate
        trade_brokerage_taker = entry_brokerage_taker + exit_brokerage_taker
        total_brokerage_taker += trade_brokerage_taker
        
        net_pnl_maker = gross_pnl_trade - trade_brokerage_maker
        net_pnl_taker = gross_pnl_trade - trade_brokerage_taker
        
        transformed_trade = trade.copy()
        transformed_trade['pnl_points'] = pnl_points
        transformed_trade['gross_pnl_currency'] = round(gross_pnl_trade, 2)
        transformed_trade['brokerage_maker'] = round(trade_brokerage_maker, 2)
        transformed_trade['brokerage_taker'] = round(trade_brokerage_taker, 2)
        transformed_trade['net_pnl_maker'] = round(net_pnl_maker, 2)
        transformed_trade['net_pnl_taker'] = round(net_pnl_taker, 2)
        transformed_trade['position_size'] = round(position_size, 4)
        
        transformed_trades.append(transformed_trade)
    
    summary = performance.get('summary', {}).copy()
    
    net_pnl_currency_maker = gross_pnl_currency - total_brokerage_maker
    net_pnl_currency_taker = gross_pnl_currency - total_brokerage_taker
    
    summary['gross_pnl_currency'] = round(gross_pnl_currency, 2)
    summary['net_pnl_currency_maker'] = round(net_pnl_currency_maker, 2)
    summary['net_pnl_currency_taker'] = round(net_pnl_currency_taker, 2)
    summary['total_brokerage_maker'] = round(total_brokerage_maker, 2)
    summary['total_brokerage_taker'] = round(total_brokerage_taker, 2)
    summary['net_pnl_points'] = summary.get('net_pnl', 0)
    summary['initial_capital'] = initial_capital
    summary['final_capital_maker'] = round(initial_capital + net_pnl_currency_maker, 2)
    summary['final_capital_taker'] = round(initial_capital + net_pnl_currency_taker, 2)
    summary['return_pct_maker'] = round((net_pnl_currency_maker / initial_capital) * 100, 2) if initial_capital > 0 else 0
    summary['return_pct_taker'] = round((net_pnl_currency_taker / initial_capital) * 100, 2) if initial_capital > 0 else 0
    
    return {
        'summary': summary,
        'trades': transformed_trades,
        'monthly_performance': performance.get('monthly_performance')
    }


class PreviewBacktestRequest(BaseModel):
    """Request model for preview backtest (no strategy_id required)"""
    strategy: Dict[str, Any] = Field(..., description="Full strategy JSON")
    backtest_settings: Dict[str, Any] = Field(..., description="Backtest settings: initialCapital, leverage, capitalPerTrade")


@router.post("/backtest/preview")
def preview_backtest(request: PreviewBacktestRequest):
    """
    Preview backtest for a strategy WITHOUT saving it.
    
    This endpoint:
    - Does NOT require strategy_id
    - Does NOT save strategy
    - Does NOT cache results
    - Runs BacktestEngine directly on provided strategy JSON
    - Applies brokerage calculations if backtest_settings provided
    
    Args:
        request: PreviewBacktestRequest with strategy JSON and backtest_settings
    
    Returns:
        Backtest results with summary, trades, and monthly_performance
    """
    try:
        strategy = request.strategy
        backtest_settings = request.backtest_settings
        
        # Validate strategy structure
        if 'logic' not in strategy:
            raise HTTPException(
                status_code=400,
                detail="Strategy missing required 'logic' section"
            )
        
        if 'risk' not in strategy:
            raise HTTPException(
                status_code=400,
                detail="Strategy missing required 'risk' section"
            )
        
        # Validate timeframe is present
        meta = strategy.get('meta', {})
        timeframe = (
            meta.get('timeframe') or
            strategy.get('userParams', {}).get('timeframe') or
            strategy.get('timeframe')
        )
        
        if not timeframe:
            logger.warning(f"Strategy missing timeframe: symbol={strategy.get('symbol', 'UNKNOWN')}")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": False,
                    "error": {
                        "code": "MISSING_TIMEFRAME",
                        "message": "Please select a timeframe before running backtest."
                    }
                }
            )
        
        # Validate backtest settings
        if not backtest_settings:
            raise HTTPException(
                status_code=400,
                detail="backtest_settings is required"
            )
        
        initial_capital = backtest_settings.get('initialCapital')
        leverage = backtest_settings.get('leverage')
        capital_per_trade = backtest_settings.get('capitalPerTrade')
        
        if initial_capital is None or initial_capital <= 0:
            raise HTTPException(
                status_code=400,
                detail="initialCapital must be greater than 0"
            )
        
        if leverage is None or leverage < 1:
            raise HTTPException(
                status_code=400,
                detail="leverage must be at least 1"
            )
        
        if capital_per_trade is None or capital_per_trade < 1 or capital_per_trade > 100:
            raise HTTPException(
                status_code=400,
                detail="capitalPerTrade must be between 1 and 100"
            )
        
        logger.info(f"Running preview backtest for strategy: {strategy.get('symbol', 'UNKNOWN')}")
        
        # Run backtest
        backtest_results = _run_backtest(strategy)
        
        # Check if backtest returned an error response (missing data or other errors)
        if not backtest_results.get('success', True):
            # Return error response with 422 status (Unprocessable Entity - valid request but data unavailable)
            # Use 200 status for business logic errors to prevent server crashes
            # Frontend will check success=false to display error
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=backtest_results
            )
        
        # Apply brokerage calculations
        transformed_results = _apply_brokerage(backtest_results, backtest_settings)
        
        # Return results (no caching, no saving)
        return {
            "success": True,
            "mode": "BACKTEST",
            "summary": transformed_results.get('summary', {}),
            "trades": transformed_results.get('trades', []),
            "monthly_performance": transformed_results.get('monthly_performance')
        }
        
    except HTTPException:
        # Re-raise HTTPException as-is (validation errors, etc.)
        raise
    except Exception as e:
        # Catch any unexpected errors and return structured response (don't crash server)
        logger.error(f"Unexpected error in preview_backtest endpoint: {e}", exc_info=True)
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

