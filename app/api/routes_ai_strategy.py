from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
import json
from app.services.openai_service import generate_strategy, generate_strategy_with_context
from app.services.backtest_service import run_backtest
from app.strategies.loader import load_strategies, save_strategy
from app.store.redis_client import redis_client
from app.services.credits_service import consume_credits, check_credits_available, get_user_id_from_header

logger = logging.getLogger(__name__)

router = APIRouter()


class AIStrategyRequest(BaseModel):
    """Request model for AI strategy generation"""
    prompt: str = Field(..., description="Natural language description of the trading strategy")
    symbol: str = Field(default="BTCUSD", description="Trading symbol (e.g., BTCUSD)")
    current_price: Optional[float] = Field(default=None, description="Current market price for context")
    market_context: Optional[str] = Field(default=None, description="Additional market context")
    save_strategy: bool = Field(default=False, description="Whether to save the strategy to strategies.json")
    # New trading parameters
    timeframe: Optional[str] = Field(default=None, description="Trading timeframe (e.g., 15MIN, 1H, 1D)")
    chart_type: Optional[str] = Field(default=None, description="Chart type (candles or heikin_ashi)")
    take_profit: Optional[Dict[str, Any]] = Field(default=None, description="Take profit settings: {type: 'percent'|'point', value: number}")
    stop_loss: Optional[Dict[str, Any]] = Field(default=None, description="Stop loss settings: {type: 'percent'|'point', value: number}")
    trailing_stop: Optional[Dict[str, Any]] = Field(default=None, description="Trailing stop settings: {enabled: bool, type: 'percent'|'point', value: number}")
    # Cache-busting parameters (ignored but logged)
    request_id: Optional[str] = Field(default=None, description="Unique request ID for tracking")
    _timestamp: Optional[int] = Field(default=None, description="Timestamp for cache-busting")
    force_refresh: Optional[bool] = Field(default=False, description="Force refresh flag")


class AIStrategyResponse(BaseModel):
    """Response model for AI strategy generation"""
    success: bool
    strategy: Optional[dict] = None
    message: str
    strategy_id: Optional[int] = None


@router.post("/ai-strategy/generate", response_model=AIStrategyResponse)
def generate_ai_strategy(request: AIStrategyRequest, authorization: Optional[str] = Header(None)):
    """
    Generate a trading strategy using AI based on natural language description.
    
    Example requests:
    - "Buy when BTC price goes above 90000"
    - "Alert me when price drops below 85000"
    - "Notify when price is between 88000 and 92000"
    
    Returns:
        AIStrategyResponse: Generated strategy in structured format
    """
    try:
        # Log incoming request for debugging
        logger.info("=" * 80)
        logger.info("🔄 NEW STRATEGY GENERATION REQUEST RECEIVED")
        logger.info(f"Request ID: {request.request_id}")
        logger.info(f"Timestamp: {request._timestamp}")
        logger.info(f"Force Refresh: {request.force_refresh}")
        logger.info(f"Prompt (first 100 chars): {request.prompt[:100] if request.prompt else 'None'}...")
        logger.info(f"Full Prompt: {request.prompt}")
        logger.info(f"Prompt Length: {len(request.prompt) if request.prompt else 0}")
        logger.info(f"Symbol: {request.symbol}")
        logger.info(f"Timeframe: {request.timeframe}")
        logger.info(f"Chart Type: {request.chart_type}")
        logger.info(f"Take Profit: {request.take_profit}")
        logger.info(f"Stop Loss: {request.stop_loss}")
        logger.info(f"Trailing Stop: {request.trailing_stop}")
        logger.info("=" * 80)
        
        # Validate input
        if not request.prompt or not request.prompt.strip():
            logger.error("❌ Validation failed: Prompt is empty")
            raise HTTPException(status_code=400, detail="Prompt is required")
        
        if not request.symbol or not request.symbol.strip():
            logger.error("❌ Validation failed: Symbol is empty")
            raise HTTPException(status_code=400, detail="Symbol is required")
        
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
        if current_price is None:
            try:
                price_key = f"PRICE:{request.symbol}"
                price_str = redis_client.get(price_key)
                if price_str:
                    current_price = float(price_str)
                    logger.info(f"Retrieved current price from Redis: {current_price}")
            except Exception as e:
                logger.warning(f"Could not retrieve current price from Redis: {e}")
        
        # CRITICAL: Create a STRUCTURED prompt that includes ALL payload parameters
        # OpenAI needs to see ALL parameters clearly, not just appended to description
        original_prompt = request.prompt.strip()
        
        logger.info(f"📝 Original User Prompt: {original_prompt}")
        logger.info(f"📝 Original Prompt Length: {len(original_prompt)}")
        
        # Build a structured prompt that clearly separates description from parameters
        # This format makes it crystal clear to OpenAI what parameters to use
        structured_prompt_parts = []
        structured_prompt_parts.append(f"Strategy Description: {original_prompt}")
        
        # Add all parameters in a clear, structured format
        if request.symbol:
            structured_prompt_parts.append(f"Symbol: {request.symbol.strip().upper()}")
            logger.info(f"📝 Parameter - Symbol: {request.symbol.strip().upper()}")
        
        if request.timeframe:
            structured_prompt_parts.append(f"Timeframe: {request.timeframe}")
            logger.info(f"📝 Parameter - Timeframe: {request.timeframe}")
        
        if request.chart_type:
            chart_type_name = "Heikin Ashi" if request.chart_type == "heikin_ashi" else "Candles"
            structured_prompt_parts.append(f"Chart Type: {chart_type_name}")
            logger.info(f"📝 Parameter - Chart Type: {chart_type_name}")
        
        if request.take_profit and request.take_profit.get('value'):
            tp_type = request.take_profit.get('type', 'percent')
            tp_value = request.take_profit.get('value')
            if tp_type == 'percent':
                structured_prompt_parts.append(f"Take Profit: {tp_value}% (percentage)")
            else:
                structured_prompt_parts.append(f"Take Profit: {tp_value} points")
            logger.info(f"📝 Parameter - Take Profit: {tp_value} {tp_type}")
        
        if request.stop_loss and request.stop_loss.get('value'):
            sl_type = request.stop_loss.get('type', 'percent')
            sl_value = request.stop_loss.get('value')
            if sl_type == 'percent':
                structured_prompt_parts.append(f"Stop Loss: {sl_value}% (percentage)")
            else:
                structured_prompt_parts.append(f"Stop Loss: {sl_value} points")
            logger.info(f"📝 Parameter - Stop Loss: {sl_value} {sl_type}")
        
        if request.trailing_stop and request.trailing_stop.get('enabled') and request.trailing_stop.get('value'):
            tr_type = request.trailing_stop.get('type', 'percent')
            tr_value = request.trailing_stop.get('value')
            if tr_type == 'percent':
                structured_prompt_parts.append(f"Trailing Stop: {tr_value}% (percentage)")
            else:
                structured_prompt_parts.append(f"Trailing Stop: {tr_value} points")
            logger.info(f"📝 Parameter - Trailing Stop: {tr_value} {tr_type}")
        
        # Create the final structured prompt
        enhanced_prompt = "\n".join(structured_prompt_parts)
        
        # Log the final structured prompt
        logger.info("=" * 80)
        logger.info(f"📝 FINAL STRUCTURED PROMPT (with ALL parameters):")
        logger.info(enhanced_prompt)
        logger.info(f"📝 Enhanced Prompt Length: {len(enhanced_prompt)}")
        logger.info("=" * 80)
        
        # Generate strategy using OpenAI
        try:
            logger.info("🤖 Calling OpenAI service to generate strategy...")
            logger.info(f"📝 Request ID: {request.request_id}")
            logger.info(f"📝 Timestamp: {request._timestamp}")
            logger.info(f"📝 Sending to OpenAI - Original Prompt: {request.prompt}")
            logger.info(f"📝 Sending to OpenAI - Enhanced Prompt: {enhanced_prompt}")
            logger.info(f"📝 Enhanced Prompt Hash (first 200 chars): {enhanced_prompt[:200]}")
            
            # Log prompt comparison if this is not the first request
            # This helps identify if same prompt is being sent
            logger.info(f"📝 Full Enhanced Prompt Length: {len(enhanced_prompt)}")
            logger.info(f"📝 Enhanced Prompt (FULL): {enhanced_prompt}")
            
            if current_price or request.market_context:
                strategy = generate_strategy_with_context(
                    user_prompt=enhanced_prompt,  # Use enhanced prompt with all parameters
                    symbol=request.symbol.strip().upper(),
                    current_price=current_price,
                    market_context=request.market_context
                )
            else:
                strategy = generate_strategy(
                    user_prompt=enhanced_prompt,  # Use enhanced prompt with all parameters
                    symbol=request.symbol.strip().upper()
                )
            
            logger.info(f"✅ Strategy generated successfully")
            logger.info(f"Strategy Type: {strategy.get('condition', {}).get('type') if strategy else 'None'}")
            logger.info(f"Strategy Symbol: {strategy.get('symbol') if strategy else 'None'}")
            
            # Log parameters to verify all conditions are captured
            if strategy and strategy.get('parameters'):
                logger.info(f"Strategy Parameters: {json.dumps(strategy.get('parameters'), indent=2)}")
                # Check if additional conditions are present
                params = strategy.get('parameters', {})
                if params.get('wait_candle_close'):
                    logger.info("✅ Candle close condition detected in parameters")
                if params.get('require_high_break'):
                    logger.info("✅ High break condition detected in parameters")
                if params.get('entry_condition'):
                    logger.info(f"✅ Entry condition: {params.get('entry_condition')}")
        except Exception as e:
            logger.error(f"Error generating strategy: {e}", exc_info=True)
            return AIStrategyResponse(
                success=False,
                message=f"Error generating strategy: {str(e)}"
            )
        
        if not strategy:
            logger.error("❌ Strategy generation returned None. Check OpenAI service logs.")
            return AIStrategyResponse(
                success=False,
                message="Failed to generate strategy. Please check your OpenAI API key and try again."
            )
        
        # CRITICAL: Merge user-provided TP/SL into strategy parameters
        # This ensures user's TP/SL values override any defaults or OpenAI response
        if strategy:
            params = strategy.get('parameters', {})
            condition_params = strategy.get('condition', {}).get('parameters', {})
            if condition_params:
                params.update(condition_params)
            
            # CRITICAL: Always use user-provided TP/SL from request (they override OpenAI response)
            # This ensures the strategy uses the exact values from the payload
            if request.take_profit and request.take_profit.get('value'):
                tp_type = request.take_profit.get('type', 'percent')
                tp_value = request.take_profit.get('value')
                # Remove any existing TP values from OpenAI response
                params.pop('tp_percent', None)
                params.pop('tp_point', None)
                params.pop('tp', None)
                # Set the user-provided TP
                if tp_type == 'percent':
                    params['tp_percent'] = tp_value
                    params['tp'] = tp_value  # Also set tp for compatibility
                    logger.info(f"✅ OVERRIDING with user-provided TP: {tp_value}%")
                else:  # point
                    params['tp_point'] = tp_value
                    params['tp'] = tp_value
                    logger.info(f"✅ OVERRIDING with user-provided TP: {tp_value} points")
            else:
                logger.info("⚠️ No user-provided TP - using OpenAI response or defaults")
            
            if request.stop_loss and request.stop_loss.get('value'):
                sl_type = request.stop_loss.get('type', 'percent')
                sl_value = request.stop_loss.get('value')
                # Remove any existing SL values from OpenAI response
                params.pop('sl_percent', None)
                params.pop('sl_point', None)
                params.pop('sl', None)
                # Set the user-provided SL
                if sl_type == 'percent':
                    params['sl_percent'] = sl_value
                    params['sl'] = sl_value  # Also set sl for compatibility
                    logger.info(f"✅ OVERRIDING with user-provided SL: {sl_value}%")
                else:  # point
                    params['sl_point'] = sl_value
                    params['sl'] = sl_value
                    logger.info(f"✅ OVERRIDING with user-provided SL: {sl_value} points")
            else:
                logger.info("⚠️ No user-provided SL - using OpenAI response or defaults")
            
            # Also ensure symbol matches the request
            if request.symbol:
                strategy['symbol'] = request.symbol.strip().upper()
                logger.info(f"✅ Using user-provided Symbol: {strategy['symbol']}")
            
            # Update strategy with merged parameters
            strategy['parameters'] = params
            if strategy.get('condition'):
                strategy['condition']['parameters'] = params
            
            # Also create risk object for compatibility
            if request.take_profit or request.stop_loss:
                strategy['risk'] = {}
                if request.take_profit:
                    strategy['risk']['take_profit'] = request.take_profit
                if request.stop_loss:
                    strategy['risk']['stop_loss'] = request.stop_loss
                logger.info(f"✅ Risk object created with user TP/SL")
            
            # Add user parameters to strategy for frontend display
            strategy['userParams'] = {
                'prompt': request.prompt.strip(),  # Store original prompt
                'symbol': request.symbol.strip().upper(),
                'timeframe': request.timeframe,
                'chartType': request.chart_type,
                'tpValue': request.take_profit.get('value') if request.take_profit else None,
                'tpType': request.take_profit.get('type') if request.take_profit else None,
                'slValue': request.stop_loss.get('value') if request.stop_loss else None,
                'slType': request.stop_loss.get('type') if request.stop_loss else None,
                'trailingEnabled': request.trailing_stop.get('enabled') if request.trailing_stop else False,
                'trailingValue': request.trailing_stop.get('value') if request.trailing_stop else None,
                'trailingType': request.trailing_stop.get('type') if request.trailing_stop else None,
            }
            
            # Log final strategy parameters
            logger.info("=" * 80)
            logger.info("📊 FINAL STRATEGY PARAMETERS:")
            logger.info(f"{json.dumps(strategy.get('parameters', {}), indent=2)}")
            logger.info("=" * 80)
            logger.info(f"✅ User parameters added to strategy")
        
        # Save strategy if requested
        strategy_id = None
        if request.save_strategy:
            try:
                strategy_id = save_strategy(strategy)
                logger.info(f"✅ Strategy saved with ID: {strategy_id}")
            except Exception as e:
                logger.error(f"❌ Failed to save strategy: {e}")
                return AIStrategyResponse(
                    success=True,
                    strategy=strategy,
                    message=f"Strategy generated successfully but failed to save: {str(e)}"
                )
        
        logger.info("=" * 80)
        logger.info("✅ STRATEGY GENERATION COMPLETED SUCCESSFULLY")
        logger.info(f"Strategy ID: {strategy_id}")
        logger.info(f"Strategy Type: {strategy.get('condition', {}).get('type') if strategy else 'None'}")
        logger.info("=" * 80)
        
        return AIStrategyResponse(
            success=True,
            strategy=strategy,
            message="Strategy generated successfully",
            strategy_id=strategy_id
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

