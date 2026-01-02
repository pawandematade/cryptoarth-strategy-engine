# Debugging 400 Bad Request Error

## Current Status
- ✅ 422 Error Fixed (Pydantic validation passing)
- ❌ 400 Error Now (Endpoint validation failing)

## Possible Causes of 400 Error

### 1. Empty Prompt/Description
**Error Message:** `"Either 'prompt' or 'description' is required and cannot be empty"`

**Check:**
- Is `description` field present in your request?
- Is `description` value empty string `""` or just whitespace?
- Is `prompt` field present?

**Solution:**
```json
{
  "description": "EMA crossover scalping strategy"  // Must be non-empty string
}
```

### 2. Extra Keys in Request
**Error Message:** `"Invalid payload: Extra keys not allowed: [...]"`

**Check:**
- Are you sending any fields NOT in this list?
  - `prompt`, `description`, `type`, `symbol`, `timeframe`, `chart_type`
  - `take_profit`, `stop_loss`, `trailing_stop`
  - `trading_session`, `max_trades_per_day`
  - `current_price`, `market_context`

**Solution:**
Remove any extra fields from your request.

## How to Debug

### Step 1: Check Server Logs
Look for these log messages in your server terminal:
```
🔄 NEW STRATEGY GENERATION REQUEST RECEIVED
Raw payload keys: [...]
Payload: {...}
Prompt value: ...
```

### Step 2: Check Postman Response Body
The 400 error response should include a `detail` field with the exact reason:

```json
{
  "detail": "Either 'prompt' or 'description' is required and cannot be empty"
}
```

OR

```json
{
  "detail": "Invalid payload: Extra keys not allowed: ['some_field']. Allowed keys: [...]"
}
```

### Step 3: Test with Minimal Request
Try this minimal request first:

```json
POST http://localhost:8000/auth/ai-strategy/generate
Content-Type: application/json

{
  "description": "Buy when price crosses above 20 EMA"
}
```

### Step 4: Test with Full Request
If minimal works, try full request:

```json
POST http://localhost:8000/auth/ai-strategy/generate
Content-Type: application/json

{
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "type": "indicator_based",
  "description": "EMA crossover scalping strategy"
}
```

## Common Mistakes

1. **Empty String:**
   ```json
   {
     "description": ""  // ❌ This will fail
   }
   ```

2. **Whitespace Only:**
   ```json
   {
     "description": "   "  // ❌ This will fail
   }
   ```

3. **Missing Field:**
   ```json
   {
     "symbol": "BTCUSDT"  // ❌ Missing description/prompt
   }
   ```

4. **Typo in Field Name:**
   ```json
   {
     "descriptions": "..."  // ❌ Should be "description"
   }
   ```

## Next Steps

1. **Share the exact error message** from Postman response body
2. **Share the server logs** showing the request payload
3. **Share your exact request body** that you're sending

This will help identify the exact issue!

