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
        # CRITICAL: OpenAI API call - send ONLY the merged prompt string
        # 
        # MANDATORY RULES:
        # 1. user_prompt contains ALL frontend fields merged into ONE human-readable string
        #    (This is done by build_prompt() in routes_ai_strategy.py)
        # 2. Send ONLY the merged prompt string to OpenAI - no system prompt, no extra instructions
        # 3. OpenAI API requires model + messages structure
        # 4. Within messages, user message contains ONLY the merged prompt string
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
        
        # Build OpenAI API payload
        # Send ONLY the merged prompt string in user message
        # No system prompt, no extra instructions - just the merged prompt
        api_params = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "user", "content": user_prompt}  # ONLY the merged prompt string
            ],
            "temperature": 0.8,
        }
        
        # Only add response_format for compatible models
        if "gpt-4" in OPENAI_MODEL or "gpt-3.5-turbo" in OPENAI_MODEL:
            api_params["response_format"] = {"type": "json_object"}
        
        # FINAL VALIDATION: Ensure no user-provided fields leak into API call
        # api_params contains ONLY:
        # - model (required by OpenAI API)
        # - messages (required by OpenAI API - contains system prompt + user message with merged prompt)
        # - temperature (optional OpenAI parameter)
        # - response_format (optional OpenAI parameter)
        # 
        # CRITICAL: NO symbol, timeframe, chart_type, take_profit, stop_loss fields
        # All these are embedded in the merged prompt string within user_message
        
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
        
        # CRITICAL: Remove condition.value completely - condition must contain ONLY type and parameters
        if "value" in condition:
            del condition["value"]
            logger.info("Removed condition.value - condition now contains only type and parameters")
        
        # Normalize parameters structure - single source of truth
        # Use condition.parameters as the source, ensure root-level parameters references the same object
        if condition.get("type") in ["supertrend", "ema_crossover", "moving_average", "rsi", "macd", "bollinger_bands"]:
            # Get parameters from condition (preferred) or root level
            if "parameters" in condition:
                params = condition.get("parameters", {})
            elif "parameters" in strategy_data:
                params = strategy_data.get("parameters", {})
            else:
                params = {}
            
            # Normalize EMA parameter naming - avoid ema_slow_2, use consistent naming
            if condition.get("type") == "ema_crossover":
                # Normalize EMA parameter names
                normalized_params = {}
                
                # Handle various EMA naming patterns
                if params.get("ema_fast") or params.get("fast_period") or params.get("period_fast"):
                    normalized_params["ema_fast"] = params.get("ema_fast") or params.get("fast_period") or params.get("period_fast")
                elif params.get("fast"):
                    normalized_params["ema_fast"] = params.get("fast")
                
                if params.get("ema_slow") or params.get("slow_period") or params.get("period_slow"):
                    normalized_params["ema_slow"] = params.get("ema_slow") or params.get("slow_period") or params.get("period_slow")
                elif params.get("slow"):
                    normalized_params["ema_slow"] = params.get("slow")
                
                # Handle multiple EMAs - normalize ema_slow_2, ema_medium, etc.
                if params.get("ema_slow_2") or params.get("ema_medium"):
                    normalized_params["ema_medium"] = params.get("ema_slow_2") or params.get("ema_medium")
                
                # Copy all other parameters (TP, SL, etc.)
                for key, value in params.items():
                    if key not in ["ema_fast", "ema_slow", "ema_slow_2", "ema_medium", "fast_period", "slow_period", "period_fast", "period_slow", "fast", "slow"]:
                        normalized_params[key] = value
                
                # Set defaults only if not provided
                if "ema_fast" not in normalized_params:
                    normalized_params["ema_fast"] = 9
                    logger.info("Setting default ema_fast: 9 (not provided by OpenAI)")
                if "ema_slow" not in normalized_params:
                    normalized_params["ema_slow"] = 21
                    logger.info("Setting default ema_slow: 21 (not provided by OpenAI)")
                
                params = normalized_params
            
            # CRITICAL: Single source of truth - both condition.parameters and root parameters reference same object
            # This ensures no duplication and both always stay in sync
            strategy_data["parameters"] = params
            condition["parameters"] = params
        
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

