# Postman Test Request - Correct Format

## ✅ CORRECT Request Body

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "type": "indicator_based",
  "description": "EMA crossover scalping strategy"
}
```

## ❌ COMMON MISTAKES

### Mistake 1: Missing `description` field
```json
{
  "symbol": "BTCUSDT",
  "timeframe": "5m"
}
```
**Error:** "Either 'prompt' or 'description' is required..."

### Mistake 2: Empty `description` string
```json
{
  "symbol": "BTCUSDT",
  "description": ""
}
```
**Error:** "Either 'prompt' or 'description' is required..."

### Mistake 3: Whitespace-only `description`
```json
{
  "symbol": "BTCUSDT",
  "description": "   "
}
```
**Error:** "Either 'prompt' or 'description' is required..."

### Mistake 4: Using `prompt` instead of `description` (this should work, but try `description`)
```json
{
  "symbol": "BTCUSDT",
  "prompt": "EMA crossover"
}
```

## ✅ MINIMAL WORKING REQUEST

```json
{
  "description": "Buy when price crosses above 20 EMA"
}
```

## Postman Setup

1. **Method:** POST
2. **URL:** `http://localhost:8000/auth/ai-strategy/generate`
3. **Headers:**
   - `Content-Type: application/json`
   - `Authorization: Bearer YOUR_TOKEN` (optional for testing)
4. **Body:** Select "raw" → "JSON" → Paste the JSON above

## Expected Success Response

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

## If Still Getting 400 Error

**Please share:**
1. The exact JSON you're sending in the request body
2. Server logs (terminal output showing the request)

