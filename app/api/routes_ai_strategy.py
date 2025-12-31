from fastapi import APIRouter, HTTPException, Header, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError, model_validator
from typing import Optional, Dict, Any
import logging
import json
import copy
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.services.openai_service import generate_strategy
from app.services.backtest_service import run_backtest
from app.services.prompt_builder import build_prompt
from app.store.redis_client import redis_client
from app.services.credit_service import (
    check_credits_available,
    deduct_credits,
    get_user_credits
)
from app.services.user_sync_service import get_or_sync_user
from app.engine.backtest_engine import BacktestEngine
from app.feed.delta_history import fetch_ohlcv, get_default_lookback_days
from app.database import get_db
from app.services.strategy_save_service import save_strategy

logger = logging.getLogger(__name__)

router = APIRouter()


class AIStrategyRequest(BaseModel):
    """
    Request model for AI strategy generation.
    
    SYSTEM RULE: All parameters are converted to a single prompt string.
    Only the prompt is sent to OpenAI - no separate fields.
    
    ACCEPTS:
    - 'prompt' OR 'description' (both map to the same internal 'prompt' field)
    - 'type' (optional strategy type hint, e.g., 'indicator_based')
    """
    prompt: Optional[str] = Field(default=None, description="Natural language description of the trading strategy")
    description: Optional[str] = Field(default=None, description="Alias for 'prompt' - natural language description of the trading strategy")
    type: Optional[str] = Field(default=None, description="Strategy type hint (e.g., 'indicator_based', 'trend_following', etc.)")
    symbol: Optional[str] = Field(default="BTCUSD", description="Trading symbol (e.g., BTCUSD)")
    timeframe: Optional[str] = Field(default=None, description="Trading timeframe (e.g., 15MIN, 1H, 1D)")
    chart_type: Optional[str] = Field(default=None, description="Chart type (candles or heikin_ashi)")
    take_profit: Optional[Dict[str, Any]] = Field(default=None, description="Take profit settings: {type: 'percent'|'point', value: number}")
    stop_loss: Optional[Dict[str, Any]] = Field(default=None, description="Stop loss settings: {type: 'percent'|'point', value: number}")
    trailing_stop: Optional[Dict[str, Any]] = Field(default=None, description="Trailing stop settings: {enabled: bool, type: 'percent'|'point', value: number}")
    trading_session: Optional[str] = Field(default=None, description="Trading session (e.g., 'asian', 'european', 'american', 'all')")
    max_trades_per_day: Optional[int] = Field(default=None, description="Maximum trades per day")
    current_price: Optional[float] = Field(default=None, description="Current market price for context")
    market_context: Optional[str] = Field(default=None, description="Additional market context")
    
    @model_validator(mode='before')
    @classmethod
    def normalize_prompt(cls, data: Any) -> Any:
        """Normalize 'description' to 'prompt' if prompt is not provided."""
        if isinstance(data, dict):
            prompt_val = data.get('prompt')
            description_val = data.get('description')
            
            # Check if values are non-empty strings
            prompt_empty = not prompt_val or (isinstance(prompt_val, str) and not prompt_val.strip())
            description_non_empty = description_val and isinstance(description_val, str) and description_val.strip()
            
            # If 'description' is provided (non-empty) but 'prompt' is missing/empty, copy description to prompt
            if description_non_empty and prompt_empty:
                data['prompt'] = description_val.strip()
        return data
    
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
def generate_ai_strategy(
    request: AIStrategyRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Generate a trading strategy using AI based on natural language description.
    
    SYSTEM RULES:
    1. All payload parameters are converted to a single prompt string via PromptBuilder
    2. Only { "prompt": "..." } is sent to OpenAI
    3. No database storage - runtime only
    4. Extra keys in payload are rejected
    5. Credits are checked and deducted before generation (1 credit per generate)
    
    Returns:
        AIStrategyResponse: Generated strategy in structured format
    """
    try:
        # FALLBACK: Normalize description to prompt if validator didn't catch it
        # Handle both None and empty string cases
        prompt_value = request.prompt
        description_value = request.description
        
        # Normalize: if prompt is missing/empty but description exists, use description
        if (not prompt_value or not str(prompt_value).strip()) and description_value and str(description_value).strip():
            request.prompt = str(description_value).strip()
            logger.info("✅ Normalized 'description' to 'prompt' in endpoint")
            prompt_value = request.prompt
        
        # Validate required fields FIRST (before extra keys check)
        if not prompt_value or not str(prompt_value).strip():
            logger.error("❌ Validation failed: Prompt is empty")
            logger.error(f"Request prompt: {repr(request.prompt)}")
            logger.error(f"Request description: {repr(request.description)}")
            raise HTTPException(
                status_code=400, 
                detail="Either 'prompt' or 'description' is required and cannot be empty. Please provide a non-empty strategy description."
            )
        
        # VALIDATION: Reject extra keys (guard against unauthorized fields)
        # Note: We check after normalization, so 'description' might still be in the dict
        allowed_fields = {
            'prompt', 'description', 'type', 'symbol', 'timeframe', 'chart_type', 
            'take_profit', 'stop_loss', 'trailing_stop',
            'trading_session', 'max_trades_per_day',
            'current_price', 'market_context'
        }
        request_dict = request.model_dump(exclude_unset=True)
        
        # Log incoming request BEFORE extra keys check for debugging
        logger.info("=" * 80)
        logger.info("🔄 NEW STRATEGY GENERATION REQUEST RECEIVED")
        logger.info(f"Raw payload keys: {list(request_dict.keys())}")
        logger.info(f"Payload: {json.dumps(request_dict, indent=2)}")
        logger.info(f"Prompt value: {request.prompt}")
        logger.info("=" * 80)
        
        extra_keys = set(request_dict.keys()) - allowed_fields
        if extra_keys:
            logger.error(f"❌ REJECTED: Extra keys in payload: {extra_keys}")
            logger.error(f"Allowed fields: {allowed_fields}")
            logger.error(f"Received fields: {set(request_dict.keys())}")
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid payload: Extra keys not allowed: {list(extra_keys)}. Allowed keys: {sorted(allowed_fields)}"
            )
        
        # CREDIT CHECK AND DEDUCTION (MANDATORY - FIRST STEP)
        # CRITICAL: Credit deduction happens INSIDE this API - this is the SINGLE place for deduction
        # Get user from authorization header
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # Sync user and get local user ID
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate user"
            )
        
        # CRITICAL: Log user IDs for debugging
        logger.info(f"🔍 CREDIT CHECK DEBUG: user.id={user.id}, user.external_user_id={user.external_user_id}")
        
        # CRITICAL: FIRST STEP - Check and deduct credits BEFORE any other processing
        # This ensures every API call results in credit deduction
        # CRITICAL FIX: user_credits table stores credits against external_user_id, NOT user.id
        # Check if user has enough credits for AI generate (1 credit)
        is_available, available_credits, required_credits = check_credits_available(
            db, user.external_user_id, 'ai_strategy_generate'
        )
        
        # CRITICAL: Log credit query result
        logger.info(f"🔍 CREDIT CHECK RESULT: is_available={is_available}, available_credits={available_credits}, required_credits={required_credits}")
        
        if not is_available:
            # Block generation if credits <= 0
            logger.warning(f"AI GENERATE BLOCKED – insufficient credits: external_user_id={user.external_user_id}, available={available_credits}, required={required_credits}")
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,  # 402 Payment Required
                detail=f"Insufficient credits. Available: {available_credits}, Required: {required_credits}. Please purchase more credits to continue."
            )
        
        # CRITICAL: Deduct credits FIRST (atomic operation) - BEFORE any generation logic
        # This is the SINGLE place where credits are deducted for AI Generate
        # CRITICAL FIX: Use external_user_id instead of user.id
        success, error_msg = deduct_credits(
            db, user.external_user_id, 'ai_strategy_generate',
            reason="AI strategy generation",
            reference_id=None
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Failed to process credits: {error_msg}"
            )
        
        # CRITICAL: Log credit deduction (silent - no popup, no message to user)
        logger.info(f"AI GENERATE CALLED – credit deducted: user_id={user.id}, credits={required_credits}, remaining={available_credits - required_credits}")
        
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
                trading_session=request.trading_session,
                max_trades_per_day=request.max_trades_per_day,
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
        except ValueError as e:
            # Handle validation errors (like EMA validation for SuperTrend)
            error_msg = str(e)
            logger.error(f"❌ Strategy validation error: {error_msg}")
            return AIStrategyResponse(
                success=False,
                message=f"Strategy validation failed: {error_msg}. Please check your strategy description and try again."
            )
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
            elif "No EMA periods" in error_msg:
                return AIStrategyResponse(
                    success=False,
                    message=f"Strategy validation error: {error_msg}. For SuperTrend or other non-EMA strategies, please ensure your prompt clearly describes the strategy type."
                )
            else:
                return AIStrategyResponse(
                    success=False,
                    message=f"Error generating strategy: {error_msg}. Please check server logs for details."
                )
        
        if not strategy:
            logger.error("❌ Strategy generation returned None. Check OpenAI service logs.")
            # Check if client is initialized, try to reinitialize if needed
            from app.services.openai_service import client, initialize_client
            if not client:
                # Try to reinitialize the client (in case API key was added after server start)
                logger.warning("OpenAI client not initialized. Attempting to reinitialize...")
                if initialize_client():
                    logger.info("✅ OpenAI client reinitialized successfully")
                else:
                    return AIStrategyResponse(
                        success=False,
                        message="OpenAI client not initialized. Please check OPENAI_API_KEY in .env file and restart the server."
                    )
            return AIStrategyResponse(
                success=False,
                message="Failed to generate strategy. Please check server logs for details. Possible issues: Invalid API key, network error, or OpenAI service unavailable."
            )
        
        # All trading rules come from OpenAI response based on the prompt
        # Strategy uses unified schema: symbol, strategy_type, logic, risk, meta
        if strategy:
            # CRITICAL: Remove userParams if it exists (security violation)
            # userParams contains frontend request data and must NEVER be in strategy object
            if 'userParams' in strategy:
                del strategy['userParams']
                logger.warning("⚠️ Removed userParams from strategy object (security violation)")
            
            # CRITICAL: Remove old schema fields if present (condition, parameters, sell_condition)
            # These should have been transformed to unified schema, but remove if still present
            old_schema_fields = ['condition', 'parameters', 'sell_condition']
            for field in old_schema_fields:
                if field in strategy:
                    del strategy[field]
                    logger.warning(f"⚠️ Removed old schema field '{field}' from strategy")
            
            # CRITICAL: Validate unified schema structure
            # REQUIRED sections: symbol, strategy_type, logic, risk, meta
            # DO NOT remove these required sections - only remove forbidden fields
            
            # Check for required sections
            required_sections = {'symbol', 'strategy_type', 'logic', 'risk', 'meta'}
            missing_sections = required_sections - set(strategy.keys())
            if missing_sections:
                logger.error(f"❌ CRITICAL ERROR: Strategy missing required sections: {missing_sections}")
                raise ValueError(f"Strategy must contain all required sections: {required_sections}. Missing: {missing_sections}")
            
            # Validate logic section
            logic = strategy.get('logic', {})
            if not logic:
                logger.error("❌ CRITICAL ERROR: logic section is empty")
                raise ValueError("Strategy logic section must not be empty")
            
            # Validate logic.emas array exists and is non-empty
            if 'emas' not in logic or not isinstance(logic.get('emas'), list) or len(logic.get('emas', [])) == 0:
                logger.error("❌ CRITICAL ERROR: logic.emas array is missing or empty")
                raise ValueError("Strategy logic must contain non-empty 'emas' array")
            
            # Validate entry structure
            if 'entry' not in logic:
                logger.error("❌ CRITICAL ERROR: logic.entry section is missing")
                raise ValueError("Strategy logic must contain 'entry' section")
            if 'buy' not in logic.get('entry', {}) or 'sell' not in logic.get('entry', {}):
                logger.error("❌ CRITICAL ERROR: logic.entry must contain both 'buy' and 'sell'")
                raise ValueError("Strategy entry must contain both 'buy' and 'sell' sections")
            
            # CRITICAL: Remove ONLY forbidden fields from root level, NOT required sections
            # Forbidden fields: userParams, prompt, chart_type (outside meta), timeframe (outside meta), condition, parameters, ema_fast, ema_slow
            allowed_strategy_fields = {'symbol', 'strategy_type', 'logic', 'risk', 'meta'}
            strategy_keys = set(strategy.keys())
            forbidden_fields = strategy_keys - allowed_strategy_fields
            
            if forbidden_fields:
                logger.warning(f"⚠️ Removing forbidden fields: {forbidden_fields}")
                # Remove only forbidden fields (not required sections)
                for field in forbidden_fields:
                    if field not in required_sections:  # Double check - don't remove required sections
                        del strategy[field]
                        logger.warning(f"⚠️ Removed forbidden field '{field}' from strategy object")
            
            # CRITICAL: Remove forbidden fields from logic section (ema_fast, ema_slow, timeframe, chart_type)
            logic = strategy.get('logic', {})
            forbidden_logic_fields = ['ema_fast', 'ema_slow', 'timeframe', 'chart_type', 'condition', 'sell_condition', 'parameters']
            for field in forbidden_logic_fields:
                if field in logic:
                    del logic[field]
                    logger.warning(f"⚠️ Removed forbidden field '{field}' from logic section")
            
            # CRITICAL: Ensure timeframe and chart_type are in meta, not logic
            if 'timeframe' in logic:
                if 'timeframe' not in strategy.get('meta', {}):
                    strategy.setdefault('meta', {})['timeframe'] = logic['timeframe']
                del logic['timeframe']
            if 'chart_type' in logic:
                if 'chart_type' not in strategy.get('meta', {}):
                    strategy.setdefault('meta', {})['chart_type'] = logic['chart_type']
                del logic['chart_type']
            
            logger.info(f"✅ Using OpenAI response with unified schema (logic, risk, meta)")
            
            # CRITICAL: Do NOT include request payload data in response
            # Request payload (prompt, symbol, timeframe, chart_type, take_profit, stop_loss, etc.) is INTERNAL ONLY
            # Response contains ONLY the parsed strategy from OpenAI (symbol, strategy_type, logic, risk, meta)
            # No userParams, no request data, no builder/internal fields
            
            # Final check: Verify strategy has all required sections
            final_strategy_keys = set(strategy.keys())
            if 'userParams' in final_strategy_keys:
                raise ValueError("CRITICAL ERROR: userParams still present in strategy after cleanup")
            
            # Verify required sections are present
            if not required_sections.issubset(final_strategy_keys):
                missing = required_sections - final_strategy_keys
                raise ValueError(f"CRITICAL ERROR: Strategy missing required sections: {missing}")
            
            # Log final strategy structure (for debugging only - not in response)
            logger.info("=" * 80)
            logger.info("📊 FINAL STRATEGY STRUCTURE (Unified Schema):")
            logger.info(f"Symbol: {strategy.get('symbol')}")
            logger.info(f"Strategy Type: {strategy.get('strategy_type')}")
            logger.info(f"EMAs: {strategy.get('logic', {}).get('emas', [])}")
            logger.info(f"Risk: {json.dumps(strategy.get('risk', {}), indent=2)}")
            logger.info(f"Meta: {json.dumps(strategy.get('meta', {}), indent=2)}")
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


@router.get("/ai-strategy/{strategy_id:int}")
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
def run_strategy_backtest(
    request: BacktestRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Run backtest for a strategy.
    
    CREDIT RULES:
    - Every backtest run MUST deduct 1 credit
    - No free usage - all backtests require credits
    - If credits <= 0, return 402 Insufficient Credits
    
    Args:
        request: BacktestRequest with strategy and period
        authorization: Authorization header with user ID
        db: Database session
    
    Returns:
        dict: Comprehensive backtest results
    """
    try:
        # Validate input
        if not request.strategy:
            raise HTTPException(status_code=400, detail="Strategy is required")
        
        if request.period not in ['year', 'month', 'day']:
            raise HTTPException(status_code=400, detail="Period must be 'year', 'month', or 'day'")
        
        # Get user from authorization header
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # Sync user and get local user ID
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate user"
            )
        
        # CREDIT CHECK AND DEDUCTION (MANDATORY - NO FREE USAGE)
        # Every backtest run MUST deduct 1 credit
        # CRITICAL FIX: user_credits table stores credits against external_user_id, NOT user.id
        # Check if user has enough credits for backtest (1 credit)
        logger.info(f"🔍 BACKTEST CREDIT CHECK DEBUG: user.id={user.id}, user.external_user_id={user.external_user_id}")
        is_available, available_credits, required_credits = check_credits_available(
            db, user.external_user_id, 'backtest'
        )
        
        logger.info(f"🔍 BACKTEST CREDIT CHECK RESULT: is_available={is_available}, available_credits={available_credits}, required_credits={required_credits}")
        
        if not is_available:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,  # 402 Payment Required
                detail=f"Insufficient credits. Available: {available_credits}, Required: {required_credits}. Please purchase more credits to continue."
            )
        
        # Extract strategy_code from strategy object (for reference_id in transaction)
        strategy = request.strategy
        strategy_code = (
            strategy.get('strategy_code') or
            strategy.get('meta', {}).get('strategy_code') or
            strategy.get('id') or
            'TEMP'  # Fallback for TEMP strategies
        )
        
        # Deduct credits BEFORE running backtest (atomic operation)
        # CRITICAL FIX: Use external_user_id instead of user.id
        success, error_msg = deduct_credits(
            db, user.external_user_id, 'backtest',
            reason="Backtest execution",
            reference_id=str(strategy_code)
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Failed to process credits: {error_msg}"
            )
        
        logger.info(f"BACKTEST CALLED – credit deducted: user_id={user.id}, strategy_code={strategy_code}, credits={required_credits}, remaining={available_credits - required_credits}")
        
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


class PreviewBacktestRequest(BaseModel):
    """Request model for preview backtest (no strategy_id required)"""
    strategy: Dict[str, Any] = Field(..., description="Full strategy JSON")
    backtest_settings: Dict[str, Any] = Field(..., description="Backtest settings: initialCapital, leverage, capitalPerTrade")


@router.post("/ai-strategy/backtest/preview")
def preview_backtest(request: PreviewBacktestRequest):
    """
    Preview backtest for a strategy WITHOUT saving it.
    
    CRITICAL: This endpoint does NOT deduct credits.
    Credit deduction happens ONLY in:
    - /ai-strategy/generate (AI Generate API) - deducts 1 credit
    - /ai-strategy/backtest (Backtest API) - deducts 1 credit
    
    This endpoint:
    - Does NOT require strategy_id
    - Does NOT save strategy
    - Does NOT cache results
    - Does NOT deduct credits (Preview API only)
    - Runs BacktestEngine directly on provided strategy JSON
    - Applies brokerage calculations if backtest_settings provided
    
    Args:
        request: PreviewBacktestRequest with strategy JSON and backtest_settings
    
    Returns:
        Backtest results with summary, trades, and monthly_performance
    """
    try:
        strategy = request.strategy
        backtest_settings = request.backtest_settings
        
        # Validate strategy structure
        if 'logic' not in strategy:
            raise HTTPException(
                status_code=400,
                detail="Strategy missing required 'logic' section"
            )
        
        if 'risk' not in strategy:
            raise HTTPException(
                status_code=400,
                detail="Strategy missing required 'risk' section"
            )
        
        # Validate backtest settings
        if not backtest_settings:
            raise HTTPException(
                status_code=400,
                detail="backtest_settings is required"
            )
        
        initial_capital = backtest_settings.get('initialCapital')
        leverage = backtest_settings.get('leverage')
        capital_per_trade = backtest_settings.get('capitalPerTrade')
        
        if initial_capital is None or initial_capital <= 0:
            raise HTTPException(
                status_code=400,
                detail="initialCapital must be greater than 0"
            )
        
        if leverage is None or leverage < 1:
            raise HTTPException(
                status_code=400,
                detail="leverage must be at least 1"
            )
        
        if capital_per_trade is None or capital_per_trade < 1 or capital_per_trade > 100:
            raise HTTPException(
                status_code=400,
                detail="capitalPerTrade must be between 1 and 100"
            )
        
        logger.info(f"Running preview backtest for strategy: {strategy.get('symbol', 'UNKNOWN')}")
        
        # Run backtest directly (avoid circular import)
        backtest_results = _run_preview_backtest(strategy)
        
        # Check if backtest returned an error response (missing data)
        if not backtest_results.get('success', True):
            # Return error response with 422 status (Unprocessable Entity - valid request but data unavailable)
            from fastapi import status
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content=backtest_results
            )
        
        # Apply brokerage calculations
        transformed_results = _apply_preview_brokerage(backtest_results, backtest_settings)
        
        # Return results (no caching, no saving)
        return {
            "success": True,
            "mode": "BACKTEST",
            "summary": transformed_results.get('summary', {}),
            "trades": transformed_results.get('trades', []),
            "monthly_performance": transformed_results.get('monthly_performance')
        }
        
    except HTTPException:
        # Re-raise HTTPException as-is (validation errors, etc.)
        raise
    except Exception as e:
        # Catch any unexpected errors and return structured response (don't crash server)
        logger.error(f"Unexpected error in preview_backtest endpoint: {e}", exc_info=True)
        from fastapi import status
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Please try again or contact support."
                }
            }
        )


# Helper functions for preview backtest (avoid circular imports)
PREVIEW_TIMEFRAME_MAP = {
    '1MIN': '1',
    '3M': '3',
    '5MIN': '5',
    '15MIN': '15',
    '30MIN': '30',
    '1H': '60',
    '4H': '240',
    '1D': '1D',
    '1W': '1W',
    '1M': '1M'
}


def _calculate_max_indicator_period(strategy: Dict[str, Any]) -> int:
    """
    Calculate the maximum indicator period required for the strategy.
    
    Checks:
    - EMA periods (logic.emas)
    - SuperTrend period (logic.supertrend.period)
    - RSI period (logic.rsi.period)
    - MACD periods (logic.macd.fast_period, slow_period, signal_period)
    - Bollinger Bands period (logic.bollinger_bands.period)
    - Any other indicator periods
    
    Args:
        strategy: Strategy dictionary
    
    Returns:
        Maximum period required (default: 200 if no indicators found)
    """
    max_period = 0
    logic = strategy.get('logic', {})
    
    # Check EMA periods
    if 'emas' in logic and isinstance(logic['emas'], list):
        ema_periods = [int(p) for p in logic['emas'] if isinstance(p, (int, float)) and p > 0]
        if ema_periods:
            max_period = max(max_period, max(ema_periods))
    
    # Check SuperTrend period
    if 'supertrend' in logic and isinstance(logic['supertrend'], dict):
        period = logic['supertrend'].get('period')
        if isinstance(period, (int, float)) and period > 0:
            max_period = max(max_period, int(period))
    
    # Check RSI period
    if 'rsi' in logic and isinstance(logic['rsi'], dict):
        period = logic['rsi'].get('period')
        if isinstance(period, (int, float)) and period > 0:
            max_period = max(max_period, int(period))
    
    # Check MACD periods
    if 'macd' in logic and isinstance(logic['macd'], dict):
        fast = logic['macd'].get('fast_period')
        slow = logic['macd'].get('slow_period')
        signal = logic['macd'].get('signal_period')
        for period in [fast, slow, signal]:
            if isinstance(period, (int, float)) and period > 0:
                max_period = max(max_period, int(period))
    
    # Check Bollinger Bands period
    if 'bollinger_bands' in logic and isinstance(logic['bollinger_bands'], dict):
        period = logic['bollinger_bands'].get('period')
        if isinstance(period, (int, float)) and period > 0:
            max_period = max(max_period, int(period))
    
    # Default to 200 if no indicators found (safety buffer)
    if max_period == 0:
        max_period = 200
    
    return max_period


def _convert_candles_to_dataframe(candles):
    """Convert candles list to pandas DataFrame."""
    if not candles:
        return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
    
    sorted_candles = sorted(candles, key=lambda c: c.get('time', 0))
    
    data = {
        'open': [float(c['open']) for c in sorted_candles],
        'high': [float(c['high']) for c in sorted_candles],
        'low': [float(c['low']) for c in sorted_candles],
        'close': [float(c['close']) for c in sorted_candles],
        'volume': [float(c.get('volume', 0)) for c in sorted_candles]
    }
    
    df = pd.DataFrame(data)
    df = df.reset_index(drop=True)
    return df


def _group_trades_by_date(trades, candles_list):
    """Group trades by Year → Month → Day."""
    if not trades or not candles_list:
        return {}
    
    index_to_timestamp = {}
    for idx, candle in enumerate(candles_list):
        if idx < len(candles_list):
            index_to_timestamp[idx] = candle.get('time', 0)
    
    grouped = {}
    
    for trade in trades:
        entry_index = trade.get('entry_index', 0)
        entry_timestamp = index_to_timestamp.get(entry_index, 0)
        
        if entry_timestamp == 0:
            continue
        
        dt = datetime.fromtimestamp(entry_timestamp)
        year = str(dt.year)
        month = dt.strftime('%m')
        day = dt.strftime('%d')
        
        if year not in grouped:
            grouped[year] = {}
        if month not in grouped[year]:
            grouped[year][month] = {}
        if day not in grouped[year][month]:
            grouped[year][month][day] = []
        
        grouped[year][month][day].append(trade)
    
    # Calculate monthly summaries
    for year in grouped:
        for month in grouped[year]:
            month_trades = []
            for day in grouped[year][month]:
                month_trades.extend(grouped[year][month][day])
            
            wins = sum(1 for t in month_trades if t.get('result') == 'WIN')
            losses = sum(1 for t in month_trades if t.get('result') == 'LOSS')
            net_pnl = sum(float(t.get('pnl', 0)) for t in month_trades)
            
            grouped[year][month]['summary'] = {
                'total_trades': len(month_trades),
                'wins': wins,
                'losses': losses,
                'net_pnl': round(net_pnl, 2)
            }
    
    return grouped


def _run_preview_backtest(strategy: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run BacktestEngine on strategy for preview.
    
    Returns:
        Dict with either:
        - Success: {'success': True, 'mode': 'BACKTEST', 'summary': {...}, 'trades': [...], 'monthly_performance': {...}}
        - Error: {'success': False, 'error_code': 'NO_HISTORICAL_DATA', 'message': '...'}
    """
    try:
        strategy_copy = copy.deepcopy(strategy)
        
        symbol = strategy_copy.get('symbol', 'BTCUSD')
        meta = strategy_copy.get('meta', {})
        
        # Get timeframe from multiple possible locations
        timeframe = (
            meta.get('timeframe') or
            strategy_copy.get('userParams', {}).get('timeframe') or
            strategy_copy.get('timeframe') or
            '15MIN'  # Default fallback
        )
        
        # Validate timeframe is present (even if defaulted)
        if not timeframe or (timeframe == '15MIN' and not meta.get('timeframe') and not strategy_copy.get('userParams', {}).get('timeframe')):
            logger.warning(f"Strategy missing explicit timeframe, using default: {timeframe}")
        
        # Ensure timeframe is in meta for consistency
        if not meta.get('timeframe'):
            meta['timeframe'] = timeframe
            strategy_copy['meta'] = meta
        
        # Get lookback_days from strategy or use default based on timeframe
        lookback_days = strategy_copy.get('lookback_days')
        if lookback_days is None:
            lookback_days = get_default_lookback_days(timeframe)
        
        # Fetch historical candles with controlled lookback window
        # Note: fetch_ohlcv now handles UI → Delta mapping and chunked fetching automatically
        end_time = datetime.now()
        end_timestamp = int(end_time.timestamp())
        start_timestamp = int((end_time - timedelta(days=lookback_days)).timestamp())
        
        logger.info(f"Fetching historical candles for preview backtest: symbol={symbol}, timeframe={timeframe}, lookback_days={lookback_days}")
        candles_list = fetch_ohlcv(symbol, timeframe, start_timestamp, end_timestamp, auto_map=True, lookback_days=lookback_days)
        
        if not candles_list:
            # Log detailed error for debugging (backend only) - WARNING, not ERROR
            logger.warning(f"No historical data available for {symbol} {timeframe} - Delta Exchange returned empty response")
            # Return structured error response (broker-agnostic) - DO NOT raise exception
            return {
                "success": False,
                "error": {
                    "code": "NO_HISTORICAL_DATA",
                    "message": "Backtest data is not available for the selected symbol and timeframe. Please try a different timeframe or symbol."
                }
            }
        
        candles_df = _convert_candles_to_dataframe(candles_list)
        
        if len(candles_df) == 0:
            # Log detailed error for debugging (backend only) - WARNING, not ERROR
            logger.warning(f"Empty candles DataFrame for {symbol} {timeframe} after conversion")
            # Return structured error response (broker-agnostic) - DO NOT raise exception
            return {
                "success": False,
                "error": {
                    "code": "NO_HISTORICAL_DATA",
                    "message": "Backtest data is not available for the selected symbol and timeframe. Please try a different timeframe or symbol."
                }
            }
        
        # Pre-backtest safety validation: Calculate required candles
        max_period = _calculate_max_indicator_period(strategy_copy)
        required_candles = max_period * 2  # Require 2x max period for reliable backtest
        
        candle_count = len(candles_df)
        
        logger.info(f"Pre-backtest validation: count={candle_count}, max_period={max_period}, required={required_candles} (max_period * 2)")
        
        if candle_count < required_candles:
            logger.warning(f"Insufficient historical data for {symbol} {timeframe}: {candle_count} candles < {required_candles} required (max indicator period: {max_period})")
            # Return structured error response (broker-agnostic) - DO NOT raise exception
            return {
                "success": False,
                "error": {
                    "code": "INSUFFICIENT_DATA",
                    "message": "Not enough historical data to run this strategy. Try a shorter timeframe or reduce indicators."
                }
            }
        
        # Run BacktestEngine
        try:
            engine = BacktestEngine(strategy_copy)
            results = engine.run(candles_df)
        except Exception as e:
            # BacktestEngine error - log but return structured error response (don't crash)
            logger.error(f"BacktestEngine error for {symbol} {timeframe}: {e}", exc_info=True)
            return {
                "success": False,
                "error": {
                    "code": "BACKTEST_ENGINE_ERROR",
                    "message": "An error occurred while running the backtest. Please try again or contact support."
                }
            }
        
        # Group trades by date
        monthly_perf = _group_trades_by_date(results.get('trades', []), candles_list)
        
        results['mode'] = 'BACKTEST'
        results['monthly_performance'] = monthly_perf
        results['success'] = True  # Mark as successful
        
        return results
        
    except Exception as e:
        # Catch any unexpected errors and return structured response (don't crash server)
        logger.error(f"Unexpected error running preview backtest: {e}", exc_info=True)
        return {
            "success": False,
            "error": {
                "code": "UNEXPECTED_ERROR",
                "message": "An unexpected error occurred. Please try again or contact support."
            }
        }


def _apply_preview_brokerage(performance: Dict[str, Any], backtest_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Apply brokerage and capital calculations to performance results."""
    if not backtest_settings:
        return performance
    
    initial_capital = float(backtest_settings.get('initialCapital', 100000))
    leverage = float(backtest_settings.get('leverage', 1))
    capital_per_trade_pct = float(backtest_settings.get('capitalPerTrade', 10)) / 100.0
    
    maker_rate = 0.0002  # 0.02%
    taker_rate = 0.0005  # 0.05%
    
    capital_per_trade = initial_capital * capital_per_trade_pct
    
    transformed_trades = []
    total_brokerage_maker = 0.0
    total_brokerage_taker = 0.0
    gross_pnl_currency = 0.0
    
    for trade in performance.get('trades', []):
        entry_price = float(trade.get('entry_price', 0))
        exit_price = float(trade.get('exit_price', 0))
        pnl_points = float(trade.get('pnl', 0))
        
        leveraged_capital = capital_per_trade * leverage
        position_size = leveraged_capital / entry_price if entry_price > 0 else 0
        
        gross_pnl_trade = pnl_points * position_size
        gross_pnl_currency += gross_pnl_trade
        
        entry_brokerage_maker = leveraged_capital * maker_rate
        exit_brokerage_maker = position_size * exit_price * maker_rate
        trade_brokerage_maker = entry_brokerage_maker + exit_brokerage_maker
        total_brokerage_maker += trade_brokerage_maker
        
        entry_brokerage_taker = leveraged_capital * taker_rate
        exit_brokerage_taker = position_size * exit_price * taker_rate
        trade_brokerage_taker = entry_brokerage_taker + exit_brokerage_taker
        total_brokerage_taker += trade_brokerage_taker
        
        net_pnl_maker = gross_pnl_trade - trade_brokerage_maker
        net_pnl_taker = gross_pnl_trade - trade_brokerage_taker
        
        transformed_trade = trade.copy()
        transformed_trade['pnl_points'] = pnl_points
        transformed_trade['gross_pnl_currency'] = round(gross_pnl_trade, 2)
        transformed_trade['brokerage_maker'] = round(trade_brokerage_maker, 2)
        transformed_trade['brokerage_taker'] = round(trade_brokerage_taker, 2)
        transformed_trade['net_pnl_maker'] = round(net_pnl_maker, 2)
        transformed_trade['net_pnl_taker'] = round(net_pnl_taker, 2)
        transformed_trade['position_size'] = round(position_size, 4)
        
        transformed_trades.append(transformed_trade)
    
    summary = performance.get('summary', {}).copy()
    
    net_pnl_currency_maker = gross_pnl_currency - total_brokerage_maker
    net_pnl_currency_taker = gross_pnl_currency - total_brokerage_taker
    
    summary['gross_pnl_currency'] = round(gross_pnl_currency, 2)
    summary['net_pnl_currency_maker'] = round(net_pnl_currency_maker, 2)
    summary['net_pnl_currency_taker'] = round(net_pnl_currency_taker, 2)
    summary['total_brokerage_maker'] = round(total_brokerage_maker, 2)
    summary['total_brokerage_taker'] = round(total_brokerage_taker, 2)
    summary['net_pnl_points'] = summary.get('net_pnl', 0)
    summary['initial_capital'] = initial_capital
    summary['final_capital_maker'] = round(initial_capital + net_pnl_currency_maker, 2)
    summary['final_capital_taker'] = round(initial_capital + net_pnl_currency_taker, 2)
    summary['return_pct_maker'] = round((net_pnl_currency_maker / initial_capital) * 100, 2) if initial_capital > 0 else 0
    summary['return_pct_taker'] = round((net_pnl_currency_taker / initial_capital) * 100, 2) if initial_capital > 0 else 0
    
    return {
        'summary': summary,
        'trades': transformed_trades,
        'monthly_performance': performance.get('monthly_performance')
    }


class AutoSaveStrategyRequest(BaseModel):
    """Request model for auto-saving a strategy"""
    strategy: Dict[str, Any] = Field(..., description="Full strategy JSON payload")


class AutoSaveStrategyResponse(BaseModel):
    """Response model for auto-saving a strategy"""
    success: bool
    strategy_id: int
    strategy_code: str
    version: int
    message: str


@router.post("/ai-strategy/save/", response_model=AutoSaveStrategyResponse)
def auto_save_strategy(
    request: AutoSaveStrategyRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Auto-save a strategy silently (no user interaction required).
    
    This endpoint is called automatically after strategy generation.
    It generates a temp_strategy_id and name automatically.
    
    FLOW:
    1. Extract Authorization token
    2. Generate temp_strategy_id (TEMP-{timestamp})
    3. Generate strategy name from strategy data (or use default)
    4. Call save_strategy service
    5. Return strategy_id, strategy_code, version
    
    Args:
        request: AutoSaveStrategyRequest with strategy payload
        authorization: Authorization header (Bearer token)
        db: Database session
    
    Returns:
        AutoSaveStrategyResponse with strategy_id, strategy_code, version
    
    Raises:
        HTTPException: If validation fails or save fails
    """
    try:
        # Validate authorization header - silent failure for auto-save
        if not authorization:
            logger.warning("Auto-save skipped: Authorization header missing")
            # Return controlled response (not HTTPException) - silent failure
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Strategy auto-save skipped (user not authenticated)."
                    }
                }
            )
        
        # Generate temp_strategy_id automatically
        temp_strategy_id = f"TEMP-{int(datetime.now().timestamp() * 1000)}"
        
        # Generate strategy name from strategy data
        strategy = request.strategy
        symbol = strategy.get('symbol') or strategy.get('userParams', {}).get('symbol') or 'UNKNOWN'
        timeframe = strategy.get('timeframe') or strategy.get('userParams', {}).get('timeframe') or ''
        strategy_type = strategy.get('strategy_type') or strategy.get('condition', {}).get('type') or 'Strategy'
        
        # Create a descriptive name
        name = f"{symbol} {timeframe} {strategy_type}".strip()
        if not name or name == 'Strategy':
            name = f"Strategy {symbol} {timeframe}".strip() or "Auto-saved Strategy"
        
        # Save strategy using existing service
        result = save_strategy(
            db=db,
            temp_strategy_id=temp_strategy_id,
            name=name,
            strategy_payload=strategy,
            authorization=authorization,
            description=None,  # No description for auto-save
            backtest_snapshot=None  # No backtest snapshot for auto-save
        )
        
        logger.info(f"Strategy auto-saved successfully: strategy_id={result['strategy_id']}, strategy_code={result['strategy_code']}")
        
        return AutoSaveStrategyResponse(
            success=True,
            strategy_id=result["strategy_id"],
            strategy_code=result["strategy_code"],
            version=result["version"],
            message="Strategy auto-saved successfully"
        )
        
    except ValueError as e:
        # Validation errors
        logger.warning(f"Validation error auto-saving strategy: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # All other errors (including auth backend unavailable, DB errors, etc.)
        logger.error(f"Error auto-saving strategy: {e}", exc_info=True)
        if hasattr(e, 'status_code'):
            # Re-raise HTTPException as-is
            raise e
        # Convert other exceptions to HTTPException
        raise HTTPException(status_code=500, detail=f"Failed to auto-save strategy: {str(e)}")

