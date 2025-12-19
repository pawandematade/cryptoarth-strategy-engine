import json
import logging
import uuid
from typing import Dict, Optional
from openai import OpenAI
from app.config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = None

def initialize_client():
    """Initialize or reinitialize the OpenAI client"""
    global client
    from app.config import OPENAI_API_KEY
    if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here":
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            logger.info("OpenAI client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            client = None
            return False
    else:
        logger.warning("OPENAI_API_KEY not set. AI strategy builder will not work.")
        client = None
        return False

# Initialize on module load
if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here":
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        client = None
else:
    logger.warning("OPENAI_API_KEY not set. AI strategy builder will not work.")


def generate_strategy(user_prompt: str) -> Optional[Dict]:
    """
    Generate a trading strategy using OpenAI based on user's natural language prompt.
    
    IMPORTANT: This function receives ONLY a prompt string.
    All trading parameters (symbol, timeframe, TP, SL, etc.) must be embedded in the prompt.
    
    Args:
        user_prompt: Complete prompt string with all trading parameters embedded
    
    Returns:
        dict: Strategy object with symbol and condition, or None if generation fails
    """
    # Reinitialize client if needed (in case .env was updated)
    if not client:
        logger.warning("OpenAI client not initialized. Attempting to reinitialize...")
        if not initialize_client():
            logger.error("OpenAI client not initialized. Please set OPENAI_API_KEY in environment variables and restart the server.")
            return None
    
    try:
        # System prompt to guide the AI
        system_prompt = """You are an expert trading strategy builder for cryptocurrency markets. 
Your task is to convert user's natural language trading strategy descriptions into structured JSON format.

CRITICAL: You MUST capture ALL conditions and requirements mentioned in the user's prompt. 
Different descriptions MUST result in different strategy structures, even if they seem similar.
Pay close attention to additional conditions like "candle close", "high break", "wait", "after", etc.

The strategy format should be:
{
    "symbol": "BTCUSD",
    "condition": {
        "type": "price_above" | "price_below" | "price_between" | "supertrend" | "ema_crossover" | "moving_average" | "rsi" | "macd" | "bollinger_bands",
        "value": <number> or {"min": <number>, "max": <number>} or null for indicator strategies
    },
    "parameters": {
        // For EMA Crossover: {"ema_fast": 9, "ema_slow": 21, "tp_percent": 1, "sl_percent": 1}
        // For SuperTrend: {"period": 7, "multiplier": 3}
        // For Moving Average: {"period": 20, "type": "SMA" | "EMA"}
        // For RSI: {"period": 14, "oversold": 30, "overbought": 70}
        // Additional conditions can be stored here:
        // "wait_candle_close": true/false - wait for candle to close before executing
        // "require_high_break": true/false - require high to break before taking trade
        // "entry_condition": "crossover" | "candle_close" | "high_break" - specific entry condition
    }
}

Supported condition types:
- "price_above": Trigger when price is above a value
- "price_below": Trigger when price is below a value
- "price_between": Trigger when price is between min and max values
- "ema_crossover": EMA crossover strategy (requires ema_fast and ema_slow in parameters)
- "supertrend": SuperTrend indicator strategy (requires period and multiplier in parameters)
- "moving_average": Moving average crossover strategy
- "rsi": RSI indicator strategy
- "macd": MACD indicator strategy
- "bollinger_bands": Bollinger Bands strategy

Examples showing how to capture DIFFERENT conditions:
- "EMA 9 cross above 21 EMA buy and EMA 9 cross below 21 EMA sell, TP 1% SL 1%" -> 
  {"type": "ema_crossover", "value": null, "parameters": {"ema_fast": 9, "ema_slow": 21, "tp_percent": 1, "sl_percent": 1}}

- "EMA 9 cross above 21 EMA buy and EMA 9 cross below 21 EMA sell once cross over candle close and close candle high break then take trade" -> 
  {"type": "ema_crossover", "value": null, "parameters": {"ema_fast": 9, "ema_slow": 21, "tp_percent": 1, "sl_percent": 1, "wait_candle_close": true, "require_high_break": true, "entry_condition": "candle_close_high_break"}}

- "9 and 21 EMA crossover strategy with 1% TP and 1% SL" -> 
  {"type": "ema_crossover", "value": null, "parameters": {"ema_fast": 9, "ema_slow": 21, "tp_percent": 1, "sl_percent": 1}}

- "Buy when BTC price goes above 90000" -> {"type": "price_above", "value": 90000}
- "Super trend 7 3" or "supertrend 7 3" -> {"type": "supertrend", "value": null, "parameters": {"period": 7, "multiplier": 3}}
- "Sell when price drops below 85000" -> {"type": "price_below", "value": 85000}

IMPORTANT RULES:
1. ALWAYS capture ALL conditions mentioned in the user prompt - do not ignore any part
2. If user mentions "candle close", "wait for candle close", "after candle close" - add "wait_candle_close": true
3. If user mentions "high break", "break high", "candle high break" - add "require_high_break": true
4. If user mentions both "candle close" AND "high break" - add both conditions
5. Different prompts MUST result in different parameter structures
6. For EMA Crossover: Extract fast EMA period, slow EMA period, TP percentage, and SL percentage from the prompt
7. For SuperTrend: Extract period and multiplier from the prompt (e.g., "7 3" means period=7, multiplier=3)
8. Always include the "parameters" field for indicator-based strategies
9. TP and SL percentages should be extracted and included in parameters
10. Return ONLY valid JSON, no additional text or explanation."""

        # CRITICAL: user_prompt contains ALL parameters merged into ONE string
        # Format: "strategy description. Symbol: BTCUSD. Timeframe: 15MIN. Chart Type: Candles. Take Profit: 2000 points. Stop Loss: 2000 points."
        # OpenAI receives ONLY this prompt string - no other fields
        
        # Generate unique request ID for this call
        unique_id = str(uuid.uuid4())
        
        # Build user message - the prompt contains EVERYTHING
        user_message = f"""Convert this complete trading strategy description into JSON format.
The description below contains the strategy logic AND all trading parameters in a single line.
YOU MUST extract and use ALL parameters mentioned in the description.

Request ID: {unique_id}

Complete Strategy Description (all parameters included):
{user_prompt}

MANDATORY INSTRUCTIONS - YOU MUST FOLLOW THESE:
1. Extract the strategy type from "Strategy Description:" line (e.g., EMA crossover, SuperTrend, etc.)
2. Extract Symbol from "Symbol:" line - USE THIS EXACT SYMBOL in your response
3. If "Timeframe:" is provided, note it (important context for the strategy)
4. If "Chart Type:" is provided, note it (important context)
5. If "Take Profit:" is provided, you MUST include it in parameters:
   - If it says "points" → add "tp_point": [value] to parameters
   - If it says "percentage" or "%" → add "tp_percent": [value] to parameters
   - Example: "Take Profit: 2000 points" → "tp_point": 2000
   - Example: "Take Profit: 1%" → "tp_percent": 1
6. If "Stop Loss:" is provided, you MUST include it in parameters:
   - If it says "points" → add "sl_point": [value] to parameters
   - If it says "percentage" or "%" → add "sl_percent": [value] to parameters
   - Example: "Stop Loss: 2000 points" → "sl_point": 2000
   - Example: "Stop Loss: 1%" → "sl_percent": 1
7. If "Trailing Stop:" is provided, include it similarly
8. If "Strategy Description:" contains "candle close" or "high break" or "once", add:
   - "wait_candle_close": true (if candle close mentioned)
   - "require_high_break": true (if high break mentioned)
   - "entry_condition": "candle_close_high_break" (if both mentioned)
9. For SuperTrend: Extract period and multiplier EXACTLY as mentioned
   - "value 7 3" → period=7, multiplier=3
   - "value 10 2" → period=10, multiplier=2
10. Different inputs MUST result in DIFFERENT parameter structures

EXAMPLE INPUT:
Strategy Description: make super trend strategy value 7 3
Symbol: BTCUSD
Timeframe: 15MIN
Chart Type: Candles
Take Profit: 2000 points
Stop Loss: 2000 points

EXAMPLE OUTPUT:
{{
  "symbol": "BTCUSD",
  "condition": {{
    "type": "supertrend",
    "parameters": {{
      "period": 7,
      "multiplier": 3,
      "tp_point": 2000,
      "sl_point": 2000
    }}
  }}
}}

CRITICAL: If parameters are provided (TP, SL, Symbol, Timeframe), you MUST include them in your response.
DO NOT ignore any parameters - they are part of the complete strategy requirements.
Return only the JSON object with 'symbol' and 'condition' fields."""

        # CRITICAL: OpenAI API call - we send ONLY the prompt
        # The user_message contains the complete merged prompt with all parameters
        # No other fields (symbol, timeframe, etc.) are sent separately
        
        # OpenAI API requires model + messages structure
        # We send ONLY the merged prompt string in the user message
        # The request body contains: model, messages (system + user prompt), temperature, response_format
        # NO other user-provided fields (symbol, timeframe, chart_type, take_profit, stop_loss) are sent
        
        api_params = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}  # ONLY the merged prompt string
            ],
            "temperature": 0.8,
        }
        
        # Only add response_format for compatible models
        if "gpt-4" in OPENAI_MODEL or "gpt-3.5-turbo" in OPENAI_MODEL:
            api_params["response_format"] = {"type": "json_object"}
        
        # FINAL CHECK: api_params contains ONLY OpenAI-required fields
        # - model (required by OpenAI)
        # - messages (required by OpenAI, contains system prompt + user prompt)
        # - temperature (optional)
        # - response_format (optional, for JSON mode)
        # NO symbol, timeframe, chart_type, take_profit, stop_loss fields
        
        response = client.chat.completions.create(**api_params)
        
        # Extract and parse the response
        content = response.choices[0].message.content.strip()
        logger.info("✅ OpenAI response received")
        
        # Try to extract JSON from the response (in case there's extra text)
        # First, try direct parsing
        try:
            strategy_data = json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON object in the response using a more flexible regex
            import re
            # Look for JSON object that contains symbol and condition
            json_match = re.search(r'\{[^{}]*(?:"symbol"[^{}]*"condition"|"condition"[^{}]*"symbol")[^{}]*\}', content, re.DOTALL)
            if json_match:
                try:
                    strategy_data = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    # Try to extract JSON from code blocks
                    json_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                    if json_block:
                        strategy_data = json.loads(json_block.group(1))
                    else:
                        raise json.JSONDecodeError("Could not find valid JSON in response", content, 0)
            else:
                # Try to extract JSON from code blocks
                json_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                if json_block:
                    strategy_data = json.loads(json_block.group(1))
                else:
                    raise json.JSONDecodeError("Could not find valid JSON in response", content, 0)
        
        # Validate structure
        if "symbol" not in strategy_data or "condition" not in strategy_data:
            logger.error("Invalid strategy structure from OpenAI")
            return None
        
        condition = strategy_data.get("condition", {})
        if "type" not in condition:
            logger.error("Missing condition type in strategy")
            return None
        
        # Extract symbol from OpenAI response or prompt
        # Symbol should be in OpenAI's response, but if not, extract from prompt
        if "symbol" not in strategy_data or not strategy_data.get("symbol"):
            # Try to extract from prompt (look for "Symbol: XXX" pattern)
            import re
            symbol_match = re.search(r'Symbol:\s*([A-Z0-9]+)', user_prompt, re.IGNORECASE)
            if symbol_match:
                strategy_data["symbol"] = symbol_match.group(1).upper()
                logger.info(f"✅ Extracted symbol from prompt: {strategy_data['symbol']}")
            else:
                strategy_data["symbol"] = "BTCUSD"  # Default fallback
                logger.warning("⚠️ Could not extract symbol, using default: BTCUSD")
        else:
            # Ensure symbol is uppercase
            strategy_data["symbol"] = str(strategy_data["symbol"]).upper()
        
        # Normalize strategy type - handle moving_average as ema_crossover if it has EMA parameters
        if condition.get("type") == "moving_average":
            params = condition.get("parameters", {}) or strategy_data.get("parameters", {})
            if params.get("ema_fast") or params.get("fast_period") or params.get("period_fast") or \
               (params.get("period") and params.get("period2")) or (params.get("fast") and params.get("slow")):
                condition["type"] = "ema_crossover"
                strategy_data["condition"]["type"] = "ema_crossover"
                logger.info("Normalized moving_average to ema_crossover based on parameters")
        
        # Ensure parameters field exists (even if empty) for indicator-based strategies
        if condition.get("type") in ["supertrend", "ema_crossover", "moving_average", "rsi", "macd", "bollinger_bands"]:
            if "parameters" not in strategy_data:
                strategy_data["parameters"] = {}
            # Also check if parameters are in condition
            if "parameters" in condition:
                strategy_data["parameters"] = condition.get("parameters", {})
            # Move parameters from condition to root level if needed
            if "parameters" in condition and "parameters" not in strategy_data:
                strategy_data["parameters"] = condition.get("parameters", {})
            
            # For ema_crossover, ensure all required parameters exist with defaults
            # BUT: Only set defaults if OpenAI didn't provide them - don't override OpenAI's response
            if condition.get("type") == "ema_crossover":
                params = strategy_data.get("parameters", {})
                # Only set EMA defaults if not provided by OpenAI
                if not params.get("ema_fast") and not params.get("fast_period"):
                    params["ema_fast"] = 9
                    logger.info("Setting default ema_fast: 9 (not provided by OpenAI)")
                if not params.get("ema_slow") and not params.get("slow_period"):
                    params["ema_slow"] = 21
                    logger.info("Setting default ema_slow: 21 (not provided by OpenAI)")
                # DO NOT set default TP/SL here - they will be set from request if provided
                # Only set defaults if OpenAI didn't provide AND request doesn't have them
                # (This will be handled in routes_ai_strategy.py after merging user params)
                strategy_data["parameters"] = params
                condition["parameters"] = params
                
                # Log what OpenAI returned
                logger.info(f"OpenAI returned parameters: {json.dumps(params, indent=2)}")
        
        logger.info(f"Successfully generated strategy: {strategy_data}")
        return strategy_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI JSON response: {e}")
        logger.error(f"Response content: {content}")
        return None
    except Exception as e:
        logger.error(f"Error generating strategy with OpenAI: {e}", exc_info=True)
        # Log more details about the error
        if hasattr(e, 'response'):
            logger.error(f"OpenAI API error response: {e.response}")
        if hasattr(e, 'status_code'):
            logger.error(f"HTTP status code: {e.status_code}")
        return None


def generate_strategy_with_context(
    user_prompt: str, 
    current_price: Optional[float] = None,
    market_context: Optional[str] = None
) -> Optional[Dict]:
    """
    Generate a trading strategy with additional market context.
    
    DEPRECATED: Use PromptBuilder to build complete prompt instead.
    This function is kept for backward compatibility but should not be used.
    
    Args:
        user_prompt: Complete prompt string (should already include all parameters)
        current_price: Current market price (optional - should be in prompt)
        market_context: Additional market context (optional - should be in prompt)
    
    Returns:
        dict: Strategy object or None if generation fails
    """
    if not client:
        logger.error("OpenAI client not initialized.")
        return None
    
    # Note: Context should already be in the prompt from PromptBuilder
    # This function just passes through to generate_strategy
    return generate_strategy(user_prompt)

