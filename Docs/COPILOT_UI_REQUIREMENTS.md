# Copilot UI Requirements - Delta / ChatGPT Premium Feel

## 🔥 PART 1 — REMOVE THESE UI SECTIONS (COPILOT MODE)

### ❌ COMPLETELY REMOVE / HIDE (FOR COPILOT)

Hide the entire marked section from the UI:

- ❌ **AI Guidance box**
- ❌ **Advanced Trading Parameters**
- ❌ **Chart Type selector**
- ❌ **Trading Session**
- ❌ **Take Profit / Stop Loss inputs**
- ❌ **Trailing Stop**
- ❌ **Max Trades / Day**
- ❌ **Generate Strategy button**
- ❌ **Reset button**

📌 **These fields must NOT be visible in Copilot mode.**  
📌 **They will be used later internally or during deploy — not now.**

## ✅ PART 2 — KEEP ONLY THESE (MINIMAL UI)

### ✅ Visible in Copilot Mode

1. **Single Chat Input (Strategy Description)**
   - Multiline textarea
   - Placeholder text: `"Describe your trading strategy in simple language…"`

2. **Chat History Panel**
   - Shows Copilot responses
   - Shows user messages

3. **UP ARROW (↑) SEND BUTTON**
   - ChatGPT / Delta style
   - Bottom-right inside input box
   - ❌ No "Generate Strategy" text
   - ❌ No play / right arrow icon

## 🎯 PART 3 — SEND BUTTON (VERY IMPORTANT)

### 🔺 SEND BUTTON SPEC

- **Icon**: UP ARROW (↑) only
- **Behavior**:
  - `Enter` → Send message
  - `Shift + Enter` → New line
  - `Click ↑` → Send message
  - Disabled only when input is empty

📌 **This must feel like chat, not execution.**

## 🎯 UI Behavior (Locked)

### Chat Input Component

- **Type**: Single multiline chat input
- **Placeholder**: `"Describe your trading strategy…"`
- **Send Button**: **UP ARROW (↑)** inside input (bottom-right corner)
- **Keyboard Shortcuts**:
  - `Enter` → Send message
  - `Shift + Enter` → New line
- **Button State**: Arrow disabled only when input is empty

### Visual Design

- **Up Arrow Icon**: Use standard up arrow (↑) - NOT right arrow (→)
- **Position**: Bottom-right inside input field
- **Style**: Minimal, clean, ChatGPT-like
- **Color**: Subtle gray, becomes active/colored when input has text

## 🧠 Psychology

- **Up arrow** = chat / thinking / conversation
- **Generate button** = execution / final action (we don't want this in Copilot)

The up arrow encourages dialogue and exploration, not execution.

## 🔁 Final User Flow (DO NOT CHANGE)

1. **User chats freely** (↑ send button)
2. **Copilot summarizes** + asks missing questions
3. **User types CONFIRM / BACKTEST / PROCEED** (explicit intent)
4. **System asks symbol & timeframe** (via confirm endpoint)
5. **Existing backtest engine runs**
6. **User may save or deploy**

## 🔒 PART 5 — UX & FLOW RULES (LOCKED)

### Copilot Mode Characteristics

- ✅ **Copilot mode = no forms**
- ✅ **No validation errors**
- ✅ **No technical language**
- ✅ **No execution wording**
- ✅ **Everything feels exploratory**

### ❌ NEVER show technical errors like:
- "emas missing"
- "invalid schema"
- "indicator not supported"
- "OUTPUT_ERROR: ..."
- Any technical stack traces

### ✅ ALWAYS show human language:
- "I understand your strategy as…"
- "I just need to clarify…"
- "Please confirm to proceed"
- "Something went wrong while preparing the strategy. Please review your strategy and try again."

### 🧷 FINAL GUIDING LINE

**Copilot UI is a chat experience, not a configuration form.**  
**Users should feel safe to think, refine, and confirm before any execution.**

## 🎯 Confirmation Flow

### Strict Confirmation Words

Only these exact words (case-insensitive) trigger the next step:
- `CONFIRM`
- `BACKTEST`
- `PROCEED`

### Words that do NOT trigger:
- "yes"
- "ok"
- "ready"
- "sure"
- Any other variations

This prevents accidental flow jumps and ensures explicit user intent.

## 📱 Responsive Design

- **Mobile**: Full-width input, up arrow clearly visible
- **Desktop**: Comfortable width, up arrow in bottom-right
- **Tablet**: Adaptive layout

## 🧩 PART 4 — WHEN TO SHOW SYMBOL & TIMEFRAME

### ❌ NOT SHOWN INITIALLY

- Symbol
- Timeframe

### ✅ SHOW ONLY WHEN:

User types **CONFIRM** / **BACKTEST**

Then show a small modal or inline section:

```
┌─────────────────────────────────────┐
│  Select Symbol                      │
│  [BTCUSD ▼]                         │
│                                     │
│  Select Timeframe                   │
│  [15MIN ▼]                         │
│                                     │
│  [ Run Backtest ]                  │
└─────────────────────────────────────┘
```

📌 **Only these two fields**  
📌 **Nothing else**

## 🎨 Example UI Layout

### Copilot Mode (Initial)
```
┌─────────────────────────────────────────┐
│  Copilot Chat                           │
├─────────────────────────────────────────┤
│                                         │
│  [User Message 1]                       │
│  [Copilot Response 1]                   │
│                                         │
│  [User Message 2]                       │
│  [Copilot Response 2]                   │
│                                         │
├─────────────────────────────────────────┤
│  Describe your trading strategy…    [↑] │
└─────────────────────────────────────────┘
```

### After CONFIRM (Symbol & Timeframe Modal)
```
┌─────────────────────────────────────────┐
│  Copilot Chat                           │
├─────────────────────────────────────────┤
│  [Previous conversation...]            │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │ Select Symbol                     │  │
│  │ [BTCUSD ▼]                        │  │
│  │                                   │  │
│  │ Select Timeframe                  │  │
│  │ [15MIN ▼]                         │  │
│  │                                   │  │
│  │ [ Run Backtest ]                  │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## 🔐 Final Lock

- **UP ARROW (↑)** = CHAT ✅
- **GENERATE BUTTON** = ❌ REMOVED

## Implementation Notes

### Frontend Components Needed

1. **ChatInput Component**
   - Multiline textarea
   - Placeholder: "Describe your trading strategy in simple language…"
   - Up arrow button (bottom-right)
   - Enter/Shift+Enter handling
   - Disabled state when empty

2. **ChatMessage Component**
   - User messages (right-aligned)
   - Copilot messages (left-aligned)
   - Clean, minimal styling
   - No technical formatting

3. **ChatContainer Component**
   - Scrollable message area
   - Input at bottom
   - Auto-scroll to latest message

4. **SymbolTimeframeModal Component** (Shown only after CONFIRM)
   - Small modal or inline section
   - Symbol dropdown
   - Timeframe dropdown
   - "Run Backtest" button
   - Only these two fields, nothing else

### UI State Management

- **Copilot Mode** (default):
  - Show: Chat input, Chat history, UP ARROW button
  - Hide: All form fields, buttons, advanced options

- **After CONFIRM/BACKTEST**:
  - Show: Symbol & Timeframe modal
  - Hide: Chat input (or keep it disabled)

- **After Backtest**:
  - Show: Backtest results
  - Show: Save/Deploy options (existing flow)

### API Integration

- `POST /auth/copilot/message` - Send chat message
- `POST /auth/copilot/confirm` - Confirm and generate strategy (requires symbol, timeframe)
- `POST /auth/copilot/backtest` - Run backtest

### State Management

- Session ID (auto-generated or persisted)
- Conversation history
- `is_ready` flag (from API response)
- Loading states
- Error states (human-readable only)
- Modal visibility (symbol/timeframe)

### Component Visibility Rules

```javascript
// Copilot Mode - Show only these
const copilotModeVisible = {
  chatInput: true,
  chatHistory: true,
  upArrowButton: true,
  // Everything else: false
  aiGuidance: false,
  advancedParams: false,
  chartType: false,
  tradingSession: false,
  takeProfit: false,
  stopLoss: false,
  trailingStop: false,
  maxTrades: false,
  generateButton: false,
  resetButton: false,
  symbolTimeframe: false, // Only show after CONFIRM
};

// After CONFIRM - Show symbol/timeframe modal
const afterConfirmVisible = {
  symbolTimeframe: true,
  runBacktestButton: true,
};
```

