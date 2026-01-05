"""
Secure AI Strategy Generation API
- Production-safe
- Schema validated
- No executable code
"""
from fastapi import APIRouter, HTTPException, status, Header
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging
from core.services.secure_strategy_service import generate_secure_strategy
from common.redis import redis_client
from core.services.credits_service import consume_credits, check_credits_available, get_user_id_from_header
import json

logger = logging.getLogger(__name__)

router = APIRouter()

class SecureStrategyRequest(BaseModel):
    """Request model for secure strategy generation"""
    symbol: str = Field(..., description="Trading symbol (e.g., BTCUSD)", min_length=1, max_length=20)
    description: str = Field(..., description="Natural language strategy description", min_length=10, max_length=2000)
    market_context: Optional[str] = Field(default=None, description="Optional market context (trend, volatility, etc.)", max_length=500)

class SecureStrategyResponse(BaseModel):
    """Response model for secure strategy generation"""
    success: bool
    strategy: Dict[str, Any]
    suggestions: List[str]
    meta: Dict[str, Any]

@router.post("/ai/generate-strategy", response_model=SecureStrategyResponse)
def generate_secure_strategy_api(request: SecureStrategyRequest, authorization: Optional[str] = Header(None)):
    """
    Generate a secure, structured trading strategy from natural language.
    
    This endpoint:
    - Accepts free-text strategy descriptions
    - Uses controlled OpenAI prompts (server-side only)
    - Validates output against strict schema
    - Never returns executable code
    - Only allows whitelisted indicators and operators
    - Saves strategy to Redis
    
    Example requests:
    - {"symbol": "BTCUSD", "description": "EMA 9 cross above 21 EMA buy and EMA 9 cross below 21 EMA sell, TP 2% SL 1%"}
    - {"symbol": "ETHUSD", "description": "Buy when price goes above 3000, sell when price drops below 2800"}
    - {"symbol": "BTCUSD", "description": "RSI above 70 sell, RSI below 30 buy, TP 3% SL 1.5%"}
    
    Returns:
        SecureStrategyResponse with validated strategy, suggestions, and metadata
    """
    try:
        # Validate input
        if not request.symbol or not request.symbol.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Symbol is required"
            )
        
        if not request.description or len(request.description.strip()) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Description must be at least 10 characters"
            )
        
        if len(request.description) > 2000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Description must be less than 2000 characters"
            )
        
        # Sanitize symbol (uppercase, alphanumeric only)
        symbol = request.symbol.strip().upper()
        if not symbol.replace('USD', '').replace('USDT', '').isalnum():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid symbol format"
            )
        
        # Check and consume credits
        user_id = get_user_id_from_header(authorization)
        credit_check = check_credits_available(user_id, 'ai_generate')
        
        if not credit_check['has_credits']:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient credits. {credit_check['message']}. Please purchase more credits to continue."
            )
        
        # Consume credits before generating
        credit_result = consume_credits(user_id, 'ai_generate')
        if not credit_result['success']:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Failed to process credits: {credit_result['message']}"
            )
        
        logger.info(f"Generating secure strategy for {symbol}: {request.description[:100]}... (Credits remaining: {credit_result['credits_remaining']})")
        
        # Generate strategy using secure service with market context
        result = generate_secure_strategy(
            description=request.description.strip(),
            symbol=symbol,
            market_context=request.market_context.strip() if request.market_context else None
        )
        
        strategy = result['strategy']
        strategy_id = strategy.get('strategy_id')
        
        if not strategy_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate strategy ID"
            )
        
        # Save to Redis
        try:
            redis_key = f"STRATEGY:{strategy_id}"
            strategy_data = {
                **strategy,
                'raw_description': request.description.strip(),
                'saved_at': result['meta']['generated_at']
            }
            redis_client.setex(
                redis_key,
                86400 * 30,  # 30 days TTL
                json.dumps(strategy_data)
            )
            logger.info(f"Strategy saved to Redis: {redis_key}")
        except Exception as redis_error:
            logger.error(f"Failed to save strategy to Redis: {redis_error}")
            # Don't fail the request if Redis save fails
            # Strategy is still returned to user
        
        return SecureStrategyResponse(
            success=True,
            strategy=strategy,
            suggestions=result.get('suggestions', []),
            meta=result.get('meta', {})
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Strategy validation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error generating secure strategy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@router.get("/ai/strategy/{strategy_id}")
def get_strategy_by_id(strategy_id: str):
    """
    Retrieve a saved strategy by ID from Redis
    
    Args:
        strategy_id: UUID of the strategy
    
    Returns:
        Strategy data if found
    """
    try:
        redis_key = f"STRATEGY:{strategy_id}"
        strategy_data = redis_client.get(redis_key)
        
        if not strategy_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy not found: {strategy_id}"
            )
        
        strategy = json.loads(strategy_data)
        return {
            "success": True,
            "strategy": strategy
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving strategy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

