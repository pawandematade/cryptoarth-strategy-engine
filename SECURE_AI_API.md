# Secure AI Strategy Generation API

## Overview
Production-safe API for generating trading strategies from natural language using OpenAI.

## Endpoint
```
POST /auth/ai/generate-strategy
```

## Request
```json
{
  "symbol": "BTCUSD",
  "description": "EMA 9 cross above 21 EMA buy and EMA 9 cross below 21 EMA sell, TP 2% SL 1%"
}
```

### Request Fields
- `symbol` (required): Trading symbol (e.g., "BTCUSD", "ETHUSD")
- `description` (required): Natural language strategy description (10-2000 characters)

## Response
```json
{
  "success": true,
  "strategy": {
    "strategy_id": "uuid-string",
    "symbol": "BTCUSD",
    "timeframe": "1h",
    "type": "indicator_based",
    "logic": {
      "entry": {
        "conditions": [
          {
            "indicator": "ema",
            "operator": "cross_above",
            "value": 21,
            "comparison": "ema_9"
          }
        ],
        "logic_operator": "and"
      },
      "exit": {
        "conditions": [
          {
            "indicator": "ema",
            "operator": "cross_below",
            "value": 9,
            "comparison": "ema_21"
          }
        ],
        "logic_operator": "and"
      }
    },
    "risk": {
      "stop_loss": {
        "type": "percentage",
        "value": 1.0
      },
      "take_profit": {
        "type": "percentage",
        "value": 2.0
      },
      "position_size": {
        "type": "percentage",
        "value": 1.0
      }
    },
    "meta": {
      "confidence": 0.8,
      "explanation": "EMA crossover strategy with 9 and 21 period EMAs",
      "complexity": "simple"
    },
    "created_at": "2024-01-01T12:00:00"
  },
  "suggestions": [
    "Improve risk-reward ratio (aim for at least 1.5:1)",
    "Consider adding higher timeframe filter to avoid false signals",
    "Add trend filter to avoid trading in sideways markets"
  ],
  "meta": {
    "generated_at": "2024-01-01T12:00:00",
    "model": "gpt-4o-mini",
    "validated": true
  }
}
```

## Security Features

### 1. Whitelist Approach
- **Allowed Indicators**: EMA, SMA, RSI, MACD, SuperTrend, Bollinger Bands, etc.
- **Allowed Operators**: above, below, cross, crossover, and, or, etc.
- **Allowed Timeframes**: 1m, 5m, 15m, 1h, 4h, 1d, etc.
- **Allowed Strategy Types**: indicator_based, grid_based, condition_based, formula_based, hybrid

### 2. Schema Validation
- All strategies are validated against strict schema
- No executable code allowed
- No arbitrary expressions
- Only numeric values (no string numbers)

### 3. Server-Side Only
- OpenAI API calls happen server-side only
- No prompts exposed to frontend
- API keys never sent to client

### 4. Redis Storage
- Strategies saved to Redis with 30-day TTL
- Key format: `STRATEGY:{strategy_id}`
- Retrievable via: `GET /auth/ai/strategy/{strategy_id}`

## Example Requests

### Indicator-Based Strategy
```json
{
  "symbol": "BTCUSD",
  "description": "RSI above 70 sell, RSI below 30 buy, TP 3% SL 1.5%"
}
```

### Price-Based Strategy
```json
{
  "symbol": "ETHUSD",
  "description": "Buy when price goes above 3000, sell when price drops below 2800"
}
```

### Grid Strategy
```json
{
  "symbol": "BTCUSD",
  "description": "Grid trading between 90000 and 95000 with 10 levels, TP 0.5% per level"
}
```

### Hybrid Strategy
```json
{
  "symbol": "BTCUSD",
  "description": "SuperTrend 7 3 for trend, RSI filter above 50 for entries, TP 2% SL 1%"
}
```

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Description must be at least 10 characters"
}
```

### 400 Validation Error
```json
{
  "detail": "Strategy validation failed: Invalid indicator: custom_indicator"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error: OpenAI API error message"
}
```

## Retrieve Saved Strategy
```
GET /auth/ai/strategy/{strategy_id}
```

Returns the strategy saved in Redis.

## Supported Languages
- English
- Hindi
- Hinglish
- Telugu
- Tamil
- And more (via OpenAI's multilingual support)

## Notes
- Strategies are validated before returning
- Suggestions are auto-generated based on strategy analysis
- All strategies are saved to Redis automatically
- No executable code is ever returned
- All values are sanitized and validated

