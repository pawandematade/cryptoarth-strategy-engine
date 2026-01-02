# Prompt-Only AI Contract

## Architecture Principle

**Our system follows a strict prompt-only AI contract: all user inputs are merged into a single human-readable prompt string, and no structured fields are ever sent to OpenAI.**

## Implementation Details

### 1. Frontend Request (Unchanged)
Frontend continues to send structured payload:
```json
{
  "prompt": "EMA crossover strategy",
  "symbol": "BTCUSD",
  "timeframe": "15MIN",
  "chart_type": "candles",
  "take_profit": { "type": "percent", "value": 1 },
  "stop_loss": { "type": "percent", "value": 1 },
  "trailing_stop": { "enabled": false },
  "market_context": "Bullish market"
}
```

### 2. Backend Transformation
All structured fields are merged into ONE human-readable prompt string via `build_prompt()`:

```
EMA crossover strategy. Symbol: BTCUSD. Timeframe: 15MIN. Chart Type: Candles. Take Profit: 1%. Stop Loss: 1%. Market Context: Bullish market.
```

### 3. OpenAI API Call
**ONLY** the merged prompt string is sent to OpenAI (within OpenAI's required `messages` structure):

```python
{
  "model": "gpt-4",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "<merged prompt string>"}  # ONLY merged prompt
  ],
  "temperature": 0.8
}
```

### 4. Critical Rules

✅ **DO:**
- Merge ALL user inputs into a single prompt string
- Send ONLY the merged prompt to OpenAI
- Keep frontend contract unchanged
- Handle future fields automatically (they'll be merged too)

❌ **DON'T:**
- Send structured fields (symbol, timeframe, chart_type, etc.) separately
- Include request payload data in response
- Modify frontend request structure
- Send any fields other than the merged prompt string

## Files Involved

1. **`app/services/prompt_builder.py`**
   - Merges all structured fields into one prompt string
   - Handles: prompt, symbol, timeframe, chart_type, take_profit, stop_loss, trailing_stop, current_price, market_context
   - Automatically includes any future fields added from frontend

2. **`app/api/routes_ai_strategy.py`**
   - Receives structured payload from frontend
   - Calls `build_prompt()` to merge all fields
   - Passes ONLY merged prompt string to OpenAI service

3. **`app/services/openai_service.py`**
   - Receives ONLY the merged prompt string
   - Sends it to OpenAI within messages structure
   - Validates that no structured fields leak into API call

## Validation

The system includes validation to ensure:
- No structured fields (symbol, timeframe, chart_type, take_profit, stop_loss) are sent to OpenAI
- All fields are properly merged into the prompt string
- Request payload remains internal-only (never returned in response)

## Benefits

1. **Security**: Request payload data never leaks to external services
2. **Flexibility**: Future fields automatically included in prompt
3. **Simplicity**: Single prompt string is easier for AI to process
4. **Consistency**: All parameters always embedded in prompt
5. **Maintainability**: Clear separation between input and output

## Example Flow

```
Frontend Request
  ↓
{ prompt, symbol, timeframe, chart_type, take_profit, stop_loss, ... }
  ↓
build_prompt() → Merges ALL into ONE string
  ↓
"Strategy description. Symbol: BTCUSD. Timeframe: 15MIN. Chart Type: Candles. Take Profit: 1%. Stop Loss: 1%."
  ↓
OpenAI API Call (ONLY merged prompt)
  ↓
Response (parsed strategy only, no request data)
```

---

**Last Updated**: Implementation verified and documented
**Status**: ✅ Active and Enforced
