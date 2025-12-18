"""
Secure Strategy Generation Service
- Controlled OpenAI prompts
- Schema validation
- No executable code
- Production-safe
"""
import json
import logging
import re
import uuid
from typing import Dict, Optional, List, Any
from datetime import datetime
from openai import OpenAI
from app.config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = None

def initialize_client():
    """Initialize OpenAI client"""
    global client
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
        logger.warning("OPENAI_API_KEY not set")
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

# Allowed indicators (whitelist approach)
ALLOWED_INDICATORS = {
    'ema', 'sma', 'wma', 'rma',  # Moving averages
    'rsi', 'stoch', 'stochastic',  # Oscillators
    'macd', 'signal', 'histogram',  # MACD
    'bollinger', 'bb', 'upper_band', 'lower_band', 'middle_band',  # Bollinger Bands
    'supertrend', 'atr',  # Trend indicators
    'adx', 'dmi', 'plus_di', 'minus_di',  # Directional Movement
    'obv', 'volume', 'volume_sma',  # Volume indicators
    'vwap', 'pivot', 'support', 'resistance',  # Price levels
    'fibonacci', 'fib',  # Fibonacci
    'ichimoku', 'tenkan', 'kijun', 'senkou',  # Ichimoku
    'williams', 'wr',  # Williams %R
    'cci', 'commodity_channel',  # CCI
    'mfi', 'money_flow',  # Money Flow Index
    'roc', 'rate_of_change',  # Rate of Change
    'momentum', 'mom',  # Momentum
}

# Allowed operators
ALLOWED_OPERATORS = {
    'above', 'below', 'cross', 'crossover', 'cross_above', 'cross_below',
    'greater_than', 'less_than', 'equal', 'not_equal',
    'and', 'or', 'not',
    'between', 'outside',
    'divergence', 'convergence',
    'increasing', 'decreasing', 'rising', 'falling'
}

# Allowed timeframes
ALLOWED_TIMEFRAMES = {
    '1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'
}

# Allowed strategy types
ALLOWED_STRATEGY_TYPES = {
    'indicator_based', 'grid_based', 'condition_based', 'formula_based', 'hybrid'
}

def get_system_prompt(market_context: Optional[str] = None) -> str:
    """Get the controlled system prompt for OpenAI with enhanced intelligence"""
    base_prompt = """You are the world's most advanced AI trading strategy builder for cryptocurrency markets. You have deep expertise in:
- Technical analysis and indicator interpretation
- Risk management and position sizing
- Market microstructure and trading psychology
- Strategy optimization and backtesting principles
- Multi-timeframe analysis
- Market regime detection (trending, ranging, volatile)

Your task is to convert natural language trading strategy descriptions into a SAFE, STRUCTURED, OPTIMIZED JSON format that represents a production-ready trading strategy.

CRITICAL INTELLIGENCE RULES:
1. NEVER generate executable code - only declarative logic
2. NEVER allow arbitrary expressions or formulas
3. ONLY use whitelisted indicators, operators, and values
4. ALL numeric values must be positive numbers
5. ALL logic must be declarative (what to do, not how to do it)
6. Apply best practices: proper risk-reward ratios, timeframe alignment, market regime awareness
7. Infer missing parameters intelligently based on strategy type and market context
8. Optimize default values for cryptocurrency volatility (crypto is more volatile than traditional markets)
"""
    
    if market_context:
        base_prompt += f"\n\nCURRENT MARKET CONTEXT:\n{market_context}\n\nUse this context to optimize the strategy parameters."
    
    return base_prompt + """

CRITICAL RULES:
1. NEVER generate executable code
2. NEVER allow arbitrary expressions or formulas
3. ONLY use whitelisted indicators, operators, and values
4. ALL numeric values must be positive numbers
5. ALL logic must be declarative (what to do, not how to do it)

OUTPUT SCHEMA (MUST FOLLOW EXACTLY):
{
  "strategy_id": "unique-uuid-string",
  "symbol": "BTCUSD",
  "timeframe": "1h",
  "type": "indicator_based" | "grid_based" | "condition_based" | "formula_based" | "hybrid",
  "logic": {
    "entry": {
      "conditions": [
        {
          "indicator": "ema",
          "operator": "cross_above",
          "value": 21,
          "comparison": "ema_9"
        }
      ],
      "logic_operator": "and" | "or"
    },
    "exit": {
      "conditions": [
        {
          "indicator": "price",
          "operator": "above",
          "value": 90000
        }
      ],
      "logic_operator": "and" | "or"
    }
  },
  "risk": {
    "stop_loss": {
      "type": "percentage" | "absolute" | "atr_multiple",
      "value": 1.0
    },
    "take_profit": {
      "type": "percentage" | "absolute" | "atr_multiple",
      "value": 2.0
    },
    "position_size": {
      "type": "fixed" | "percentage" | "risk_based",
      "value": 1.0
    }
  },
  "meta": {
    "confidence": 0.85,
    "explanation": "Brief explanation of the strategy",
    "complexity": "simple" | "medium" | "complex"
  }
}

ALLOWED INDICATORS (ONLY THESE):
""" + ", ".join(sorted(ALLOWED_INDICATORS)) + """

ALLOWED OPERATORS (ONLY THESE):
""" + ", ".join(sorted(ALLOWED_OPERATORS)) + """

ALLOWED TIMEFRAMES (ONLY THESE):
""" + ", ".join(sorted(ALLOWED_TIMEFRAMES)) + """

EXAMPLES:

Input: "EMA 9 cross above 21 EMA buy and EMA 9 cross below 21 EMA sell, TP 2% SL 1%"
Output:
{
  "strategy_id": "uuid-here",
  "symbol": "BTCUSD",
  "timeframe": "1h",
  "type": "indicator_based",
  "logic": {
    "entry": {
      "conditions": [{
        "indicator": "ema",
        "operator": "cross_above",
        "value": 21,
        "comparison": "ema_9"
      }],
      "logic_operator": "and"
    },
    "exit": {
      "conditions": [{
        "indicator": "ema",
        "operator": "cross_below",
        "value": 9,
        "comparison": "ema_21"
      }],
      "logic_operator": "and"
    }
  },
  "risk": {
    "stop_loss": {"type": "percentage", "value": 1.0},
    "take_profit": {"type": "percentage", "value": 2.0},
    "position_size": {"type": "percentage", "value": 1.0}
  },
  "meta": {
    "confidence": 0.8,
    "explanation": "EMA crossover strategy with 9 and 21 period EMAs",
    "complexity": "simple"
  }
}

Input: "Buy when price goes above 90000, sell when price drops below 88000"
Output:
{
  "strategy_id": "uuid-here",
  "symbol": "BTCUSD",
  "timeframe": "1h",
  "type": "condition_based",
  "logic": {
    "entry": {
      "conditions": [{
        "indicator": "price",
        "operator": "above",
        "value": 90000
      }],
      "logic_operator": "and"
    },
    "exit": {
      "conditions": [{
        "indicator": "price",
        "operator": "below",
        "value": 88000
      }],
      "logic_operator": "and"
    }
  },
  "risk": {
    "stop_loss": {"type": "percentage", "value": 2.0},
    "take_profit": {"type": "percentage", "value": 3.0},
    "position_size": {"type": "percentage", "value": 1.0}
  },
  "meta": {
    "confidence": 0.75,
    "explanation": "Price-based entry and exit strategy",
    "complexity": "simple"
  }
}

IMPORTANT:
- Return ONLY valid JSON
- No additional text or explanation
- All values must be numeric (no strings for numbers)
- If timeframe is not specified, default to "1h"
- If risk parameters are not specified, use safe defaults (SL: 2%, TP: 3%)
- Confidence score should be between 0.0 and 1.0
- Generate a unique strategy_id as UUID string
"""
    
    return base_prompt

def validate_strategy_schema(strategy: Dict[str, Any]) -> tuple:
    """
    Validate strategy against schema and security rules
    
    Returns:
        (is_valid, error_message)
    """
    try:
        # Required fields
        required_fields = ['strategy_id', 'symbol', 'timeframe', 'type', 'logic', 'risk', 'meta']
        for field in required_fields:
            if field not in strategy:
                return False, f"Missing required field: {field}"
        
        # Validate strategy_id
        if not isinstance(strategy['strategy_id'], str) or len(strategy['strategy_id']) < 10:
            return False, "Invalid strategy_id (must be string UUID)"
        
        # Validate symbol
        if not isinstance(strategy['symbol'], str) or not strategy['symbol']:
            return False, "Invalid symbol"
        
        # Validate timeframe
        if strategy['timeframe'] not in ALLOWED_TIMEFRAMES:
            return False, f"Invalid timeframe: {strategy['timeframe']}"
        
        # Validate type
        if strategy['type'] not in ALLOWED_STRATEGY_TYPES:
            return False, f"Invalid strategy type: {strategy['type']}"
        
        # Validate logic structure
        if not isinstance(strategy['logic'], dict):
            return False, "Logic must be a dictionary"
        
        if 'entry' not in strategy['logic'] or 'exit' not in strategy['logic']:
            return False, "Logic must have 'entry' and 'exit'"
        
        # Validate entry conditions
        entry = strategy['logic']['entry']
        if 'conditions' not in entry or not isinstance(entry['conditions'], list):
            return False, "Entry must have 'conditions' array"
        
        for condition in entry['conditions']:
            if not isinstance(condition, dict):
                return False, "Each condition must be a dictionary"
            if 'indicator' not in condition:
                return False, "Condition must have 'indicator'"
            
            indicator = condition['indicator'].lower()
            if indicator not in ALLOWED_INDICATORS and indicator != 'price':
                return False, f"Invalid indicator: {indicator}"
            
            if 'operator' not in condition:
                return False, "Condition must have 'operator'"
            
            operator = condition['operator'].lower()
            if operator not in ALLOWED_OPERATORS:
                return False, f"Invalid operator: {operator}"
            
            if 'value' in condition:
                value = condition['value']
                if not isinstance(value, (int, float)) or value < 0:
                    return False, f"Invalid value: {value} (must be positive number)"
        
        # Validate exit conditions (same as entry)
        exit_conditions = strategy['logic']['exit']
        if 'conditions' not in exit_conditions or not isinstance(exit_conditions['conditions'], list):
            return False, "Exit must have 'conditions' array"
        
        for condition in exit_conditions['conditions']:
            if not isinstance(condition, dict):
                return False, "Each condition must be a dictionary"
            if 'indicator' not in condition:
                return False, "Condition must have 'indicator'"
            
            indicator = condition['indicator'].lower()
            if indicator not in ALLOWED_INDICATORS and indicator != 'price':
                return False, f"Invalid indicator: {indicator}"
        
        # Validate risk structure
        risk = strategy['risk']
        required_risk_fields = ['stop_loss', 'take_profit', 'position_size']
        for field in required_risk_fields:
            if field not in risk:
                return False, f"Missing risk field: {field}"
            
            risk_item = risk[field]
            if not isinstance(risk_item, dict):
                return False, f"{field} must be a dictionary"
            
            if 'type' not in risk_item or 'value' not in risk_item:
                return False, f"{field} must have 'type' and 'value'"
            
            if not isinstance(risk_item['value'], (int, float)) or risk_item['value'] < 0:
                return False, f"Invalid {field} value (must be positive number)"
        
        # Validate meta
        meta = strategy['meta']
        if 'confidence' not in meta:
            return False, "Meta must have 'confidence'"
        
        confidence = meta['confidence']
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            return False, "Confidence must be between 0.0 and 1.0"
        
        return True, None
        
    except Exception as e:
        logger.error(f"Validation error: {e}", exc_info=True)
        return False, f"Validation error: {str(e)}"

def extract_json_from_response(text: str) -> Optional[Dict]:
    """Extract JSON from OpenAI response"""
    try:
        # Try direct JSON parse
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON object in text
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        return None

def calculate_strategy_quality(strategy: Dict[str, Any]) -> float:
    """
    Calculate a quality score (0-1) for the strategy based on multiple factors
    
    Returns:
        Quality score between 0.0 and 1.0
    """
    score = 0.0
    max_score = 0.0
    
    # Risk-reward ratio (0-0.25)
    risk = strategy.get('risk', {})
    sl = risk.get('stop_loss', {}).get('value', 0)
    tp = risk.get('take_profit', {}).get('value', 0)
    if sl > 0 and tp > 0:
        risk_reward = tp / sl
        if 1.5 <= risk_reward <= 3.0:
            score += 0.25  # Optimal range
        elif 1.0 <= risk_reward < 1.5:
            score += 0.15  # Acceptable
        elif 3.0 < risk_reward <= 5.0:
            score += 0.20  # Good but may be optimistic
        else:
            score += 0.05  # Needs improvement
    max_score += 0.25
    
    # Strategy completeness (0-0.25)
    logic = strategy.get('logic', {})
    entry_conditions = len(logic.get('entry', {}).get('conditions', []))
    exit_conditions = len(logic.get('exit', {}).get('conditions', []))
    if entry_conditions > 0 and exit_conditions > 0:
        if 1 <= entry_conditions <= 3 and 1 <= exit_conditions <= 3:
            score += 0.25  # Optimal complexity
        elif entry_conditions > 3 or exit_conditions > 3:
            score += 0.15  # May be over-complicated
        else:
            score += 0.10  # Too simple
    max_score += 0.25
    
    # Indicator usage (0-0.20)
    conditions = logic.get('entry', {}).get('conditions', []) + logic.get('exit', {}).get('conditions', [])
    indicators_used = set(cond.get('indicator', '').lower() for cond in conditions)
    has_trend_filter = any(ind in ['supertrend', 'adx', 'dmi', 'ichimoku'] for ind in indicators_used)
    has_momentum = any(ind in ['rsi', 'stoch', 'williams', 'cci'] for ind in indicators_used)
    has_volume = any('volume' in ind or 'obv' in ind for ind in indicators_used)
    
    if has_trend_filter:
        score += 0.10
    if has_momentum:
        score += 0.05
    if has_volume:
        score += 0.05
    max_score += 0.20
    
    # Risk management (0-0.15)
    if sl > 0 and 0.5 <= sl <= 5.0:  # Reasonable SL for crypto
        score += 0.10
    if tp > 0:
        score += 0.05
    max_score += 0.15
    
    # Confidence from meta (0-0.15)
    meta = strategy.get('meta', {})
    confidence = meta.get('confidence', 0.5)
    score += confidence * 0.15
    max_score += 0.15
    
    # Normalize score
    if max_score > 0:
        final_score = min(1.0, score / max_score)
    else:
        final_score = 0.5
    
    return round(final_score, 2)

def calculate_strategy_quality(strategy: Dict[str, Any]) -> float:
    """
    Calculate a quality score (0-1) for the strategy based on multiple factors
    
    Returns:
        Quality score between 0.0 and 1.0
    """
    score = 0.0
    max_score = 0.0
    
    # Risk-reward ratio (0-0.25)
    risk = strategy.get('risk', {})
    sl = risk.get('stop_loss', {}).get('value', 0)
    tp = risk.get('take_profit', {}).get('value', 0)
    if sl > 0 and tp > 0:
        risk_reward = tp / sl
        if 1.5 <= risk_reward <= 3.0:
            score += 0.25  # Optimal range
        elif 1.0 <= risk_reward < 1.5:
            score += 0.15  # Acceptable
        elif 3.0 < risk_reward <= 5.0:
            score += 0.20  # Good but may be optimistic
        else:
            score += 0.05  # Needs improvement
    max_score += 0.25
    
    # Strategy completeness (0-0.25)
    logic = strategy.get('logic', {})
    entry_conditions = len(logic.get('entry', {}).get('conditions', []))
    exit_conditions = len(logic.get('exit', {}).get('conditions', []))
    if entry_conditions > 0 and exit_conditions > 0:
        if 1 <= entry_conditions <= 3 and 1 <= exit_conditions <= 3:
            score += 0.25  # Optimal complexity
        elif entry_conditions > 3 or exit_conditions > 3:
            score += 0.15  # May be over-complicated
        else:
            score += 0.10  # Too simple
    max_score += 0.25
    
    # Indicator usage (0-0.20)
    conditions = logic.get('entry', {}).get('conditions', []) + logic.get('exit', {}).get('conditions', [])
    indicators_used = set(cond.get('indicator', '').lower() for cond in conditions)
    has_trend_filter = any(ind in ['supertrend', 'adx', 'dmi', 'ichimoku'] for ind in indicators_used)
    has_momentum = any(ind in ['rsi', 'stoch', 'williams', 'cci'] for ind in indicators_used)
    has_volume = any('volume' in ind or 'obv' in ind for ind in indicators_used)
    
    if has_trend_filter:
        score += 0.10
    if has_momentum:
        score += 0.05
    if has_volume:
        score += 0.05
    max_score += 0.20
    
    # Risk management (0-0.15)
    if sl > 0 and 0.5 <= sl <= 5.0:  # Reasonable SL for crypto
        score += 0.10
    if tp > 0:
        score += 0.05
    max_score += 0.15
    
    # Confidence from meta (0-0.15)
    meta = strategy.get('meta', {})
    confidence = meta.get('confidence', 0.5)
    score += confidence * 0.15
    max_score += 0.15
    
    # Normalize score
    if max_score > 0:
        final_score = min(1.0, score / max_score)
    else:
        final_score = 0.5
    
    return round(final_score, 2)

def generate_strategy_suggestions(strategy: Dict[str, Any]) -> List[str]:
    """Generate intelligent improvement suggestions based on strategy analysis"""
    suggestions = []
    
    # Check risk-reward ratio
    risk = strategy.get('risk', {})
    sl = risk.get('stop_loss', {}).get('value', 0)
    tp = risk.get('take_profit', {}).get('value', 0)
    
    if sl > 0 and tp > 0:
        risk_reward = tp / sl
        if risk_reward < 1.5:
            suggestions.append("⚠️ Improve risk-reward ratio (aim for at least 1.5:1 for crypto markets)")
        elif risk_reward < 2.0:
            suggestions.append("💡 Consider increasing take-profit to 2:1 or higher for better risk-adjusted returns")
        elif risk_reward > 5:
            suggestions.append("⚠️ Risk-reward ratio is very high - ensure realistic profit targets based on market volatility")
    
    # Check stop loss appropriateness for crypto
    if sl > 0:
        if sl < 0.5:
            suggestions.append("⚠️ Stop loss is very tight (<0.5%) - crypto volatility may cause premature exits")
        elif sl > 5:
            suggestions.append("⚠️ Stop loss is wide (>5%) - consider tighter risk management for crypto")
    
    # Check for timeframe filter
    logic = strategy.get('logic', {})
    conditions = logic.get('entry', {}).get('conditions', [])
    has_timeframe_filter = any('timeframe' in str(c).lower() for c in conditions)
    if not has_timeframe_filter:
        suggestions.append("💡 Add higher timeframe trend filter to avoid false signals in ranging markets")
    
    # Check complexity and overtrading risk
    meta = strategy.get('meta', {})
    complexity = meta.get('complexity', 'medium')
    entry_conditions = len(logic.get('entry', {}).get('conditions', []))
    exit_conditions = len(logic.get('exit', {}).get('conditions', []))
    
    if entry_conditions > 4:
        suggestions.append("⚠️ Too many entry conditions may reduce trade frequency - consider simplifying")
    elif entry_conditions == 1 and complexity == 'simple':
        suggestions.append("💡 Consider adding a confirmation filter to improve signal quality")
    
    # Check for sideways market protection
    indicators_used = [cond.get('indicator', '').lower() for cond in conditions]
    has_trend_filter = any(ind in ['supertrend', 'adx', 'dmi', 'ichimoku'] for ind in indicators_used)
    if not has_trend_filter:
        suggestions.append("💡 Add trend indicator (SuperTrend, ADX, or Ichimoku) to avoid trading in sideways markets")
    
    # Check for volume confirmation
    has_volume_filter = any('volume' in ind or 'obv' in ind for ind in indicators_used)
    if not has_volume_filter:
        suggestions.append("💡 Consider adding volume confirmation to validate price movements")
    
    # Check timeframe appropriateness
    timeframe = strategy.get('timeframe', '1h')
    if timeframe in ['1m', '3m', '5m']:
        suggestions.append("⚠️ Very short timeframes may have high noise - consider 15m or higher for better signal quality")
    
    # Check strategy type specific suggestions
    strategy_type = strategy.get('type', '')
    if strategy_type == 'grid_based':
        suggestions.append("💡 Grid strategies work best in ranging markets - add trend filter to disable in strong trends")
    elif strategy_type == 'indicator_based':
        if not any(ind in ['rsi', 'stoch', 'williams'] for ind in indicators_used):
            suggestions.append("💡 Consider adding momentum oscillator (RSI, Stochastic) for better entry timing")
    
    # Check position sizing
    position_size = risk.get('position_size', {}).get('value', 1.0)
    if position_size > 5:
        suggestions.append("⚠️ Position size is high (>5%) - consider risk-based position sizing for better capital preservation")
    
    # Default suggestions if none generated
    if not suggestions:
        suggestions.append("✅ Strategy structure looks solid! Consider backtesting on historical data")
        suggestions.append("💡 Monitor performance metrics and adjust parameters based on market regime changes")
        suggestions.append("💡 Consider paper trading first to validate strategy behavior in live market conditions")
    
    # Prioritize and return top 3-4 most important suggestions
    priority_suggestions = []
    warning_suggestions = [s for s in suggestions if s.startswith('⚠️')]
    tip_suggestions = [s for s in suggestions if s.startswith('💡')]
    success_suggestions = [s for s in suggestions if s.startswith('✅')]
    
    # Prioritize warnings, then tips, then success messages
    priority_suggestions.extend(warning_suggestions[:2])
    priority_suggestions.extend(tip_suggestions[:2])
    if len(priority_suggestions) < 3:
        priority_suggestions.extend(success_suggestions[:1])
    
    return priority_suggestions[:4]  # Return max 4 suggestions

def generate_secure_strategy(description: str, symbol: str = "BTCUSD", market_context: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate a secure, structured strategy from natural language
    
    Args:
        description: User's natural language strategy description
        symbol: Trading symbol
    
    Returns:
        Dict with strategy, suggestions, and metadata
    """
    if not client:
        if not initialize_client():
            raise ValueError("OpenAI client not initialized. Check API key.")
    
    try:
        system_prompt = get_system_prompt(market_context=market_context)
        user_message = f"""Convert this trading strategy description into the structured JSON format with intelligent optimizations:

SYMBOL: {symbol}
DESCRIPTION: {description}

INSTRUCTIONS:
1. Analyze the strategy description carefully
2. Extract all mentioned indicators, parameters, and conditions
3. Infer optimal defaults for missing parameters (consider crypto market volatility)
4. Apply best practices for risk management
5. Set appropriate timeframe if not specified (default to 1h for crypto)
6. Calculate confidence score based on strategy clarity and completeness
7. Generate a comprehensive explanation of the strategy logic

Return ONLY the JSON object following the exact schema. No additional text."""

        api_params = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.2,  # Lower temperature for more consistent, structured output
            "max_tokens": 2500,  # Increased for more detailed strategies
            "top_p": 0.95,
            "frequency_penalty": 0.1,  # Encourage diverse but relevant responses
        }

        if "gpt-4" in OPENAI_MODEL or "gpt-3.5-turbo" in OPENAI_MODEL:
            api_params["response_format"] = {"type": "json_object"}

        logger.info(f"Calling OpenAI API for strategy generation: {symbol}")
        response = client.chat.completions.create(**api_params)
        content = response.choices[0].message.content
        logger.info(f"OpenAI raw response: {content[:200]}...")

        # Extract JSON
        strategy = extract_json_from_response(content)
        
        if not strategy:
            raise ValueError("Failed to extract JSON from OpenAI response")

        # Generate strategy_id if missing
        if 'strategy_id' not in strategy or not strategy['strategy_id']:
            strategy['strategy_id'] = str(uuid.uuid4())

        # Ensure symbol matches
        strategy['symbol'] = symbol

        # Validate schema
        is_valid, error_msg = validate_strategy_schema(strategy)
        if not is_valid:
            logger.error(f"Strategy validation failed: {error_msg}")
            logger.error(f"Strategy data: {json.dumps(strategy, indent=2)}")
            raise ValueError(f"Invalid strategy schema: {error_msg}")

        # Generate suggestions
        suggestions = generate_strategy_suggestions(strategy)

        # Add timestamp
        strategy['created_at'] = datetime.utcnow().isoformat()

        logger.info(f"Successfully generated and validated strategy: {strategy['strategy_id']}")

        return {
            "strategy": strategy,
            "suggestions": suggestions,
            "meta": {
                "generated_at": datetime.utcnow().isoformat(),
                "model": OPENAI_MODEL,
                "validated": True
            }
        }

    except Exception as e:
        logger.error(f"Error generating secure strategy: {e}", exc_info=True)
        raise

