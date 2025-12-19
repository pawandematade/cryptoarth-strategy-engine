from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, Dict, Any
import logging
import json
from app.services.openai_service import generate_strategy
from app.services.backtest_service import run_backtest
from app.services.prompt_builder import build_prompt
from app.store.redis_client import redis_client
from app.services.credits_service import consume_credits, check_credits_available, get_user_id_from_header

logger = logging.getLogger(__name__)

router = APIRouter()


class AIStrategyRequest(BaseModel):
    """
    Request model for AI strategy generation.
    
    SYSTEM RULE: All parameters are converted to a single prompt string.
    Only the prompt is sent to OpenAI - no separate fields.
    """
    prompt: str = Field(..., description="Natural language description of the trading strategy")
    symbol: Optional[str] = Field(default="BTCUSD", description="Trading symbol (e.g., BTCUSD)")
    timeframe: Optional[str] = Field(default=None, description="Trading timeframe (e.g., 15MIN, 1H, 1D)")
    chart_type: Optional[str] = Field(default=None, description="Chart type (candles or heikin_ashi)")
    take_profit: Optional[Dict[str, Any]] = Field(default=None, description="Take profit settings: {type: 'percent'|'point', value: number}")
    stop_loss: Optional[Dict[str, Any]] = Field(default=None, description="Stop loss settings: {type: 'percent'|'point', value: number}")
    trailing_stop: Optional[Dict[str, Any]] = Field(default=None, description="Trailing stop settings: {enabled: bool, type: 'percent'|'point', value: number}")
    current_price: Optional[float] = Field(default=None, description="Current market price for context")
    market_context: Optional[str] = Field(default=None, description="Additional market context")
    
    class Config:
        # Allow extra fields but we'll validate and reject them
        extra = "allow"


class AIStrategyResponse(BaseModel):
    """
    Response model for AI strategy generation.
    
    NOTE: strategy_id is always None - no database storage (runtime only).
    """
    success: bool
    strategy: Optional[dict] = None
    message: str
    strategy_id: Optional[int] = None  # Always None - no database


@router.post("/ai-strategy/generate", response_model=AIStrategyResponse)
def generate_ai_strategy(request: AIStrategyRequest, authorization: Optional[str] = Header(None)):
    """
    Generate a trading strategy using AI based on natural language description.
    
    SYSTEM RULES:
    1. All payload parameters are converted to a single prompt string via PromptBuilder
    2. Only { "prompt": "..." } is sent to OpenAI
    3. No database storage - runtime only
    4. Extra keys in payload are rejected
    
    Returns:
        AIStrategyResponse: Generated strategy in structured format
    """
    try:
        # VALIDATION: Reject extra keys (guard against unauthorized fields)
        allowed_fields = {
            'prompt', 'symbol', 'timeframe', 'chart_type', 
            'take_profit', 'stop_loss', 'trailing_stop',
            'current_price', 'market_context'
        }
        request_dict = request.model_dump(exclude_unset=True)
        extra_keys = set(request_dict.keys()) - allowed_fields
        if extra_keys:
            logger.error(f"❌ REJECTED: Extra keys in payload: {extra_keys}")
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid payload: Extra keys not allowed: {list(extra_keys)}. Allowed keys: {list(allowed_fields)}"
            )
        
        # Log incoming request
        logger.info("=" * 80)
        logger.info("🔄 NEW STRATEGY GENERATION REQUEST RECEIVED")
        logger.info(f"Payload: {json.dumps(request_dict, indent=2)}")
        logger.info("=" * 80)
        
        # Validate required fields
        if not request.prompt or not request.prompt.strip():
            logger.error("❌ Validation failed: Prompt is empty")
            raise HTTPException(status_code=400, detail="Prompt is required")
        
        # CREDIT FACILITY DISABLED FOR TESTING - Code kept for future enablement
        # Check and consume credits
        # user_id = get_user_id_from_header(authorization)
        # credit_check = check_credits_available(user_id, 'ai_generate')
        # 
        # if not credit_check['has_credits']:
        #     raise HTTPException(
        #         status_code=402,  # Payment Required
        #         detail=f"Insufficient credits. {credit_check['message']}. Please purchase more credits to continue."
        #     )
        # 
        # # Consume credits before generating
        # credit_result = consume_credits(user_id, 'ai_generate')
        # if not credit_result['success']:
        #     raise HTTPException(
        #         status_code=402,
        #         detail=f"Failed to process credits: {credit_result['message']}"
        #     )
        
        # Get current price from Redis if not provided
        current_price = request.current_price
        if current_price is None and request.symbol:
            try:
                price_key = f"PRICE:{request.symbol.strip().upper()}"
                price_str = redis_client.get(price_key)
                if price_str:
                    current_price = float(price_str)
                    logger.info(f"Retrieved current price from Redis: {current_price}")
            except Exception as e:
                logger.warning(f"Could not retrieve current price from Redis: {e}")
        
        # CRITICAL: Transform incoming payload into ONE single prompt string
        # 
        # MANDATORY RULES:
        # 1. Frontend sends: { chart_type, prompt, symbol, timeframe, stop_loss, take_profit, ... }
        # 2. We merge ALL fields (including future fields) into ONE human-readable prompt string
        # 3. This merged prompt string is the ONLY thing sent to OpenAI
        # 4. NO other fields (chart_type, symbol, timeframe, stop_loss, take_profit) are sent separately
        # 5. Frontend contract remains unchanged
        #
        # The build_prompt() function merges ALL incoming fields into a single string:
        # - prompt (strategy description)
        # - symbol
        # - timeframe
        # - chart_type
        # - take_profit
        # - stop_loss
        # - trailing_stop
        # - current_price
        # - market_context
        # - Any future fields added from frontend
        try:
            final_prompt = build_prompt(
                strategy_description=request.prompt.strip(),
                symbol=request.symbol,
                timeframe=request.timeframe,
                chart_type=request.chart_type,
                take_profit=request.take_profit,
                stop_loss=request.stop_loss,
                trailing_stop=request.trailing_stop,
                current_price=current_price,
                market_context=request.market_context
            )
        except ValueError as e:
            logger.error(f"❌ PromptBuilder validation failed: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        
        # CRITICAL: Generate strategy using OpenAI
        # 
        # We send ONLY the merged prompt string to OpenAI
        # The final_prompt contains ALL parameters merged into ONE string
        # OpenAI receives ONLY: { "prompt": "<merged string>" } (within messages structure)
        # NO other fields are sent separately
        try:
            logger.info("🤖 Calling OpenAI with merged prompt (all parameters embedded in single string)")
            
            # Call OpenAI with ONLY the merged prompt string
            # generate_strategy() receives only the merged prompt and sends it to OpenAI
            # OpenAI API requires model + messages structure (OpenAI's API requirement)
            # Within messages, user message contains ONLY the merged prompt string
            # No other fields (symbol, timeframe, chart_type, take_profit, stop_loss) are sent separately
            strategy = generate_strategy(user_prompt=final_prompt)
            
            logger.info(f"✅ Strategy generated successfully")
            logger.info(f"Strategy Type: {strategy.get('condition', {}).get('type') if strategy else 'None'}")
            logger.info(f"Strategy Symbol: {strategy.get('symbol') if strategy else 'None'}")
            
            # Log parameters to verify all conditions are captured
            if strategy and strategy.get('parameters'):
                logger.info(f"Strategy Parameters: {json.dumps(strategy.get('parameters'), indent=2)}")
        except Exception as e:
            logger.error(f"Error generating strategy: {e}", exc_info=True)
            error_msg = str(e)
            # Provide more specific error messages
            if "API key" in error_msg or "authentication" in error_msg.lower() or "401" in error_msg or "403" in error_msg:
                return AIStrategyResponse(
                    success=False,
                    message=f"OpenAI API authentication failed. Please check your OPENAI_API_KEY in .env file. Error: {error_msg}"
                )
            elif "rate limit" in error_msg.lower() or "429" in error_msg:
                return AIStrategyResponse(
                    success=False,
                    message=f"OpenAI API rate limit exceeded. Please try again in a few moments. Error: {error_msg}"
                )
            else:
                return AIStrategyResponse(
                    success=False,
                    message=f"Error generating strategy: {error_msg}"
                )
        
        if not strategy:
            logger.error("❌ Strategy generation returned None. Check OpenAI service logs.")
            # Check if client is initialized
            from app.services.openai_service import client
            if not client:
                return AIStrategyResponse(
                    success=False,
                    message="OpenAI client not initialized. Please check OPENAI_API_KEY in .env file and restart the server."
                )
            return AIStrategyResponse(
                success=False,
                message="Failed to generate strategy. Please check server logs for details. Possible issues: Invalid API key, network error, or OpenAI service unavailable."
            )
        
        # All trading rules come from OpenAI response based on the prompt
        # No overrides - we trust OpenAI to extract all parameters from the prompt
        if strategy:
            # CRITICAL: Final normalization - ensure condition.value is removed
            if strategy.get('condition') and 'value' in strategy.get('condition', {}):
                del strategy['condition']['value']
                logger.info("Removed condition.value from final response")
            
            # CRITICAL: Remove userParams if it exists (security violation)
            # userParams contains frontend request data and must NEVER be in strategy object
            if 'userParams' in strategy:
                del strategy['userParams']
                logger.warning("⚠️ Removed userParams from strategy object (security violation)")
            
            # CRITICAL: Ensure single source of truth for parameters
            # Both condition.parameters and root parameters should reference the same object
            condition = strategy.get('condition', {})
            if condition and 'parameters' in condition:
                # Use condition.parameters as source of truth
                params = condition['parameters']
                strategy['parameters'] = params
                # Ensure both reference the same object (no duplication)
                strategy['condition']['parameters'] = params
            elif 'parameters' in strategy:
                # If only root parameters exist, sync to condition
                params = strategy['parameters']
                if condition:
                    condition['parameters'] = params
                    strategy['condition'] = condition
            
            # CRITICAL: Final validation - strategy must contain ONLY AI-generated data
            # Allowed fields: symbol, condition, parameters
            # Forbidden fields: userParams, prompt, chart_type, timeframe (from request)
            allowed_strategy_fields = {'symbol', 'condition', 'parameters'}
            strategy_keys = set(strategy.keys())
            forbidden_fields = strategy_keys - allowed_strategy_fields
            
            if forbidden_fields:
                logger.error(f"❌ SECURITY VIOLATION: Strategy contains forbidden fields: {forbidden_fields}")
                # Remove all forbidden fields
                for field in forbidden_fields:
                    del strategy[field]
                    logger.warning(f"⚠️ Removed forbidden field '{field}' from strategy object")
            
            logger.info(f"✅ Using OpenAI response parameters (from prompt)")
            
            # CRITICAL: Do NOT include request payload data in response
            # Request payload (prompt, symbol, timeframe, chart_type, take_profit, stop_loss, etc.) is INTERNAL ONLY
            # Response contains ONLY the parsed strategy from OpenAI (symbol, condition, parameters)
            # No userParams, no request data, no builder/internal fields
            # Condition must contain ONLY: type and parameters (no value field)
            
            # Final check: Verify strategy structure is clean
            final_strategy_keys = set(strategy.keys())
            if 'userParams' in final_strategy_keys:
                raise ValueError("CRITICAL ERROR: userParams still present in strategy after cleanup")
            if not final_strategy_keys.issubset(allowed_strategy_fields):
                raise ValueError(f"CRITICAL ERROR: Strategy contains unexpected fields: {final_strategy_keys - allowed_strategy_fields}")
            
            # Log final strategy parameters (for debugging only - not in response)
            logger.info("=" * 80)
            logger.info("📊 FINAL STRATEGY PARAMETERS:")
            logger.info(f"{json.dumps(strategy.get('parameters', {}), indent=2)}")
            logger.info("=" * 80)
        
        # NO DATABASE STORAGE - Runtime only
        logger.info("=" * 80)
        logger.info("✅ STRATEGY GENERATION COMPLETED SUCCESSFULLY (Runtime Only - No Storage)")
        logger.info(f"Strategy Type: {strategy.get('strategy_type') if strategy else 'None'}")
        
        # FINAL VALIDATION: Verify strategy contains all required sections (unified schema)
        if strategy:
            # REQUIRED sections - must be present
            required_sections = {'symbol', 'strategy_type', 'logic', 'risk', 'meta'}
            final_keys = set(strategy.keys())
            
            # Check for missing required sections
            missing_sections = required_sections - final_keys
            if missing_sections:
                logger.error(f"❌ CRITICAL ERROR: Strategy missing required sections: {missing_sections}")
                raise ValueError(f"Strategy must contain all required sections: {required_sections}. Missing: {missing_sections}")
            
            # Check for forbidden fields (but don't remove required sections)
            allowed = {'symbol', 'strategy_type', 'logic', 'risk', 'meta'}
            forbidden_fields = final_keys - allowed
            if forbidden_fields:
                logger.warning(f"⚠️ Strategy contains unexpected fields: {forbidden_fields}")
                # Remove only if not required
                for key in list(forbidden_fields):
                    if key not in required_sections:
                        del strategy[key]
                        logger.warning(f"⚠️ Removed forbidden field '{key}' from final strategy")
            
            if 'userParams' in strategy:
                raise ValueError("CRITICAL SECURITY ERROR: userParams found in final strategy object")
            
            # Final validation: Check for forbidden fields in logic section
            logic = strategy.get('logic', {})
            if not logic:
                raise ValueError("CRITICAL ERROR: logic section is empty")
            if 'ema_fast' in logic or 'ema_slow' in logic:
                raise ValueError("CRITICAL ERROR: ema_fast or ema_slow found in logic section - use emas array instead")
            if 'timeframe' in logic or 'chart_type' in logic:
                raise ValueError("CRITICAL ERROR: timeframe or chart_type found in logic section - must be in meta section")
            
            # Verify required sections are not empty
            if not strategy.get('logic'):
                raise ValueError("CRITICAL ERROR: logic section must not be empty")
            if not isinstance(strategy.get('logic', {}).get('emas'), list) or len(strategy.get('logic', {}).get('emas', [])) == 0:
                raise ValueError("CRITICAL ERROR: logic.emas must be a non-empty array")
        
        logger.info("=" * 80)
        
        return AIStrategyResponse(
            success=True,
            strategy=strategy,
            message="Strategy generated successfully",
            strategy_id=None  # No database - always None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in generate_ai_strategy: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/ai-strategy/list")
def list_strategies():
    """
    Get all saved strategies.
    
    Returns:
        dict: List of all strategies
    """
    try:
        strategies = load_strategies()
        return {
            "success": True,
            "count": len(strategies),
            "strategies": strategies
        }
    except Exception as e:
        logger.error(f"Error listing strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load strategies: {str(e)}")


@router.get("/ai-strategy/{strategy_id}")
def get_strategy(strategy_id: int):
    """
    Get a specific strategy by ID.
    
    Returns:
        dict: Strategy details
    """
    try:
        strategies = load_strategies()
        strategy = next((s for s in strategies if s.get("id") == strategy_id), None)
        
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy with ID {strategy_id} not found")
        
        return {
            "success": True,
            "strategy": strategy
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get strategy: {str(e)}")


class BacktestRequest(BaseModel):
    """Request model for backtest"""
    strategy: Dict[str, Any] = Field(..., description="Strategy object to backtest")
    period: str = Field(default="month", description="Time period: 'year', 'month', or 'day'")


@router.post("/ai-strategy/backtest")
def run_strategy_backtest(request: BacktestRequest, authorization: Optional[str] = Header(None)):
    """
    Run backtest for a strategy.
    
    Args:
        request: BacktestRequest with strategy and period
        authorization: Authorization header with user ID
    
    Returns:
        dict: Comprehensive backtest results
    """
    try:
        # Validate input
        if not request.strategy:
            raise HTTPException(status_code=400, detail="Strategy is required")
        
        if request.period not in ['year', 'month', 'day']:
            raise HTTPException(status_code=400, detail="Period must be 'year', 'month', or 'day'")
        
        # CREDIT FACILITY DISABLED FOR TESTING - Code kept for future enablement
        # Check and consume credits
        # user_id = get_user_id_from_header(authorization)
        # credit_check = check_credits_available(user_id, 'backtest')
        # 
        # if not credit_check['has_credits']:
        #     raise HTTPException(
        #         status_code=402,  # Payment Required
        #         detail=f"Insufficient credits. {credit_check['message']}. Please purchase more credits to run backtest."
        #     )
        # 
        # # Consume credits before running backtest
        # credit_result = consume_credits(user_id, 'backtest')
        # if not credit_result['success']:
        #     raise HTTPException(
        #         status_code=402,
        #         detail=f"Failed to process credits: {credit_result['message']}"
        #     )
        
        # Validate strategy structure
        strategy = request.strategy
        
        # Check for required fields
        if not isinstance(strategy, dict):
            raise HTTPException(status_code=400, detail="Strategy must be a dictionary/object")
        
        if not strategy.get('symbol'):
            raise HTTPException(status_code=400, detail="Strategy must have a 'symbol' field")
        
        if not strategy.get('condition'):
            raise HTTPException(status_code=400, detail="Strategy must have a 'condition' field")
        
        condition = strategy.get('condition')
        if not isinstance(condition, dict):
            raise HTTPException(status_code=400, detail="Strategy condition must be a dictionary/object")
        
        if not condition.get('type'):
            raise HTTPException(status_code=400, detail="Strategy condition must have a 'type' field")
        
        # Normalize strategy structure - ensure parameters are accessible
        # Parameters can be at root level or in condition.parameters
        if 'parameters' not in strategy and condition.get('parameters'):
            strategy['parameters'] = condition.get('parameters')
        elif 'parameters' in strategy and not condition.get('parameters'):
            condition['parameters'] = strategy.get('parameters')
        
        # For indicator strategies, ensure parameters exist
        condition_type = condition.get('type')
        if condition_type in ['ema_crossover', 'supertrend', 'moving_average', 'rsi', 'macd', 'bollinger_bands']:
            if not strategy.get('parameters') and not condition.get('parameters'):
                # Add default parameters based on type
                if condition_type == 'ema_crossover':
                    strategy['parameters'] = {'ema_fast': 9, 'ema_slow': 21, 'tp_percent': 1, 'sl_percent': 1}
                    condition['parameters'] = strategy['parameters']
                elif condition_type == 'supertrend':
                    strategy['parameters'] = {'period': 7, 'multiplier': 3}
                    condition['parameters'] = strategy['parameters']
        
        logger.info(f"Running backtest for strategy: {strategy.get('symbol', 'N/A')}, type: {condition_type}, period: {request.period}")
        logger.debug(f"Strategy structure: symbol={strategy.get('symbol')}, condition.type={condition_type}, has_parameters={bool(strategy.get('parameters') or condition.get('parameters'))}")
        
        # Run backtest
        backtest_results = run_backtest(strategy, request.period)
        
        if not backtest_results:
            raise HTTPException(status_code=500, detail="Failed to run backtest")
        
        # Cache backtest results in Redis for performance endpoint
        try:
            strategy_id = None
            # Try to get strategy_id from strategy
            if 'strategy_id' in strategy:
                strategy_id = strategy['strategy_id']
            elif 'id' in strategy:
                strategy_id = str(strategy['id'])
            
            if strategy_id:
                backtest_key = f"BACKTEST:{strategy_id}"
                import json
                redis_client.setex(
                    backtest_key,
                    86400 * 7,  # Cache for 7 days
                    json.dumps(backtest_results)
                )
                logger.info(f"Cached backtest results for strategy: {strategy_id}")
        except Exception as cache_error:
            logger.warning(f"Failed to cache backtest results: {cache_error}")
            # Don't fail the request if caching fails
        
        return {
            "success": True,
            "results": backtest_results,
            "message": f"Backtest completed successfully for {request.period}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running backtest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

