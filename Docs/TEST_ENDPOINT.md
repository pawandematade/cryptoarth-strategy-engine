# Testing the Fixed Endpoint

## Important: Server Restart Required

**⚠️ CRITICAL:** After code changes, you MUST restart the FastAPI server for changes to take effect.

```bash
# Stop the current server (Ctrl+C)
# Then restart:
cd Cryptoarth-strategy-engine
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Test Request (Postman)

### Request 1: Using `description` field

```http
POST http://localhost:8000/auth/ai-strategy/generate
Content-Type: application/json

{
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "type": "indicator_based",
  "description": "EMA crossover scalping strategy"
}
```

### Request 2: Using `prompt` field (backward compatible)

```http
POST http://localhost:8000/auth/ai-strategy/generate
Content-Type: application/json

{
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "prompt": "EMA crossover scalping strategy"
}
```

### Request 3: Minimal request

```http
POST http://localhost:8000/auth/ai-strategy/generate
Content-Type: application/json

{
  "description": "Buy when price crosses above 20 EMA"
}
```

## Expected Response (Success)

```json
{
  "success": true,
  "strategy": {
    "symbol": "BTCUSDT",
    "strategy_type": "...",
    "logic": {...},
    "risk": {...},
    "meta": {...}
  },
  "message": "Strategy generated successfully",
  "strategy_id": null
}
```

## If Still Getting 422 Error

Please check:

1. **Server Restarted?** - Changes only take effect after server restart
2. **Exact Error Message?** - Check Postman response body for detailed error
3. **Pydantic Version?** - Run: `pip show pydantic`

## Common 422 Error Causes

1. **Field name typo** - Check spelling: `description` not `descriptions`
2. **Missing required field** - Either `prompt` OR `description` must be provided
3. **Invalid data type** - `timeframe` should be string, not number
4. **Server not restarted** - Most common issue!

## Debug Steps

1. Check server logs for validation errors
2. Verify the request body JSON is valid
3. Check Postman response body for Pydantic validation details
4. Ensure server was restarted after code changes

