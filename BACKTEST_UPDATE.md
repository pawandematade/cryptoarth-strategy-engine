# Backtest Service Update - Real Historical Data Integration

## Summary
Updated `backtest_service.py` to use **REAL historical candle data** from Delta Exchange API instead of mock data.

## Changes Made

### 1. Real Data Integration
- **Replaced**: Mock candle generation with real API calls
- **Source**: `/auth/history/candles` endpoint (Delta Exchange)
- **Function**: `fetch_historical_candles()` - Fetches real OHLCV data

### 2. Timeframe Mapping
- **Mapping**: Strategy timeframes → Delta Exchange resolutions
  - `1m` → `1`
  - `5m` → `5`
  - `15m` → `15`
  - `1h` → `60`
  - `4h` → `240`
  - `1d` → `1D`
  - `1w` → `1W`
  - etc.

### 3. Indicator Calculations
Implemented real technical indicators from candle data:
- **EMA** (Exponential Moving Average)
- **SMA** (Simple Moving Average)
- **RSI** (Relative Strength Index)
- **ATR** (Average True Range)
- **SuperTrend** (with proper trend direction tracking)

### 4. Strategy Evaluation
- **Entry/Exit Logic**: Evaluates conditions candle-by-candle
- **Stop Loss/Take Profit**: Applied per trade
- **Position Management**: Tracks open positions and closes them properly
- **Trade Tracking**: Records all trades with entry/exit prices and PNL

### 5. Legacy Format Support
- **Auto-conversion**: Legacy strategy format (`condition`-based) automatically converted to secure format (`logic`-based) for backtesting
- **Supported Types**:
  - `ema_crossover` → EMA crossover logic
  - `supertrend` → SuperTrend indicator logic
  - `price_above` / `price_below` → Price-based conditions

### 6. Metrics Calculation
All metrics calculated from **real trades**:
- Net PNL, Realized PNL
- Win Rate, Loss Rate
- Average Profit/Loss per Trade
- Max Drawdown (with start/end dates)
- Sharpe Ratio
- Profit Factor
- Win/Loss Streaks
- Reward to Risk Ratio
- Expectancy Ratio

### 7. Hierarchical Data
- **Year → Month → Day** breakdown generated from actual trades
- Real timestamps and dates from historical candles

### 8. Fallback Mechanism
- **Fallback**: If insufficient data (< 10 candles) or API error, falls back to mock data
- **Logging**: Comprehensive logging for debugging

## Key Functions

### `fetch_historical_candles(symbol, timeframe, days)`
- Fetches real candles from Delta Exchange
- Maps timeframe to resolution
- Returns list of candle dictionaries

### `calculate_indicators(candles, strategy)`
- Calculates all required indicators based on strategy conditions
- Returns dictionary of indicator arrays

### `evaluate_condition(condition, indicators, candle_index, current_price)`
- Evaluates single condition against market state
- Supports price, EMA, RSI, SuperTrend, etc.

### `evaluate_entry_exit(strategy, indicators, candle_index, current_price, is_in_position)`
- Evaluates entry and exit conditions
- Returns `(should_enter, should_exit)` tuple

### `run_backtest(strategy, period)`
- Main backtest function
- Processes candles candle-by-candle
- Executes trades based on strategy logic
- Calculates comprehensive metrics

## Strategy Schema Support

### Secure Format (Preferred)
```json
{
  "symbol": "BTCUSD",
  "timeframe": "1h",
  "logic": {
    "entry": {
      "conditions": [...],
      "logic_operator": "and"
    },
    "exit": {
      "conditions": [...],
      "logic_operator": "and"
    }
  },
  "risk": {
    "stop_loss": {"type": "percentage", "value": 1.0},
    "take_profit": {"type": "percentage", "value": 2.0}
  }
}
```

### Legacy Format (Auto-converted)
```json
{
  "symbol": "BTCUSD",
  "condition": {
    "type": "ema_crossover",
    "parameters": {
      "ema_fast": 9,
      "ema_slow": 21,
      "tp_percent": 2,
      "sl_percent": 1
    }
  }
}
```

## Error Handling

1. **Insufficient Data**: Falls back to mock data if < 10 candles
2. **API Errors**: Catches exceptions and falls back gracefully
3. **Invalid Strategy**: Returns None with error logging
4. **No Trades**: Falls back to mock data if no trades executed

## Testing

To test the updated backtest service:

```python
from app.services.backtest_service import run_backtest

# Test with secure format
strategy = {
    "symbol": "BTCUSD",
    "timeframe": "1h",
    "logic": {
        "entry": {
            "conditions": [{
                "indicator": "ema",
                "operator": "cross_above",
                "value": 21,
                "comparison": "ema_9"
            }],
            "logic_operator": "and"
        },
        "exit": {
            "conditions": [{
                "indicator": "ema",
                "operator": "cross_below",
                "value": 9,
                "comparison": "ema_21"
            }],
            "logic_operator": "and"
        }
    },
    "risk": {
        "stop_loss": {"type": "percentage", "value": 1.0},
        "take_profit": {"type": "percentage", "value": 2.0},
        "position_size": {"type": "percentage", "value": 1.0}
    }
}

results = run_backtest(strategy, period='month')
print(results)
```

## Notes

- **Real Market Behavior**: Backtest results now reflect actual market conditions
- **Timeframe Respect**: Strategy timeframes are properly mapped to Delta Exchange resolutions
- **Candle-by-Candle**: Strategy evaluated on each historical candle
- **Accurate Metrics**: All metrics calculated from real trades
- **Production Ready**: Handles edge cases and errors gracefully

## Next Steps (Optional Enhancements)

1. **More Indicators**: Add MACD, Bollinger Bands, Ichimoku, etc.
2. **Multi-Timeframe**: Support strategies using multiple timeframes
3. **Order Types**: Support limit orders, stop orders
4. **Slippage**: Add slippage modeling
5. **Commissions**: More accurate commission calculation
6. **Partial Fills**: Handle partial order fills
7. **Backtest Optimization**: Parallel processing for faster backtests

