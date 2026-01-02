# Strategy Performance API

## Endpoint
**GET** `/auth/strategy/performance/{strategy_id}`

## Purpose
Provides lightweight performance metrics for strategy UI cards without rerunning backtests.

## Features

### 1. **Caching System**
- Backtest results are automatically cached in Redis when a backtest is run
- Cache key: `BACKTEST:{strategy_id}`
- Cache TTL: 7 days (604,800 seconds)
- No backtest rerun required - fetches from cache

### 2. **Strategy Lookup**
- Supports both secure format (UUID strategy_id from Redis)
- Supports legacy format (integer ID from strategies.json)
- Automatically detects and handles both formats

### 3. **Lightweight Metrics**
Returns only essential metrics for UI cards:
- `net_pnl`: Net profit/loss
- `win_rate`: Win rate percentage
- `max_drawdown`: Maximum drawdown
- `total_trades`: Total number of trades
- `sharpe_ratio`: Sharpe ratio
- `profit_factor`: Profit factor
- `total_return`: Total return percentage
- `realized_pnl`: Realized profit/loss

### 4. **Risk Level Calculation**
Automatically calculates risk level based on:
- **Win Rate**: >60% (Low), 40-60% (Medium), <40% (High)
- **Sharpe Ratio**: >1.5 (Low), 0.5-1.5 (Medium), <0.5 (High)
- **Max Drawdown**: <10% (Low), 10-25% (Medium), >25% (High)

Returns: `"Low"`, `"Medium"`, or `"High"`

## Request

```http
GET /auth/strategy/performance/{strategy_id}
```

**Path Parameters:**
- `strategy_id` (string): Strategy ID (UUID for secure format, or integer for legacy)

## Response

### Success (with cached results)
```json
{
  "success": true,
  "strategy_id": "abc-123-def-456",
  "metrics": {
    "net_pnl": 1250.50,
    "win_rate": 65.5,
    "max_drawdown": 8.2,
    "total_trades": 45,
    "sharpe_ratio": 1.8,
    "profit_factor": 2.1,
    "total_return": 12.5,
    "realized_pnl": 1300.00
  },
  "risk_level": "Low",
  "message": null
}
```

### No Backtest Results
```json
{
  "success": false,
  "strategy_id": "abc-123-def-456",
  "metrics": null,
  "risk_level": null,
  "message": "No backtest results found. Please run a backtest first."
}
```

### Strategy Not Found
```http
HTTP 404 Not Found
{
  "detail": "Strategy not found: {strategy_id}"
}
```

## Implementation Details

### Files Created/Modified

1. **`app/api/routes_strategy.py`** (NEW)
   - Main performance endpoint
   - Risk level calculation
   - Metrics extraction
   - Strategy lookup (Redis + JSON)

2. **`app/api/routes_ai_strategy.py`** (MODIFIED)
   - Added caching logic to backtest endpoint
   - Caches results in Redis after backtest completes

3. **`app/main.py`** (MODIFIED)
   - Registered new strategy router

### Caching Flow

1. User runs backtest via `POST /auth/ai-strategy/backtest`
2. Backtest results are cached in Redis with key `BACKTEST:{strategy_id}`
3. Frontend calls `GET /auth/strategy/performance/{strategy_id}`
4. Endpoint retrieves cached results from Redis
5. Returns lightweight metrics + risk level

### Risk Level Algorithm

```python
risk_score = 0

# Win rate component (0-2 points)
if win_rate >= 60: risk_score += 0
elif win_rate >= 40: risk_score += 1
else: risk_score += 2

# Sharpe ratio component (0-2 points)
if sharpe_ratio >= 1.5: risk_score += 0
elif sharpe_ratio >= 0.5: risk_score += 1
else: risk_score += 2

# Drawdown component (0-2 points)
if max_drawdown < 10: risk_score += 0
elif max_drawdown < 25: risk_score += 1
else: risk_score += 2

# Final risk level
if risk_score <= 2: return "Low"
elif risk_score <= 4: return "Medium"
else: return "High"
```

## Usage Example

### Frontend Integration

```javascript
// Fetch strategy performance
const response = await fetch(
  `http://localhost:8000/auth/strategy/performance/${strategyId}`
);
const data = await response.json();

if (data.success) {
  // Display metrics
  console.log(`Net PNL: $${data.metrics.net_pnl}`);
  console.log(`Win Rate: ${data.metrics.win_rate}%`);
  console.log(`Risk Level: ${data.risk_level}`);
} else {
  // No backtest results - prompt user to run backtest
  console.log(data.message);
}
```

## Error Handling

- **Strategy Not Found**: Returns 404 with error message
- **No Cached Results**: Returns success=false with message
- **Invalid Cache Data**: Returns success=false with error message
- **Redis Errors**: Logged but doesn't fail request (graceful degradation)

## Performance

- **Fast**: No backtest computation - just Redis lookup
- **Lightweight**: Returns only essential metrics
- **Cached**: Results cached for 7 days
- **Efficient**: Single Redis GET operation

## Notes

- Backtest must be run first to cache results
- Cache expires after 7 days
- Supports both secure (UUID) and legacy (integer) strategy IDs
- Risk level is calculated dynamically from metrics

