"""
Credits API Routes
Manages user credits for AI and backtesting operations
"""
from fastapi import APIRouter, HTTPException, status, Header
from pydantic import BaseModel, Field
from typing import Optional
import logging
from app.services.credits_service import (
    get_user_credits,
    consume_credits,
    add_credits,
    check_credits_available,
    initialize_user_credits,
    CREDIT_COSTS,
    DEFAULT_FREE_CREDITS
)

logger = logging.getLogger(__name__)

router = APIRouter()


class ConsumeCreditRequest(BaseModel):
    """Request model for consuming credits"""
    action_type: str = Field(..., description="Action type: 'ai_generate', 'ai_improve', or 'backtest'")
    amount: Optional[int] = Field(None, description="Optional custom credit amount (uses default cost if not provided)")


class AddCreditRequest(BaseModel):
    """Request model for adding credits (for admin/future payment integration)"""
    amount: int = Field(..., gt=0, description="Amount of credits to add")


def get_user_id_from_header(authorization: Optional[str] = Header(None)) -> str:
    """
    Extract user ID from authorization header
    In production, this should decode JWT token or session
    For now, we'll use a simple header format: "Bearer user_id"
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    
    # Simple extraction - in production, decode JWT token
    # Format: "Bearer user_id" or "user_id"
    parts = authorization.split()
    if len(parts) >= 2:
        user_id = parts[-1]  # Get last part (user_id)
    else:
        user_id = authorization
    
    if not user_id or user_id == "Bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )
    
    return user_id


@router.get("/user/credits")
def get_credits(authorization: Optional[str] = Header(None)):
    """
    Get current credit balance for the authenticated user
    
    Returns:
        dict: {
            "success": bool,
            "credits": int,
            "message": str
        }
    """
    try:
        user_id = get_user_id_from_header(authorization)
        
        credits = get_user_credits(user_id)
        
        return {
            "success": True,
            "credits": credits,
            "message": f"Current credit balance: {credits}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/user/consume-credit")
def consume_credit(request: ConsumeCreditRequest, authorization: Optional[str] = Header(None)):
    """
    Consume credits for an action (AI generate, improve, or backtest)
    
    Args:
        request: ConsumeCreditRequest with action_type and optional amount
        authorization: Authorization header with user ID
    
    Returns:
        dict: {
            "success": bool,
            "credits_remaining": int,
            "credits_consumed": int,
            "message": str
        }
    """
    try:
        user_id = get_user_id_from_header(authorization)
        
        # Validate action type
        if request.action_type not in CREDIT_COSTS and request.amount is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action type: {request.action_type}. Allowed: {', '.join(CREDIT_COSTS.keys())}"
            )
        
        # Consume credits
        result = consume_credits(user_id, request.action_type, request.amount)
        
        if not result['success']:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,  # 402 Payment Required
                detail=result['message']
            )
        
        return {
            "success": True,
            "credits_remaining": result['credits_remaining'],
            "credits_consumed": result['credits_consumed'],
            "message": result['message']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error consuming credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/user/check-credits")
def check_credits(request: ConsumeCreditRequest, authorization: Optional[str] = Header(None)):
    """
    Check if user has enough credits for an action (without consuming)
    
    Args:
        request: ConsumeCreditRequest with action_type
        authorization: Authorization header with user ID
    
    Returns:
        dict: {
            "has_credits": bool,
            "credits_required": int,
            "credits_available": int,
            "message": str
        }
    """
    try:
        user_id = get_user_id_from_header(authorization)
        
        # Validate action type
        if request.action_type not in CREDIT_COSTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action type: {request.action_type}. Allowed: {', '.join(CREDIT_COSTS.keys())}"
            )
        
        result = check_credits_available(user_id, request.action_type)
        
        return {
            "has_credits": result['has_credits'],
            "credits_required": result['credits_required'],
            "credits_available": result['credits_available'],
            "message": result['message']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/user/initialize-credits")
def initialize_credits(authorization: Optional[str] = Header(None)):
    """
    Initialize credits for a new user (called on user registration)
    Assigns default free credits (10)
    
    Args:
        authorization: Authorization header with user ID
    
    Returns:
        dict: {
            "success": bool,
            "credits": int,
            "message": str
        }
    """
    try:
        user_id = get_user_id_from_header(authorization)
        
        # Initialize credits (only if user doesn't have credits yet)
        success = initialize_user_credits(user_id, DEFAULT_FREE_CREDITS)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initialize credits"
            )
        
        credits = get_user_credits(user_id)
        
        return {
            "success": True,
            "credits": credits,
            "message": f"Initialized {DEFAULT_FREE_CREDITS} free credits"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initializing credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/admin/add-credits")
def admin_add_credits(user_id: str, request: AddCreditRequest):
    """
    Admin endpoint to add credits to a user account
    (For future payment integration or admin operations)
    
    Args:
        user_id: User ID to add credits to
        request: AddCreditRequest with amount
    
    Returns:
        dict: {
            "success": bool,
            "credits_remaining": int,
            "credits_added": int,
            "message": str
        }
    """
    try:
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User ID is required"
            )
        
        result = add_credits(user_id, request.amount)
        
        if not result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result['message']
            )
        
        return {
            "success": True,
            "credits_remaining": result['credits_remaining'],
            "credits_added": result['credits_added'],
            "message": result['message']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

