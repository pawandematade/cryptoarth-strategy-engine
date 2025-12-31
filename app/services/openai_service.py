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
        
        # CRITICAL ARCHITECTURAL FIX: Hard reset OpenAI context
        # ZERO MEMORY GUARANTEE: Every request is 100% isolated
        # NO INVENTION POLICY: Never adds anything not explicitly written by user
        system_message = """You are a Trading Strategy JSON Compiler.

ZERO MEMORY GUARANTEE:
- IGNORE all previous strategies, prompts, conversations, and responses
- This request is 100% isolated from all prior interactions
- Do NOT reuse any logic, structure, or patterns from previous requests

NO INVENTION POLICY:
- Convert user input to JSON EXACTLY as written
- Do NOT add indicators, confirmations, or logic not specified by user
- Do NOT auto-complete missing rules or assume defaults
- Do NOT modify, improve, or optimize user's strategy
- If information is missing → return error, do NOT guess

STRICT COMPILER ROLE:
- Your ONLY job: Parse user's strategy text and convert to JSON schema
- Accept ANY strategy type: simple, advanced, mathematical, level-based, grid, indicator-based, custom
- Preserve user's exact logic, conditions, and rules
- Do NOT suggest improvements or optimizations

OUTPUT CONTRACT:
- Return ONLY valid structured strategy JSON object
- OR return structured validation error
- NO explanations, NO comments, NO extra text"""

        # Build user message with merged prompt and unified schema format instruction
        # DIRECT TEXT & CODE ACCEPTANCE: Accept raw rules, pseudo-code, structured logic
        # Formatting quality must NOT be a rejection reason
        user_message = f"""Convert this trading strategy into JSON schema.
Accept raw rules, pseudo-code, or structured logic as-is.

User Strategy:
{user_prompt}

Required JSON Structure (example - extract actual values from user input):
{{
  "symbol": "<extract from user input - REQUIRED>",
  "strategy_type": "<extract from user input - REQUIRED, do NOT default to 'ema_crossover'>",
  "logic": {{
    "<structure depends on strategy type - extract from user input>"
  }},
  "risk": {{
    "take_profit_points": <extract from user input - REQUIRED>,
    "stop_loss_points": <extract from user input - REQUIRED>
  }},
  "meta": {{
    "timeframe": "<extract from user input>",
    "chart_type": "<extract from user input>"
  }}
}}

CRITICAL COMPILATION RULES (NO INVENTION POLICY):
- Extract strategy_type from user input - if missing, return error (do NOT default to "ema_crossover")
- Extract crossover values from user input - do NOT auto-generate "ema_X_above_all" or "ema_X_below_all"
- Include confirmation block ONLY if user explicitly wrote it - do NOT add "candle_high_break", "candle_low_break", or "immediate"
- Include entry.buy and entry.sell ONLY if user specified them - do NOT auto-create
- Extract EMA periods from user input - do NOT use defaults or assumptions
- If required fields (symbol, strategy_type, logic, risk) are missing → return error, do NOT guess
- Preserve user's exact logic, conditions, and rules - do NOT modify or optimize"""
        
        # Build OpenAI API payload
        # CRITICAL: Include system message to reset context and define compiler role
        api_params = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_message},  # Hard reset context + compiler role
                {"role": "user", "content": user_message}  # Merged prompt + format instruction
            ],
            "temperature": 0.7,  # Reduced from 0.8 for more deterministic output
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
            # KEEP ONLY SAFE JSON EXTRACTION (old schema is illegal)
            import re
            json_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_block:
                strategy_data = json.loads(json_block.group(1))
            else:
                raise ValueError("OUTPUT_ERROR: OpenAI response is not valid JSON.")
        
        # Validate structure - check for new unified schema or old schema
        has_unified_schema = "logic" in strategy_data and "risk" in strategy_data and "meta" in strategy_data
        has_old_schema = "condition" in strategy_data
        
        if not has_unified_schema and not has_old_schema:
            logger.error("Invalid strategy structure from OpenAI - missing both unified and old schema")
            return None
        
        # Extract symbol from OpenAI response (STRICT NO-INVENTION)
        # Backend must never infer anything, even via regex
        if "symbol" not in strategy_data or not strategy_data.get("symbol"):
            raise ValueError(
                "OUTPUT_ERROR: Strategy missing required 'symbol'. "
                "AI must explicitly return symbol in unified schema."
            )
        else:
            # Ensure symbol is uppercase
            strategy_data["symbol"] = str(strategy_data["symbol"]).upper()
        
        # CRITICAL: Reject old schema - should not exist (OpenAI should return unified schema)
        if has_old_schema:
            logger.error("❌ OpenAI returned old schema - this should not happen")
            raise ValueError("OUTPUT_ERROR: OpenAI returned deprecated schema format. Please try again.")
        
        # Validate unified schema (NO INVENTION - reject if missing required fields)
        if has_unified_schema:
            strategy_data = _validate_unified_schema(strategy_data, user_prompt)
        else:
            logger.error("❌ OpenAI response missing unified schema structure")
            raise ValueError("OUTPUT_ERROR: Strategy is missing required unified schema structure (logic, risk, meta).")
        
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


# REMOVED: _transform_to_unified_schema function
# Old schema transformation is no longer supported.
# OpenAI must return unified schema directly.
# If old schema appears, it is rejected with error.
    


def _validate_unified_schema(strategy_data: Dict[str, Any], user_prompt: str) -> Dict[str, Any]:
    """
    Validate unified schema - NO INVENTION POLICY.
    Reject if required fields are missing (do NOT create defaults).
    """
    # NO INVENTION: Reject if required sections are missing
    if "logic" not in strategy_data:
        raise ValueError("OUTPUT_ERROR: Strategy is missing required 'logic' section.")
    if "risk" not in strategy_data:
        raise ValueError("OUTPUT_ERROR: Strategy is missing required 'risk' section.")
    if "meta" not in strategy_data:
        raise ValueError("OUTPUT_ERROR: Strategy is missing required 'meta' section.")
    
    # NO INVENTION: Reject if strategy_type is missing
    if not strategy_data.get("strategy_type"):
        raise ValueError("OUTPUT_ERROR: Strategy is missing required 'strategy_type' field. Do NOT default to 'ema_crossover'.")
    
    # CRITICAL: Reject forbidden fields (STRICT REJECTION, NO AUTO-CLEANUP)
    if "ema_fast" in strategy_data.get("logic", {}):
        raise ValueError(
            "OUTPUT_ERROR: Forbidden field 'ema_fast' detected. "
            "Strategy must follow unified schema strictly."
        )
    if "ema_slow" in strategy_data.get("logic", {}):
        raise ValueError(
            "OUTPUT_ERROR: Forbidden field 'ema_slow' detected. "
            "Strategy must follow unified schema strictly."
        )
    
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
    
    # NO INVENTION: For EMA-based strategies, reject if EMAs are missing
    # Do NOT extract from prompt or create defaults
    if is_ema_strategy and not is_non_ema_strategy:
        if "emas" not in strategy_data.get("logic", {}):
            raise ValueError("OUTPUT_ERROR: EMA-based strategy is missing 'emas' array in logic section. Do NOT auto-generate EMA periods.")
        
        emas = strategy_data["logic"]["emas"]
        if not isinstance(emas, list) or len(emas) < 2:
            raise ValueError("OUTPUT_ERROR: EMA-based strategy must have at least 2 EMA periods in logic.emas array.")
    
    # NO INVENTION: Reject if entry structure is missing (do NOT create)
    if "entry" not in strategy_data.get("logic", {}):
        raise ValueError("OUTPUT_ERROR: Strategy is missing 'entry' section in logic. Do NOT auto-create entry structure.")
    
    entry = strategy_data["logic"]["entry"]
    if "buy" not in entry or "sell" not in entry:
        raise ValueError("OUTPUT_ERROR: Strategy entry must contain both 'buy' and 'sell' sections. Do NOT auto-create.")
    
    # Move timeframe and chart_type from logic to meta (if present in wrong location)
    # This is schema cleanup, not invention
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

