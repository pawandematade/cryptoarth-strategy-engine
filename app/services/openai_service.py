import json
import logging
import uuid
import re
from typing import Dict, Optional, Any
from openai import OpenAI
from app.config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = None

def initialize_client():
    """Initialize or reinitialize the OpenAI client"""
    global client
    # Reload config to get latest API key (in case .env was updated)
    import importlib
    import app.config
    importlib.reload(app.config)
    from app.config import OPENAI_API_KEY
    
    if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here" and len(OPENAI_API_KEY) > 10:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            logger.info("✅ OpenAI client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize OpenAI client: {e}")
            client = None
            return False
    else:
        logger.warning("⚠️  OPENAI_API_KEY not set or invalid. AI strategy builder will not work.")
        logger.warning(f"   API Key present: {bool(OPENAI_API_KEY)}")
        logger.warning(f"   API Key length: {len(OPENAI_API_KEY) if OPENAI_API_KEY else 0}")
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
        logger.warning("⚠️  OpenAI client not initialized. Attempting to reinitialize...")
        if not initialize_client():
            logger.error("❌ OpenAI client initialization failed. Please check OPENAI_API_KEY in .env file and restart the server.")
            return None
    
    try:
        # CRITICAL: OpenAI API call - send ONLY the merged prompt string
        # 
        # MANDATORY RULES:
        # 1. user_prompt contains ALL frontend fields merged into ONE human-readable string
        #    (This is done by build_prompt() in routes_ai_strategy.py)
        # 2. Send ONLY the merged prompt string to OpenAI - no system prompt
        # 3. OpenAI API requires model + messages structure
        # 4. Within messages, user message contains the merged prompt with minimal format instructions
        # 5. NO other fields (symbol, timeframe, chart_type, take_profit, stop_loss) sent separately
        #
        # The merged prompt string (user_prompt) already contains ALL parameters:
        # - Strategy description
        # - Symbol
        # - Timeframe
        # - Chart Type
        # - Take Profit
        # - Stop Loss
        # - Trailing Stop
        # - Current Price
        # - Market Context
        # - Any future fields added from frontend
        
        # Build user message with merged prompt and unified schema format instruction
        # The merged prompt contains all user inputs, we need OpenAI to return the unified schema
        user_message = f"""Convert this trading strategy description into the following unified JSON schema:

{user_prompt}

Return JSON with this EXACT structure:
{{
  "symbol": "BTCUSD",
  "strategy_type": "ema_crossover",
  "logic": {{
    "emas": [10, 20, 50],
    "entry": {{
      "buy": {{
        "crossover": "ema_10_above_all",
        "confirmation": {{
          "type": "candle_high_break",
          "reference": "second_candle",
          "max_wait_candles": 3
        }}
      }},
      "sell": {{
        "crossover": "ema_10_below_all",
        "confirmation": {{
          "type": "candle_low_break",
          "reference": "second_candle",
          "max_wait_candles": 3
        }}
      }}
    }}
  }},
  "risk": {{
    "take_profit_points": 4000,
    "stop_loss_points": 4000
  }},
  "meta": {{
    "timeframe": "30MIN",
    "chart_type": "candles"
  }}
}}

CRITICAL RULES:
- Extract EMA periods from prompt (e.g. [10,20,50]) - do NOT use defaults
- Use ONLY POINTS for take_profit_points and stop_loss_points (not percentage)
- Extract timeframe and chart_type from prompt
- Do NOT add ema_fast or ema_slow fields
- Do NOT create condition + sell_condition - use unified entry.buy and entry.sell"""
        
        # Build OpenAI API payload
        # Send ONLY the merged prompt string in user message (with minimal format instruction)
        api_params = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "user", "content": user_message}  # Merged prompt + minimal format instruction
            ],
            "temperature": 0.8,
        }
        
        # Only add response_format for compatible models
        if "gpt-4" in OPENAI_MODEL or "gpt-3.5-turbo" in OPENAI_MODEL:
            api_params["response_format"] = {"type": "json_object"}
        
        # FINAL VALIDATION: Ensure no user-provided fields leak into API call
        # api_params contains ONLY:
        # - model (required by OpenAI API)
        # - messages (required by OpenAI API - contains ONLY user message with merged prompt)
        # - temperature (optional OpenAI parameter)
        # - response_format (optional OpenAI parameter)
        # 
        # CRITICAL: NO symbol, timeframe, chart_type, take_profit, stop_loss fields
        # All these are embedded in the merged prompt string (user_prompt)
        
        # Validate that api_params doesn't contain any user-provided fields
        forbidden_keys = ['symbol', 'timeframe', 'chart_type', 'take_profit', 'stop_loss', 'trailing_stop', 'prompt']
        for key in forbidden_keys:
            if key in api_params:
                raise ValueError(f"CRITICAL ERROR: User-provided field '{key}' found in OpenAI API params. This should never happen.")
        
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
        
        # Validate structure - check for new unified schema or old schema
        has_unified_schema = "logic" in strategy_data and "risk" in strategy_data and "meta" in strategy_data
        has_old_schema = "condition" in strategy_data
        
        if not has_unified_schema and not has_old_schema:
            logger.error("Invalid strategy structure from OpenAI - missing both unified and old schema")
            return None
        
        # Extract symbol from OpenAI response or prompt
        if "symbol" not in strategy_data or not strategy_data.get("symbol"):
            # Try to extract from prompt (look for "Symbol: XXX" pattern)
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
        
        # If OpenAI returned old schema, transform to unified schema
        if has_old_schema and not has_unified_schema:
            strategy_data = _transform_to_unified_schema(strategy_data, user_prompt)
        elif has_unified_schema:
            # Validate and clean unified schema
            strategy_data = _validate_unified_schema(strategy_data, user_prompt)
        
        logger.info(f"Successfully generated strategy with unified schema: {strategy_data}")
        return strategy_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI JSON response: {e}")
        logger.error(f"Response content (first 500 chars): {content[:500]}")
        logger.error(f"Full response length: {len(content)}")
        return None
    except Exception as e:
        logger.error(f"Error generating strategy with OpenAI: {e}", exc_info=True)
        # Log more details about the error
        if hasattr(e, 'response'):
            logger.error(f"OpenAI API error response: {e.response}")
        if hasattr(e, 'status_code'):
            logger.error(f"HTTP status code: {e.status_code}")
        # Log the actual exception type and message
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception message: {str(e)}")
        return None


def _transform_to_unified_schema(strategy_data: Dict[str, Any], user_prompt: str) -> Dict[str, Any]:
    """
    Transform old schema (condition.type, condition.parameters) to unified schema (logic, risk, meta).
    
    CRITICAL: Do NOT inject default EMA values. Use ONLY what's in the prompt.
    """
    unified = {
        "symbol": strategy_data.get("symbol", "BTCUSD").upper(),
        "strategy_type": None,
        "logic": {},
        "risk": {},
        "meta": {}
    }
    
    # Extract strategy type
    condition = strategy_data.get("condition", {})
    strategy_type = condition.get("type") or strategy_data.get("strategy_type")
    if strategy_type == "moving_average":
        strategy_type = "ema_crossover"
    unified["strategy_type"] = strategy_type or "ema_crossover"
    
    # Extract parameters
    params = condition.get("parameters", {}) or strategy_data.get("parameters", {})
    
    # Extract EMAs - CRITICAL: NO defaults, use ONLY what's in prompt
    emas = []
    if params.get("emas") and isinstance(params.get("emas"), list):
        emas = params["emas"]
    else:
        # Try to extract from various field names, but NO defaults
        if params.get("ema_fast"):
            emas.append(params["ema_fast"])
        if params.get("ema_slow"):
            emas.append(params["ema_slow"])
        if params.get("ema_medium"):
            emas.append(params["ema_medium"])
        # Extract from prompt if not in params
        if not emas:
            ema_matches = re.findall(r'EMA\s+(\d+)|(\d+)\s+EMA|ema[_\s]+(\d+)', user_prompt, re.IGNORECASE)
            for match in ema_matches:
                period = int(match[0] or match[1] or match[2])
                if period not in emas:
                    emas.append(period)
            emas.sort()
    
    # Get strategy type to determine if EMA validation is needed
    strategy_type = str(unified.get("strategy_type", "")).lower()
    # Check if it's an EMA-based strategy
    is_ema_strategy = (
        "ema" in strategy_type or 
        "moving_average" in strategy_type or 
        "crossover" in strategy_type or
        "moving average" in strategy_type
    )
    
    # Check if it's a non-EMA strategy (SuperTrend, RSI, etc.)
    is_non_ema_strategy = (
        "supertrend" in strategy_type or
        "super trend" in strategy_type or
        "rsi" in strategy_type or
        "macd" in strategy_type or
        "bollinger" in strategy_type
    )
    
    # CRITICAL: Only validate EMAs for EMA-based strategies (skip for SuperTrend and other non-EMA strategies)
    if is_ema_strategy and not is_non_ema_strategy and not emas:
        logger.error("❌ No EMA periods found in strategy - cannot generate unified schema")
        raise ValueError("No EMA periods found in strategy. For EMA-based strategies, please specify EMA periods explicitly (e.g., EMA 10, 20, 50).")
    
    # Build logic section
    # For non-EMA strategies (SuperTrend, etc.), preserve original logic structure from OpenAI
    if is_non_ema_strategy:
        # For SuperTrend and other non-EMA strategies, preserve the original logic from OpenAI
        # Don't force EMA structure - use what OpenAI generated
        if strategy_data.get("logic"):
            unified["logic"] = strategy_data["logic"].copy()
        else:
            # If no logic from OpenAI, create minimal structure
            unified["logic"] = {
                "entry": {
                    "buy": {},
                    "sell": {}
                }
            }
        # Ensure entry structure exists
        if "entry" not in unified["logic"]:
            unified["logic"]["entry"] = {"buy": {}, "sell": {}}
    else:
        # For EMA-based strategies, build EMA logic structure
        if not emas:
            # This should not happen due to validation above, but add safety check
            raise ValueError("Cannot build EMA logic without EMA periods")
        unified["logic"] = {
            "emas": emas,
            "entry": {
                "buy": {
                    "crossover": f"ema_{emas[0]}_above_all",
                    "confirmation": {
                        "type": "candle_high_break" if params.get("require_high_break") else "immediate",
                        "reference": "second_candle",
                        "max_wait_candles": params.get("break_condition", {}).get("wait_for_max_candles") or 4
                    }
                },
                "sell": {
                    "crossover": f"ema_{emas[0]}_below_all",
                    "confirmation": {
                        "type": "candle_low_break" if params.get("require_low_break") else "immediate",
                        "reference": "second_candle",
                        "max_wait_candles": params.get("break_condition", {}).get("wait_for_max_candles") or 4
                    }
                }
            }
        }
    
    # Build risk section - POINTS only (preferred), fallback to percent if needed
    risk = {}
    if params.get("tp_point") is not None:
        risk["take_profit_points"] = params["tp_point"]
    elif params.get("tp_percent") is not None:
        # Convert percent to points (approximate - would need current price)
        logger.warning("⚠️ TP provided as percentage, converting to points (approximate)")
        risk["take_profit_points"] = None  # Will need to be calculated with price
    
    if params.get("sl_point") is not None:
        risk["stop_loss_points"] = params["sl_point"]
    elif params.get("sl_percent") is not None:
        logger.warning("⚠️ SL provided as percentage, converting to points (approximate)")
        risk["stop_loss_points"] = None  # Will need to be calculated with price
    
    unified["risk"] = risk
    
    # Build meta section - extract from prompt
    meta = {}
    timeframe_match = re.search(r'Timeframe:\s*([A-Z0-9]+)', user_prompt, re.IGNORECASE)
    if timeframe_match:
        meta["timeframe"] = timeframe_match.group(1).upper()
    
    chart_type_match = re.search(r'Chart Type:\s*([A-Za-z\s]+)', user_prompt, re.IGNORECASE)
    if chart_type_match:
        chart_type_str = chart_type_match.group(1).strip().lower()
        meta["chart_type"] = "heikin_ashi" if "heikin" in chart_type_str else "candles"
    
    unified["meta"] = meta
    
    return unified


def _validate_unified_schema(strategy_data: Dict[str, Any], user_prompt: str) -> Dict[str, Any]:
    """
    Validate and clean unified schema - ensure it matches exact requirements.
    """
    # Ensure required sections exist
    if "logic" not in strategy_data:
        strategy_data["logic"] = {}
    if "risk" not in strategy_data:
        strategy_data["risk"] = {}
    if "meta" not in strategy_data:
        strategy_data["meta"] = {}
    
    # CRITICAL: Remove any ema_fast or ema_slow fields (forbidden)
    if "ema_fast" in strategy_data.get("logic", {}):
        del strategy_data["logic"]["ema_fast"]
        logger.warning("⚠️ Removed forbidden ema_fast field from logic")
    if "ema_slow" in strategy_data.get("logic", {}):
        del strategy_data["logic"]["ema_slow"]
        logger.warning("⚠️ Removed forbidden ema_slow field from logic")
    
    # Get strategy type to determine if EMA validation is needed
    strategy_type = str(strategy_data.get("strategy_type", "")).lower()
    # Check if it's an EMA-based strategy
    is_ema_strategy = (
        "ema" in strategy_type or 
        "moving_average" in strategy_type or 
        "crossover" in strategy_type or
        "moving average" in strategy_type
    )
    
    # Check if it's a non-EMA strategy (SuperTrend, RSI, etc.)
    is_non_ema_strategy = (
        "supertrend" in strategy_type or
        "super trend" in strategy_type or
        "rsi" in strategy_type or
        "macd" in strategy_type or
        "bollinger" in strategy_type
    )
    
    # Only validate EMAs for EMA-based strategies (skip for SuperTrend and other non-EMA strategies)
    if is_ema_strategy and not is_non_ema_strategy:
        # Ensure emas is an array
        if "emas" not in strategy_data.get("logic", {}):
            # Try to extract from prompt
            ema_matches = re.findall(r'EMA\s+(\d+)|(\d+)\s+EMA|ema[_\s]+(\d+)', user_prompt, re.IGNORECASE)
            emas = []
            for match in ema_matches:
                period = int(match[0] or match[1] or match[2])
                if period not in emas:
                    emas.append(period)
            emas.sort()
            if emas:
                strategy_data["logic"]["emas"] = emas
            else:
                raise ValueError("No EMA periods found in strategy or prompt. For EMA-based strategies, please specify EMA periods (e.g., EMA 10, 20, 50).")
    
    # Ensure entry structure exists
    if "entry" not in strategy_data.get("logic", {}):
        strategy_data["logic"]["entry"] = {"buy": {}, "sell": {}}
    
    # Ensure timeframe and chart_type are in meta, not logic
    if "timeframe" in strategy_data.get("logic", {}):
        if "timeframe" not in strategy_data["meta"]:
            strategy_data["meta"]["timeframe"] = strategy_data["logic"]["timeframe"]
        del strategy_data["logic"]["timeframe"]
    if "chart_type" in strategy_data.get("logic", {}):
        if "chart_type" not in strategy_data["meta"]:
            strategy_data["meta"]["chart_type"] = strategy_data["logic"]["chart_type"]
        del strategy_data["logic"]["chart_type"]
    
    # Remove any old schema fields if present
    for field in ["condition", "parameters", "sell_condition"]:
        if field in strategy_data:
            del strategy_data[field]
            logger.warning(f"⚠️ Removed old schema field '{field}' from strategy")
    
    return strategy_data


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

