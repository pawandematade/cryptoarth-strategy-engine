"""
Backtest API Routes
Direct endpoints on Strategy Engine (no /auth prefix)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any
import logging
import copy
import pandas as pd
from datetime import datetime, timedelta
from app.engine.backtest_engine import BacktestEngine
from app.feed.delta_history import fetch_ohlcv

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
    """Run BacktestEngine on strategy."""
    try:
        strategy_copy = copy.deepcopy(strategy)
        
        symbol = strategy_copy.get('symbol', 'BTCUSD')
        meta = strategy_copy.get('meta', {})
        timeframe = meta.get('timeframe', '15MIN')
        
        # Fetch historical candles
        # Note: fetch_ohlcv now handles UI → Delta mapping automatically
        # Pass UI-friendly values, mapping happens inside fetch_ohlcv
        end_time = datetime.now()
        start_time = end_time - timedelta(days=365)
        start_timestamp = int(start_time.timestamp())
        end_timestamp = int(end_time.timestamp())
        
        logger.info(f"Fetching historical candles for backtest: symbol={symbol}, timeframe={timeframe}")
        candles_list = fetch_ohlcv(symbol, timeframe, start_timestamp, end_timestamp, auto_map=True)
        
        if not candles_list:
            # Log detailed error for debugging (backend only)
            logger.warning(f"No historical data available for {symbol} {timeframe} - Delta Exchange returned empty response")
            # Return generic error message to frontend (broker-agnostic)
            raise ValueError(
                "Backtest data is not available for the selected symbol and timeframe. "
                "Please try a different timeframe or symbol."
            )
        
        candles_df = _convert_candles_to_dataframe(candles_list)
        
        if len(candles_df) == 0:
            # Log detailed error for debugging (backend only)
            logger.warning(f"Empty candles DataFrame for {symbol} {timeframe} after conversion")
            # Return generic error message to frontend (broker-agnostic)
            raise ValueError(
                "Backtest data is not available for the selected symbol and timeframe. "
                "Please try a different timeframe or symbol."
            )
        
        # Run BacktestEngine
        engine = BacktestEngine(strategy_copy)
        results = engine.run(candles_df)
        
        # Group trades by date
        monthly_perf = _group_trades_by_date(results.get('trades', []), candles_list)
        
        results['mode'] = 'BACKTEST'
        results['monthly_performance'] = monthly_perf
        
        return results
        
    except Exception as e:
        logger.error(f"Error running backtest: {e}", exc_info=True)
        raise


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
        raise
    except ValueError as e:
        logger.error(f"Validation error in preview backtest: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error running preview backtest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

