# Fix 422 Unprocessable Entity Error - Report

## Problem Identified

The FastAPI endpoint `/auth/ai-strategy/generate` was returning **422 Unprocessable Entity** because:

1. **Field Name Mismatch**: Request body used `description` but model expected `prompt`
2. **Missing Field**: Request body included `type` field which was not in the allowed fields list

## Sample Request That Was Failing

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "type": "indicator_based",
  "description": "EMA crossover scalping strategy"
}
```

## Root Cause

1. **AIStrategyRequest Model** (Line 33) required `prompt: str` but request sent `description`
2. **Validation Logic** (Lines 78-91) rejected `type` field as it wasn't in `allowed_fields` set
3. **Pydantic Validation** failed because required field `prompt` was missing

## Solution Applied

### 1. Updated Pydantic Model (`AIStrategyRequest`)

**Changes:**
- Made `prompt` optional (was required)
- Added `description` as optional field (alias for `prompt`)
- Added `type` as optional field
- Added `@model_validator` to normalize `description` → `prompt`

**Code:**
```python
class AIStrategyRequest(BaseModel):
    prompt: Optional[str] = Field(default=None, description="Natural language description...")
    description: Optional[str] = Field(default=None, description="Alias for 'prompt'...")
    type: Optional[str] = Field(default=None, description="Strategy type hint...")
    
    @model_validator(mode='after')
    def normalize_prompt(self):
        """Normalize 'description' to 'prompt' if prompt is not provided."""
        if not self.prompt and self.description:
            self.prompt = self.description
        elif not self.prompt and not self.description:
            raise ValueError("Either 'prompt' or 'description' must be provided")
        return self
```

### 2. Updated Allowed Fields List

**Changes:**
- Added `'description'` to `allowed_fields`
- Added `'type'` to `allowed_fields`

**Code:**
```python
allowed_fields = {
    'prompt', 'description', 'type', 'symbol', 'timeframe', 'chart_type', 
    'take_profit', 'stop_loss', 'trailing_stop',
    'trading_session', 'max_trades_per_day',
    'current_price', 'market_context'
}
```

## Verification

### ✅ Corrected Request Model

```python
class AIStrategyRequest(BaseModel):
    prompt: Optional[str] = None
    description: Optional[str] = None  # Maps to prompt
    type: Optional[str] = None  # Strategy type hint
    symbol: Optional[str] = "BTCUSD"
    timeframe: Optional[str] = None
    chart_type: Optional[str] = None
    # ... other fields
```

### ✅ Corrected Endpoint Signature

```python
@router.post("/ai-strategy/generate", response_model=AIStrategyResponse)
def generate_ai_strategy(request: AIStrategyRequest, authorization: Optional[str] = Header(None)):
    # Endpoint now accepts both 'prompt' and 'description'
    # 'type' field is accepted but not used in prompt building (optional hint)
```

## Working Request Examples

### Example 1: Using `description` (Original Request)

```json
POST /auth/ai-strategy/generate
Content-Type: application/json

{
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "type": "indicator_based",
  "description": "EMA crossover scalping strategy"
}
```

**Expected Response:** HTTP 200 OK

### Example 2: Using `prompt` (Backward Compatible)

```json
POST /auth/ai-strategy/generate
Content-Type: application/json

{
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "prompt": "EMA crossover scalping strategy"
}
```

**Expected Response:** HTTP 200 OK

### Example 3: Minimal Request (Only Required Fields)

```json
POST /auth/ai-strategy/generate
Content-Type: application/json

{
  "description": "Buy when price crosses above 20 EMA"
}
```

**Expected Response:** HTTP 200 OK

## Swagger/Postman Compatibility

✅ **Swagger UI**: Will show both `prompt` and `description` as optional fields
✅ **Postman**: Both field names will work
✅ **Backward Compatibility**: Existing clients using `prompt` will continue to work

## Validation Rules

1. ✅ Either `prompt` OR `description` must be provided (not both required)
2. ✅ `type` field is optional and accepted
3. ✅ All other fields remain optional with defaults
4. ✅ Extra fields (not in `allowed_fields`) are still rejected

## Testing

To test the fix:

```bash
curl -X POST "http://127.0.0.1:8000/auth/ai-strategy/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "type": "indicator_based",
    "description": "EMA crossover scalping strategy"
  }'
```

**Expected:** HTTP 200 OK (not 422)

## Files Modified

1. `app/api/routes_ai_strategy.py`
   - Updated `AIStrategyRequest` model (lines 26-48)
   - Updated `allowed_fields` set (lines 93-98)

## Status

✅ **FIXED** - The endpoint now accepts the request body format without returning 422 errors.

