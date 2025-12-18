# AI Strategy Builder API Documentation

## Overview
The AI Strategy Builder API allows you to generate trading strategies using natural language descriptions powered by OpenAI.

## Setup

### 1. Environment Variables
Add the following to your `.env` file:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini  # Optional, defaults to gpt-4o-mini
```

### 2. Start the API Server
```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## API Endpoints

### 1. Generate AI Strategy
**POST** `/auth/ai-strategy/generate`

Generate a trading strategy from natural language description.

#### Request Body
```json
{
  "prompt": "Buy when BTC price goes above 90000",
  "symbol": "BTCUSD",
  "current_price": 89000.50,  // Optional
  "market_context": "Bullish trend",  // Optional
  "save_strategy": false  // Optional, default: false
}
```

#### Response
```json
{
  "success": true,
  "strategy": {
    "symbol": "BTCUSD",
    "condition": {
      "type": "price_above",
      "value": 90000
    }
  },
  "message": "Strategy generated successfully",
  "strategy_id": 4  // Only present if save_strategy was true
}
```

#### Example Prompts
- "Buy when BTC price goes above 90000"
- "Alert me when price drops below 85000"
- "Notify when price is between 88000 and 92000"
- "Sell when ETH price exceeds 3000"

### 2. List All Strategies
**GET** `/auth/ai-strategy/list`

Get all saved strategies.

#### Response
```json
{
  "success": true,
  "count": 3,
  "strategies": [
    {
      "id": 1,
      "symbol": "BTCUSD",
      "condition": {
        "type": "price_above",
        "value": 90500
      }
    },
    ...
  ]
}
```

### 3. Get Strategy by ID
**GET** `/auth/ai-strategy/{strategy_id}`

Get a specific strategy by its ID.

#### Response
```json
{
  "success": true,
  "strategy": {
    "id": 1,
    "symbol": "BTCUSD",
    "condition": {
      "type": "price_above",
      "value": 90500
    }
  }
}
```

## Strategy Condition Types

### price_above
Triggers when price exceeds a threshold.
```json
{
  "type": "price_above",
  "value": 90000
}
```

### price_below
Triggers when price falls below a threshold.
```json
{
  "type": "price_below",
  "value": 85000
}
```

### price_between
Triggers when price is within a range.
```json
{
  "type": "price_between",
  "value": {
    "min": 88000,
    "max": 92000
  }
}
```

## Usage Examples

### cURL Example
```bash
curl -X POST "http://localhost:8000/auth/ai-strategy/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Buy when BTC price goes above 90000",
    "symbol": "BTCUSD",
    "save_strategy": true
  }'
```

### JavaScript/Fetch Example
```javascript
const response = await fetch('http://localhost:8000/auth/ai-strategy/generate', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    prompt: 'Buy when BTC price goes above 90000',
    symbol: 'BTCUSD',
    save_strategy: true
  })
});

const data = await response.json();
console.log(data);
```

### Python Example
```python
import requests

url = "http://localhost:8000/auth/ai-strategy/generate"
payload = {
    "prompt": "Buy when BTC price goes above 90000",
    "symbol": "BTCUSD",
    "save_strategy": True
}

response = requests.post(url, json=payload)
data = response.json()
print(data)
```

## Error Handling

### Missing API Key
If `OPENAI_API_KEY` is not set, the API will return:
```json
{
  "success": false,
  "message": "Failed to generate strategy. Please check your OpenAI API key and try again."
}
```

### Invalid Prompt
```json
{
  "detail": "Prompt is required"
}
```

## Notes

- The API automatically retrieves current price from Redis if `current_price` is not provided
- Strategies are saved to `strategies.json` when `save_strategy: true`
- Strategy IDs are auto-incremented
- The engine will automatically pick up new strategies from `strategies.json`

