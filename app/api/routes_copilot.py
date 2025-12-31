"""
Copilot API Routes - Conversational Strategy Builder

This module implements the Copilot-first flow:
1. Copilot Mode: Conversational strategy description (no JSON generation)
2. Backtest Mode: After confirmation, convert to JSON and run backtest
3. Deploy Mode: Save and deploy strategy

CRITICAL: This is ADDED in parallel to existing /ai-strategy/generate endpoint.
Existing endpoints remain untouched.
"""
from fastapi import APIRouter, HTTPException, Header, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
import logging
import json

from app.database import get_db
from app.services.copilot_service import (
    process_copilot_message,
    save_copilot_session,
    load_copilot_session,
    delete_copilot_session,
    create_copilot_session
)
from app.services.openai_service import generate_strategy
# Note: We'll use BacktestEngine directly for Copilot flow to match existing pattern
from app.services.prompt_builder import build_prompt
from app.services.credit_service import (
    check_credits_available,
    deduct_credits
)
from app.services.user_sync_service import get_or_sync_user
from app.engine.backtest_engine import BacktestEngine
from app.feed.delta_history import fetch_ohlcv, get_default_lookback_days
from app.services.strategy_save_service import save_strategy
from datetime import datetime, timedelta
import copy
import pandas as pd

logger = logging.getLogger(__name__)

router = APIRouter()


class CopilotMessageRequest(BaseModel):
    """Request model for Copilot message"""
    session_id: Optional[str] = Field(None, description="Session ID (auto-generated if not provided)")
    message: str = Field(..., min_length=1, description="User's strategy description or question")


class CopilotMessageResponse(BaseModel):
    """Response model for Copilot message"""
    success: bool
    session_id: str
    response: str
    is_ready: bool
    missing_details: List[str]
    summary: Optional[str] = None


class CopilotConfirmRequest(BaseModel):
    """Request model for Copilot confirmation"""
    session_id: str = Field(..., description="Session ID")
    symbol: str = Field(..., description="Trading symbol (e.g., BTCUSD)")
    timeframe: str = Field(..., description="Trading timeframe (e.g., 15MIN, 1H)")
    chart_type: Optional[str] = Field("candles", description="Chart type (candles or heikin_ashi)")


class CopilotConfirmResponse(BaseModel):
    """Response model for Copilot confirmation"""
    success: bool
    strategy: Optional[Dict[str, Any]] = None
    message: str
    strategy_id: Optional[int] = None


@router.post("/copilot/message", response_model=CopilotMessageResponse)
def copilot_message(
    request: CopilotMessageRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Process a message in Copilot mode (Step 1).
    
    This is CONVERSATIONAL ONLY:
    - Accepts ANY plain text (strategy idea, indicator code, partial logic)
    - Does NOT generate JSON
    - Does NOT validate indicators
    - Does NOT ask for symbol or timeframe
    - Summarizes what user said
    - Asks only what is missing
    
    Args:
        request: CopilotMessageRequest with session_id and message
        authorization: Authorization header (optional for Copilot mode)
        db: Database session
    
    Returns:
        CopilotMessageResponse with conversational response
    """
    try:
        # Get or create session
        session_id = request.session_id
        if not session_id:
            session_id = create_copilot_session()
        
        # Load conversation history
        conversation_history = load_copilot_session(session_id) or []
        
        # Process message
        result = process_copilot_message(
            session_id=session_id,
            user_message=request.message,
            conversation_history=conversation_history
        )
        
        # Update conversation history
        conversation_history.append({"role": "user", "content": request.message})
        conversation_history.append({"role": "assistant", "content": result["response"]})
        
        # Save updated session
        save_copilot_session(session_id, conversation_history)
        
        return CopilotMessageResponse(
            success=True,
            session_id=session_id,
            response=result["response"],
            is_ready=result["is_ready"],
            missing_details=result["missing_details"],
            summary=result["summary"]
        )
        
    except Exception as e:
        logger.error(f"Error in copilot_message: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong while processing your message. Please try again."
        )


@router.post("/copilot/confirm", response_model=CopilotConfirmResponse)
def copilot_confirm(
    request: CopilotConfirmRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Confirm strategy and move to Compiler mode (Step 2).
    
    After user confirmation:
    1. Ask for symbol and timeframe (from request)
    2. Convert confirmed understanding into Unified Strategy JSON
    3. Run existing BacktestEngine
    4. Apply all validations internally (not user-facing)
    
    Args:
        request: CopilotConfirmRequest with session_id, symbol, timeframe
        authorization: Authorization header (required for backtest)
        db: Database session
    
    Returns:
        CopilotConfirmResponse with generated strategy and backtest results
    """
    try:
        # Validate authorization
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # Sync user
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate user"
            )
        
        # Load conversation history
        conversation_history = load_copilot_session(request.session_id)
        if not conversation_history:
            raise HTTPException(
                status_code=400,
                detail="Session not found. Please start a new conversation."
            )
        
        # CREDIT CHECK AND DEDUCTION
        is_available, available_credits, required_credits = check_credits_available(
            db, user.external_user_id, 'ai_strategy_generate'
        )
        
        if not is_available:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient credits. Available: {available_credits}, Required: {required_credits}. Please purchase more credits to continue."
            )
        
        # Deduct credits
        success, error_msg = deduct_credits(
            db, user.external_user_id, 'ai_strategy_generate',
            reason="Copilot strategy generation",
            reference_id=None
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Failed to process credits: {error_msg}"
            )
        
        logger.info(f"Copilot confirm – credit deducted: user_id={user.id}, credits={required_credits}")
        
        # Build prompt from conversation history
        # Extract all user messages as strategy description
        user_messages = [
            msg["content"] for msg in conversation_history
            if msg.get("role") == "user"
        ]
        strategy_description = "\n".join(user_messages)
        
        # Build complete prompt with symbol and timeframe
        try:
            final_prompt = build_prompt(
                strategy_description=strategy_description,
                symbol=request.symbol,
                timeframe=request.timeframe,
                chart_type=request.chart_type,
                take_profit=None,  # Let OpenAI extract from conversation
                stop_loss=None,   # Let OpenAI extract from conversation
                trailing_stop=None,
                trading_session=None,
                max_trades_per_day=None,
                current_price=None,
                market_context=None
            )
        except ValueError as e:
            logger.error(f"PromptBuilder validation failed: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        
        # Generate strategy using existing OpenAI compiler
        try:
            logger.info("🤖 Calling OpenAI compiler with confirmed strategy")
            strategy = generate_strategy(user_prompt=final_prompt)
            
            if not strategy:
                logger.error("❌ OpenAI returned None - strategy generation failed")
                raise HTTPException(
                    status_code=500,
                    detail="Something went wrong while preparing the strategy. Please review your strategy and try again."
                )
            
            logger.info(f"✅ Strategy generated successfully: {strategy.get('strategy_type')}")
            
        except ValueError as e:
            # Validation errors - show human-readable message
            error_msg = str(e)
            logger.error(f"❌ Strategy validation error: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail="Something went wrong while preparing the strategy. Please review your strategy and try again."
            )
        except Exception as e:
            logger.error(f"Error generating strategy: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Something went wrong while preparing the strategy. Please review your strategy and try again."
            )
        
        # Clean up session (optional - you might want to keep it for reference)
        # delete_copilot_session(request.session_id)
        
        return CopilotConfirmResponse(
            success=True,
            strategy=strategy,
            message="Strategy generated successfully. Ready for backtest.",
            strategy_id=None  # No auto-save in Copilot flow
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in copilot_confirm: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong while preparing the strategy. Please review your strategy and try again."
        )


class CopilotBacktestRequest(BaseModel):
    """Request model for Copilot backtest"""
    strategy: Dict[str, Any] = Field(..., description="Generated strategy JSON")


@router.post("/copilot/backtest")
def copilot_backtest(
    request: CopilotBacktestRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Run backtest for a strategy from Copilot flow (Step 2 continuation).
    
    This reuses the existing backtest infrastructure.
    All validations are internal (not user-facing).
    
    Args:
        strategy: Generated strategy JSON
        authorization: Authorization header
        db: Database session
    
    Returns:
        Backtest results
    """
    try:
        # Validate authorization
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # Sync user
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate user"
            )
        
        # CREDIT CHECK AND DEDUCTION
        is_available, available_credits, required_credits = check_credits_available(
            db, user.external_user_id, 'backtest'
        )
        
        if not is_available:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient credits. Available: {available_credits}, Required: {required_credits}."
            )
        
        # Deduct credits
        success, error_msg = deduct_credits(
            db, user.external_user_id, 'backtest',
            reason="Copilot backtest execution",
            reference_id=None
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Failed to process credits: {error_msg}"
            )
        
        # Get strategy from request
        strategy = request.strategy
        
        # Validate strategy structure
        if not strategy.get('symbol'):
            raise HTTPException(status_code=400, detail="Strategy must have a 'symbol' field")
        
        if not strategy.get('logic'):
            raise HTTPException(status_code=400, detail="Strategy must have a 'logic' field")
        
        if not strategy.get('risk'):
            raise HTTPException(status_code=400, detail="Strategy must have a 'risk' field")
        
        # Run backtest using existing BacktestEngine (same as routes_ai_strategy.py)
        # This reuses the existing backtest infrastructure
        try:
            strategy_copy = copy.deepcopy(strategy)
            
            symbol = strategy_copy.get('symbol', 'BTCUSD')
            meta = strategy_copy.get('meta', {})
            
            # Get timeframe from meta
            timeframe = (
                meta.get('timeframe') or
                strategy_copy.get('timeframe') or
                '15MIN'  # Default fallback
            )
            
            # Ensure timeframe is in meta
            if not meta.get('timeframe'):
                meta['timeframe'] = timeframe
                strategy_copy['meta'] = meta
            
            # Get lookback_days
            from app.feed.delta_history import get_default_lookback_days
            lookback_days = strategy_copy.get('lookback_days')
            if lookback_days is None:
                lookback_days = get_default_lookback_days(timeframe)
            
            # Fetch historical candles
            end_time = datetime.now()
            end_timestamp = int(end_time.timestamp())
            start_timestamp = int((end_time - timedelta(days=lookback_days)).timestamp())
            
            logger.info(f"Fetching historical candles for copilot backtest: symbol={symbol}, timeframe={timeframe}")
            candles_list = fetch_ohlcv(symbol, timeframe, start_timestamp, end_timestamp, auto_map=True, lookback_days=lookback_days)
            
            if not candles_list:
                raise HTTPException(
                    status_code=500,
                    detail="Something went wrong while running the backtest. Please try again."
                )
            
            # Convert to DataFrame
            sorted_candles = sorted(candles_list, key=lambda c: c.get('time', 0))
            candles_df = pd.DataFrame({
                'open': [float(c['open']) for c in sorted_candles],
                'high': [float(c['high']) for c in sorted_candles],
                'low': [float(c['low']) for c in sorted_candles],
                'close': [float(c['close']) for c in sorted_candles],
                'volume': [float(c.get('volume', 0)) for c in sorted_candles]
            })
            
            if len(candles_df) == 0:
                raise HTTPException(
                    status_code=500,
                    detail="Something went wrong while running the backtest. Please try again."
                )
            
            # Run BacktestEngine
            engine = BacktestEngine(strategy_copy)
            backtest_results = engine.run(candles_df)
            
            if not backtest_results:
                raise HTTPException(
                    status_code=500,
                    detail="Something went wrong while running the backtest. Please try again."
                )
            
            return {
                "success": True,
                "results": backtest_results,
                "message": "Backtest completed successfully"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Backtest error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Something went wrong while running the backtest. Please try again."
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in copilot_backtest: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong while running the backtest. Please try again."
        )


@router.delete("/copilot/session/{session_id}")
def delete_session(session_id: str):
    """
    Delete a Copilot session.
    
    Args:
        session_id: Session ID to delete
    
    Returns:
        Success message
    """
    try:
        deleted = delete_copilot_session(session_id)
        if deleted:
            return {"success": True, "message": "Session deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete session")

