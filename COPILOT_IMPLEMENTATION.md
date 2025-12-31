# Copilot Implementation - Delta-Style Conversational Strategy Builder

## Overview

This implementation adds a **Copilot-first Strategy Builder** that allows users to freely describe and refine strategies through natural conversation before generating JSON and running backtests. This is inspired by Delta Exchange's smooth UX.

## Key Principles

✅ **Safe Migration**: Existing APIs remain untouched  
✅ **Conversational First**: No JSON generation until user confirms  
✅ **Human-Readable Errors**: Never expose technical errors to users  
✅ **No Hard-Coded Templates**: Accepts any strategy description  
✅ **Delta-Style UX**: Smooth, conversational experience  

## Architecture

### 3-Step Flow

#### Step 1: Copilot Mode (NEW)
- **Endpoint**: `POST /auth/copilot/message`
- **Purpose**: Conversational strategy description
- **Behavior**:
  - Accepts ANY plain text (strategy idea, indicator code, partial logic)
  - Does NOT generate JSON
  - Does NOT validate indicators
  - Does NOT ask for symbol or timeframe
  - Summarizes what user said
  - Asks only what is missing
- **Trigger Words**: `CONFIRM`, `YES`, `BACKTEST`, `PROCEED`

#### Step 2: Backtest Mode (EXISTING ENGINE)
- **Endpoint**: `POST /auth/copilot/confirm`
- **Purpose**: Convert conversation to JSON and run backtest
- **Behavior**:
  - Asks for symbol and timeframe (from request)
  - Converts confirmed understanding into Unified Strategy JSON
  - Runs existing BacktestEngine
  - Applies all validations internally (not user-facing)
- **Error Handling**: All errors shown as "Something went wrong while preparing the strategy. Please review your strategy and try again."

#### Step 3: Deploy Mode (EXISTING FLOW)
- **Endpoint**: `POST /auth/copilot/backtest` (for backtest)
- **Purpose**: Run backtest and deploy
- **Behavior**:
  - Runs backtest using existing BacktestEngine
  - Saves strategy (uses existing save_strategy service)
  - Deploys live (uses existing execution flow)

## Implementation Details

### New Files Created

1. **`app/services/copilot_service.py`**
   - `process_copilot_message()`: Handles conversational AI interaction
   - `save_copilot_session()`: Stores conversation in Redis
   - `load_copilot_session()`: Retrieves conversation from Redis
   - `create_copilot_session()`: Creates new session ID

2. **`app/api/routes_copilot.py`**
   - `POST /auth/copilot/message`: Process conversational messages
   - `POST /auth/copilot/confirm`: Confirm and generate strategy JSON
   - `POST /auth/copilot/backtest`: Run backtest on generated strategy
   - `DELETE /auth/copilot/session/{session_id}`: Delete session

### Modified Files

1. **`app/main.py`**
   - Added copilot router registration
   - No changes to existing routes

### Session Management

- **Storage**: Redis (key: `COPILOT_SESSION:{session_id}`)
- **Expiration**: 1 hour (3600 seconds)
- **Format**: JSON array of conversation messages
- **Structure**: `[{"role": "user|assistant", "content": "..."}, ...]`

### OpenAI Usage

#### Copilot Mode
- **System Prompt**: Defines conversational role (no JSON generation)
- **User Prompt**: Plain conversation text only
- **No Schema Instructions**: No JSON structure hints
- **No Validation**: Accepts any strategy description
- **No Readiness Inference**: Backend does NOT decide if strategy is ready
- **Strict Confirmation**: Only "CONFIRM", "BACKTEST", or "PROCEED" trigger next step

#### Compiler Mode (After Confirmation)
- **Reuses**: Existing `generate_strategy()` function
- **Uses**: Existing unified schema validation
- **Triggered**: Only after explicit user confirmation

### Error Handling

All errors are converted to human-readable messages:

❌ **Never Exposed**:
- "emas array missing"
- "invalid schema"
- "indicator not supported"
- Technical stack traces

✅ **Always Shown**:
- "Something went wrong while preparing the strategy. Please review your strategy and try again."
- "Something went wrong while running the backtest. Please try again."

### Credit System

- **Copilot Messages**: No credit deduction (conversational only)
- **Confirm/Generate**: Deducts 1 credit (same as `/ai-strategy/generate`)
- **Backtest**: Deducts 1 credit (same as `/ai-strategy/backtest`)

## API Endpoints

### 1. Send Message (Copilot Mode)

```http
POST /auth/copilot/message
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "COPILOT-abc123",  // Optional, auto-generated if not provided
  "message": "Buy when price breaks yesterday's high"
}
```

**Response**:
```json
{
  "success": true,
  "session_id": "COPILOT-abc123",
  "response": "I understand you want to buy when the price breaks yesterday's high. To complete your strategy, I need to know:\n1. When do you want to sell?\n2. What's your profit target?\n3. What's your stop loss?",
  "is_ready": false,
  "missing_details": [],
  "summary": null
}
```

### 2. Confirm Strategy (Compiler Mode)

```http
POST /auth/copilot/confirm
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "COPILOT-abc123",
  "symbol": "BTCUSD",
  "timeframe": "15MIN",
  "chart_type": "candles"
}
```

**Response**:
```json
{
  "success": true,
  "strategy": {
    "symbol": "BTCUSD",
    "strategy_type": "breakout",
    "logic": {...},
    "risk": {...},
    "meta": {...}
  },
  "message": "Strategy generated successfully. Ready for backtest.",
  "strategy_id": null
}
```

### 3. Run Backtest

```http
POST /auth/copilot/backtest
Authorization: Bearer <token>
Content-Type: application/json

{
  "strategy": {
    "symbol": "BTCUSD",
    "strategy_type": "breakout",
    "logic": {...},
    "risk": {...},
    "meta": {...}
  }
}
```

**Response**:
```json
{
  "success": true,
  "results": {
    "summary": {...},
    "trades": [...],
    "monthly_performance": {...}
  },
  "message": "Backtest completed successfully"
}
```

### 4. Delete Session

```http
DELETE /auth/copilot/session/{session_id}
```

## Integration with Existing System

### Existing Endpoints (Unchanged)

- ✅ `/auth/ai-strategy/generate` - Still works as before
- ✅ `/auth/ai-strategy/backtest` - Still works as before
- ✅ `/auth/strategies/save` - Still works as before
- ✅ All other endpoints - Unchanged

### Reused Services

- ✅ `openai_service.generate_strategy()` - Used in Compiler mode
- ✅ `BacktestEngine` - Used for backtesting
- ✅ `prompt_builder.build_prompt()` - Used to build final prompt
- ✅ `credit_service` - Used for credit checks
- ✅ `strategy_save_service` - Used for saving strategies

## UI Requirements (Frontend)

### 🎨 Delta / ChatGPT Premium Feel

#### ❌ REMOVE COMPLETELY
- "Generate Strategy" button
- Any button that implies execution or final action

#### ✅ ADD — ChatGPT / Delta Style UP ARROW (↑) SEND BUTTON

**THIS IS IMPORTANT — NO MISTAKE HERE**

- Use **UP ARROW (↑)** icon ONLY
- ❌ No right arrow
- ❌ No play icon
- ❌ No text like "Generate" or "Run"

#### 🎯 UI Behavior (Locked)

- Single multiline chat input
- Placeholder: `"Describe your trading strategy…"`
- **UP ARROW (↑)** inside input (bottom-right)
- Arrow sends message
- Enter → Send
- Shift + Enter → New line
- Arrow disabled only when input is empty

#### 🧠 Psychology

- **Up arrow** = chat / thinking
- **Generate button** = execution (we don't want this in Copilot)

### 🔁 Final User Flow (DO NOT CHANGE)

1. User chats freely (↑ send)
2. Copilot summarizes + asks missing questions
3. User types **CONFIRM** / **BACKTEST** / **PROCEED**
4. System asks symbol & timeframe
5. Existing backtest engine runs
6. User may save or deploy

### 🔒 UX Rules (VERY IMPORTANT)

#### ❌ NEVER show technical errors like:
- "emas missing"
- "invalid schema"
- "indicator not supported"

#### ✅ ALWAYS show human language:
- "I understand your strategy as…"
- "I just need to clarify…"
- "Please confirm to proceed"

## Testing

### Test Flow

1. **Start Conversation**:
   ```bash
   POST /auth/copilot/message
   {"message": "Buy when EMA 20 crosses above EMA 50"}
   ```

2. **Continue Conversation**:
   ```bash
   POST /auth/copilot/message
   {"session_id": "...", "message": "Sell when it crosses below, target 500 points, stop loss 300 points"}
   ```

3. **Explicit Confirmation** (strict - only these words):
   ```bash
   POST /auth/copilot/message
   {"session_id": "...", "message": "CONFIRM"}
   ```
   Note: Only "CONFIRM", "BACKTEST", or "PROCEED" trigger next step. Words like "yes", "ok", "ready" do NOT trigger.

4. **Confirm Strategy**:
   ```bash
   POST /auth/copilot/confirm
   {"session_id": "...", "symbol": "BTCUSD", "timeframe": "15MIN"}
   ```

5. **Run Backtest**:
   ```bash
   POST /auth/copilot/backtest
   {"strategy": {...}}
   ```

## Future Enhancements

- [ ] Add conversation context window management
- [ ] Add strategy refinement suggestions
- [ ] Add multi-turn clarification flow
- [ ] Add conversation export/import
- [ ] Add strategy templates from conversation history

## Notes

- **Session Expiration**: Sessions expire after 1 hour of inactivity
- **Redis Dependency**: Copilot requires Redis for session storage
- **OpenAI Dependency**: Requires valid OPENAI_API_KEY
- **Credit System**: Follows existing credit deduction rules
- **Error Handling**: All errors are user-friendly (no technical details)

## Migration Notes

This implementation is **completely additive**. No existing functionality is modified or removed. The new Copilot flow runs in parallel with the existing `/ai-strategy/generate` endpoint.

Users can choose:
- **Old Flow**: Direct JSON generation via `/auth/ai-strategy/generate`
- **New Flow**: Conversational Copilot via `/auth/copilot/message` → `/auth/copilot/confirm`

Both flows use the same underlying services and produce the same strategy JSON format.

