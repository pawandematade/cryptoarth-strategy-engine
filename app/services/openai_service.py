import json
import logging
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


def generate_strategy(user_prompt: str, symbol: str = "BTCUSD") -> Optional[Dict]:
    """
    Generate a trading strategy using OpenAI based on user's natural language prompt.
    
    Args:
        user_prompt: User's description of the strategy they want (e.g., "Buy when price goes above 90000")
        symbol: Trading symbol (default: BTCUSD)
    
    Returns:
        dict: Strategy object with id, symbol, and condition, or None if generation fails
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

        # User prompt with context - emphasize capturing ALL conditions
        # CRITICAL: Use the EXACT user_prompt passed to this function - do not modify it
        user_message = f"""Convert this trading strategy into the JSON format. 
IMPORTANT: Capture EVERY condition and requirement mentioned in the description below.
CRITICAL: Use the EXACT description provided - do not simplify or modify it.

Symbol: {symbol}
Strategy description: {user_prompt}

CRITICAL INSTRUCTIONS - READ CAREFULLY:
1. Analyze the description word by word. Every condition matters.
2. If the description contains ANY of these phrases:
   - "candle close" or "after candle close" or "wait candle close" or "once candle close"
   - "high break" or "break high" or "candle high break" or "close candle high break"
   - "then take trade" or "then enter" or "wait" or "after"
   THEN you MUST add these to the parameters:
   - "wait_candle_close": true (if candle close is mentioned)
   - "require_high_break": true (if high break is mentioned)
   - "entry_condition": "candle_close_high_break" (if both are mentioned)

3. EXAMPLE 1: "EMA 9 cross above 21 EMA buy and EMA 9 cross below 21 EMA sell once cross over candle close and close candle high break then take trade"
   MUST return: {{"type": "ema_crossover", "parameters": {{"ema_fast": 9, "ema_slow": 21, "wait_candle_close": true, "require_high_break": true, "entry_condition": "candle_close_high_break"}}}}

4. EXAMPLE 2: "EMA 9 cross above 21 EMA buy and EMA 9 cross below 21 EMA sell"
   MUST return: {{"type": "ema_crossover", "parameters": {{"ema_fast": 9, "ema_slow": 21}}}}
   DO NOT add wait_candle_close or require_high_break here.

5. Different descriptions MUST result in DIFFERENT parameter structures.
6. Pay attention to EVERY word - "once", "candle close", "high break", "then take trade" are all important.

Return only the JSON object with 'symbol' and 'condition' fields. Include ALL conditions from the description."""

        # Call OpenAI API
        # Note: response_format only works with certain models (gpt-4-turbo, gpt-4o, gpt-3.5-turbo-1106+)
        # For other models, we'll parse the JSON from the response text
        api_params = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.3,  # Lower temperature for more consistent, structured output
        }
        
        # Only add response_format for compatible models
        if "gpt-4" in OPENAI_MODEL or "gpt-3.5-turbo" in OPENAI_MODEL:
            api_params["response_format"] = {"type": "json_object"}
        
        response = client.chat.completions.create(**api_params)
        
        # Extract and parse the response
        content = response.choices[0].message.content.strip()
        logger.info("=" * 80)
        logger.info("🤖 OPENAI RESPONSE RECEIVED")
        logger.info(f"Response Content: {content}")
        logger.info(f"Response Length: {len(content)}")
        logger.info("=" * 80)
        
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
        
        # Ensure symbol matches
        strategy_data["symbol"] = symbol
        
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
    symbol: str = "BTCUSD",
    current_price: Optional[float] = None,
    market_context: Optional[str] = None
) -> Optional[Dict]:
    """
    Generate a trading strategy with additional market context.
    
    Args:
        user_prompt: User's description of the strategy
        symbol: Trading symbol
        current_price: Current market price (optional)
        market_context: Additional market context (optional)
    
    Returns:
        dict: Strategy object or None if generation fails
    """
    if not client:
        logger.error("OpenAI client not initialized.")
        return None
    
    # Enhance prompt with context
    enhanced_prompt = user_prompt
    if current_price:
        enhanced_prompt += f" (Current {symbol} price: ${current_price:,.2f})"
    if market_context:
        enhanced_prompt += f" Market context: {market_context}"
    
    return generate_strategy(enhanced_prompt, symbol)

