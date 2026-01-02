"""
Credits Service
Manages user credits for AI and backtesting operations
"""
import logging
from typing import Optional, Dict, Any
from common.redis import redis_client


def get_user_id_from_header(authorization: Optional[str]) -> str:
    """
    Extract user ID from authorization header
    In production, this should decode JWT token or session
    For now, we'll use a simple header format: "Bearer user_id" or just "user_id"
    
    Args:
        authorization: Authorization header value
    
    Returns:
        str: User ID
    """
    if not authorization:
        # Default to "anonymous" for testing - in production, require auth
        return "anonymous"
    
    # Simple extraction - in production, decode JWT token
    # Format: "Bearer user_id" or "user_id"
    parts = authorization.split()
    if len(parts) >= 2:
        user_id = parts[-1]  # Get last part (user_id)
    else:
        user_id = authorization
    
    if not user_id or user_id == "Bearer":
        return "anonymous"
    
    return user_id

logger = logging.getLogger(__name__)

# Credit costs for different actions
CREDIT_COSTS = {
    'ai_generate': 2,
    'ai_improve': 1,
    'backtest': 1,
}

# Default free credits for new users
DEFAULT_FREE_CREDITS = 10


def get_user_credits(user_id: str) -> int:
    """
    Get current credit balance for a user
    
    Args:
        user_id: User ID (string)
    
    Returns:
        int: Current credit balance (0 if not found)
    """
    try:
        credit_key = f"CREDITS:{user_id}"
        credits_str = redis_client.get(credit_key)
        
        if credits_str is None:
            # User doesn't have credits yet - initialize with default
            logger.info(f"User {user_id} has no credits record. Initializing with {DEFAULT_FREE_CREDITS} free credits.")
            initialize_user_credits(user_id)
            return DEFAULT_FREE_CREDITS
        
        credits = int(credits_str)
        return max(0, credits)  # Ensure non-negative
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing credits for user {user_id}: {e}")
        return 0
    except Exception as e:
        logger.error(f"Error getting credits for user {user_id}: {e}", exc_info=True)
        return 0


def initialize_user_credits(user_id: str, initial_credits: int = DEFAULT_FREE_CREDITS) -> bool:
    """
    Initialize credits for a new user
    
    Args:
        user_id: User ID (string)
        initial_credits: Initial credit amount (default: 10)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        credit_key = f"CREDITS:{user_id}"
        
        # Check if user already has credits
        existing = redis_client.get(credit_key)
        if existing is not None:
            logger.info(f"User {user_id} already has credits: {existing}")
            return True
        
        # Set initial credits (no expiration - credits persist)
        redis_client.set(credit_key, str(initial_credits))
        logger.info(f"Initialized {initial_credits} credits for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error initializing credits for user {user_id}: {e}", exc_info=True)
        return False


def consume_credits(user_id: str, action_type: str, amount: Optional[int] = None) -> Dict[str, Any]:
    """
    Consume credits for a user action
    
    Args:
        user_id: User ID (string)
        action_type: Type of action ('ai_generate', 'ai_improve', 'backtest')
        amount: Optional custom amount (uses CREDIT_COSTS if not provided)
    
    Returns:
        dict: {
            'success': bool,
            'credits_remaining': int,
            'credits_consumed': int,
            'message': str
        }
    """
    try:
        # Get credit cost
        if amount is not None:
            credit_cost = amount
        elif action_type in CREDIT_COSTS:
            credit_cost = CREDIT_COSTS[action_type]
        else:
            logger.error(f"Unknown action type: {action_type}")
            return {
                'success': False,
                'credits_remaining': get_user_credits(user_id),
                'credits_consumed': 0,
                'message': f'Unknown action type: {action_type}'
            }
        
        # Get current credits
        current_credits = get_user_credits(user_id)
        
        # Check if user has enough credits
        if current_credits < credit_cost:
            return {
                'success': False,
                'credits_remaining': current_credits,
                'credits_consumed': 0,
                'message': f'Insufficient credits. Required: {credit_cost}, Available: {current_credits}'
            }
        
        # Deduct credits atomically
        credit_key = f"CREDITS:{user_id}"
        new_balance = current_credits - credit_cost
        
        # Use Redis transaction for atomicity
        pipe = redis_client.pipeline()
        pipe.set(credit_key, str(new_balance))
        pipe.execute()
        
        logger.info(f"Consumed {credit_cost} credits for user {user_id} ({action_type}). Remaining: {new_balance}")
        
        return {
            'success': True,
            'credits_remaining': new_balance,
            'credits_consumed': credit_cost,
            'message': f'Successfully consumed {credit_cost} credits'
        }
        
    except Exception as e:
        logger.error(f"Error consuming credits for user {user_id}: {e}", exc_info=True)
        return {
            'success': False,
            'credits_remaining': get_user_credits(user_id),
            'credits_consumed': 0,
            'message': f'Error processing credits: {str(e)}'
        }


def add_credits(user_id: str, amount: int) -> Dict[str, Any]:
    """
    Add credits to a user's account (for future payment integration)
    
    Args:
        user_id: User ID (string)
        amount: Amount of credits to add
    
    Returns:
        dict: {
            'success': bool,
            'credits_remaining': int,
            'credits_added': int,
            'message': str
        }
    """
    try:
        if amount <= 0:
            return {
                'success': False,
                'credits_remaining': get_user_credits(user_id),
                'credits_added': 0,
                'message': 'Credit amount must be positive'
            }
        
        # Get current credits
        current_credits = get_user_credits(user_id)
        
        # Add credits
        credit_key = f"CREDITS:{user_id}"
        new_balance = current_credits + amount
        
        redis_client.set(credit_key, str(new_balance))
        
        logger.info(f"Added {amount} credits to user {user_id}. New balance: {new_balance}")
        
        return {
            'success': True,
            'credits_remaining': new_balance,
            'credits_added': amount,
            'message': f'Successfully added {amount} credits'
        }
        
    except Exception as e:
        logger.error(f"Error adding credits for user {user_id}: {e}", exc_info=True)
        return {
            'success': False,
            'credits_remaining': get_user_credits(user_id),
            'credits_added': 0,
            'message': f'Error adding credits: {str(e)}'
        }


def check_credits_available(user_id: str, action_type: str) -> Dict[str, Any]:
    """
    Check if user has enough credits for an action (without consuming)
    
    Args:
        user_id: User ID (string)
        action_type: Type of action ('ai_generate', 'ai_improve', 'backtest')
    
    Returns:
        dict: {
            'has_credits': bool,
            'credits_required': int,
            'credits_available': int,
            'message': str
        }
    """
    try:
        credit_cost = CREDIT_COSTS.get(action_type, 0)
        if credit_cost == 0:
            return {
                'has_credits': False,
                'credits_required': 0,
                'credits_available': get_user_credits(user_id),
                'message': f'Unknown action type: {action_type}'
            }
        
        current_credits = get_user_credits(user_id)
        has_credits = current_credits >= credit_cost
        
        return {
            'has_credits': has_credits,
            'credits_required': credit_cost,
            'credits_available': current_credits,
            'message': f'Credits available: {current_credits}, Required: {credit_cost}' if has_credits else f'Insufficient credits. Required: {credit_cost}, Available: {current_credits}'
        }
        
    except Exception as e:
        logger.error(f"Error checking credits for user {user_id}: {e}", exc_info=True)
        return {
            'has_credits': False,
            'credits_required': CREDIT_COSTS.get(action_type, 0),
            'credits_available': 0,
            'message': f'Error checking credits: {str(e)}'
        }

