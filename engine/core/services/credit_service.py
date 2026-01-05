"""
Credit Service
Handles all credit-related operations: checking, deducting, adding credits.
All credit rules are DB-driven (no hardcoding).
"""
import logging
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from models import (
    CreditConfig, UserCredits, CreditTransaction, StrategyUsage,
    User
)
from datetime import datetime

logger = logging.getLogger(__name__)


def get_credit_cost(db: Session, action_key: str) -> int:
    """
    Get credit cost for an action from credit_config table.
    
    Args:
        db: Database session
        action_key: Action identifier (e.g., 'ai_strategy_generate')
    
    Returns:
        int: Credit cost for the action, or 0 if not found or inactive
    
    Raises:
        ValueError: If action_key is required but not found
    """
    config = db.query(CreditConfig).filter(
        CreditConfig.action_key == action_key,
        CreditConfig.is_active == True
    ).first()
    
    if not config:
        logger.warning(f"Credit config not found for action_key: {action_key}")
        return 0
    
    return config.credit_cost


def get_default_free_credits(db: Session) -> int:
    """
    Get default free credits for new users from credit_config.
    
    Args:
        db: Database session
    
    Returns:
        int: Default free credits (default: 10)
    """
    credits = get_credit_cost(db, 'default_free_credit')
    return credits if credits > 0 else 10  # Fallback to 10 if not configured


def get_rupee_to_credit_ratio(db: Session) -> int:
    """
    Get rupee to credit conversion ratio from credit_config.
    
    Args:
        db: Database session
    
    Returns:
        int: Rupee to credit ratio (default: 10, meaning ₹10 = 1 credit)
    """
    ratio = get_credit_cost(db, 'rupee_to_credit_ratio')
    return ratio if ratio > 0 else 10  # Fallback to 10 if not configured


def initialize_user_credits(db: Session, user_id: int) -> UserCredits:
    """
    Initialize credits for a new user (signup flow).
    UNIFIED LOGIC: Uses add_credits() internally to ensure consistent behavior.
    
    Args:
        db: Database session
        user_id: Local user ID
    
    Returns:
        UserCredits: Created user credits record
    
    Raises:
        IntegrityError: If user_credits already exists for this user
    """
    # Check if credits already exist
    existing = db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
    if existing:
        logger.info(f"User credits already exist for user_id={user_id}")
        return existing
    
    # Get default free credits from config
    default_credits = get_default_free_credits(db)
    
    # Use unified add_credits function (creates user_credits if needed)
    success, error_msg = add_credits(
        db=db,
        user_id=user_id,
        credits=default_credits,
        reason="Signup bonus",
        reference_id=None
    )
    
    if not success:
        raise IntegrityError(f"Failed to initialize credits: {error_msg}", None, None)
    
    # Get the created user credits record
    user_credits = get_user_credits(db, user_id)
    if not user_credits:
        raise IntegrityError("User credits record not found after initialization", None, None)
    
    logger.info(f"Initialized credits for user_id={user_id}: {default_credits} credits")
    return user_credits


def get_user_credits(db: Session, user_id: int) -> Optional[UserCredits]:
    """
    Get user credits record.
    🔒 FINAL LOGIC: Do NOT auto-initialize credits.
    Credits are initialized ONLY on signup (via initialize_user_credits endpoint).
    
    CRITICAL: user_id parameter is actually external_user_id (business user ID).
    The user_credits table stores credits against external_user_id, NOT local users.id.
    
    Args:
        db: Database session
        user_id: External user ID (business user ID from auth backend)
    
    Returns:
        UserCredits: User credits record (None if not exists)
    """
    # CRITICAL: Log the exact query being executed
    logger.info(f"🔍 CREDIT QUERY: SELECT * FROM user_credits WHERE user_id = {user_id}")
    
    user_credits = db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
    
    # CRITICAL: Log query result
    if user_credits:
        logger.info(f"🔍 CREDIT QUERY RESULT: Found user_credits - total_credits={user_credits.total_credits}, used_credits={user_credits.used_credits}, available={user_credits.available_credits}")
    else:
        logger.warning(f"🔍 CREDIT QUERY RESULT: No user_credits found for user_id={user_id}")
    
    # ❌ REMOVED: Auto-initialization logic
    # Credits are initialized ONLY on signup, not on every credit check
    # if not user_credits:
    #     user_credits = initialize_user_credits(db, user_id)
    
    return user_credits


def check_credits_available(db: Session, user_id: int, action_key: str) -> Tuple[bool, int, int]:
    """
    Check if user has enough credits for an action.
    
    CRITICAL: user_id parameter is actually external_user_id (business user ID).
    The user_credits table stores credits against external_user_id, NOT local users.id.
    
    Args:
        db: Database session
        user_id: External user ID (business user ID from auth backend)
        action_key: Action identifier (e.g., 'ai_strategy_generate')
    
    Returns:
        tuple: (is_available, available_credits, required_credits)
    """
    # Get user credits (user_id is external_user_id)
    user_credits = get_user_credits(db, user_id)
    if not user_credits:
        logger.warning(f"Credit check failed: No user_credits found for external_user_id={user_id}")
        return False, 0, 0
    
    # Get credit cost for action
    required_credits = get_credit_cost(db, action_key)
    available_credits = user_credits.available_credits
    
    is_available = available_credits >= required_credits
    
    logger.info(f"Credit check for external_user_id={user_id}, action={action_key}: available={available_credits}, required={required_credits}, is_available={is_available}")
    
    return is_available, available_credits, required_credits


def deduct_credits(
    db: Session,
    user_id: int,
    action_key: Optional[str] = None,
    credits: Optional[int] = None,
    reason: Optional[str] = None,
    reference_id: Optional[str] = None,
    mobile: Optional[str] = None,
    admin_name: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Deduct credits from user wallet (atomic operation).
    
    CRITICAL: user_id parameter is actually external_user_id (business user ID).
    The user_credits table stores credits against external_user_id, NOT local users.id.
    
    Args:
        db: Database session
        user_id: External user ID (business user ID from auth backend)
        action_key: Action identifier (for automatic credit cost calculation)
        credits: Direct credit amount (if action_key not provided)
        reason: Optional reason for deduction
        reference_id: Optional reference ID (e.g., strategy_code)
        mobile: Mobile number in 91XXXXXXXXXX format (required for admin operations)
        admin_name: Admin name who deducted credits (required for admin operations)
    
    Returns:
        tuple: (success, error_message)
    """
    try:
        # Determine credit amount
        if action_key:
            # Check if credits available and get required amount
            is_available, available_credits, required_credits = check_credits_available(db, user_id, action_key)
            
            if not is_available:
                error_msg = f"Insufficient credits: available={available_credits}, required={required_credits}"
                logger.warning(f"Credit deduction failed for user_id={user_id}, action={action_key}: {error_msg}")
                return False, error_msg
            
            credits_to_deduct = required_credits
        elif credits is not None:
            # Direct credit amount provided (admin operations)
            credits_to_deduct = credits
        else:
            return False, "Either action_key or credits must be provided"
        
        # Get user credits (already checked to exist)
        user_credits = get_user_credits(db, user_id)
        
        # Check if sufficient credits available (for direct deduction)
        if credits is not None and user_credits.total_credits < credits_to_deduct:
            error_msg = f"Insufficient credits: available={user_credits.total_credits}, required={credits_to_deduct}"
            logger.warning(f"Credit deduction failed for user_id={user_id}: {error_msg}")
            return False, error_msg
        
        # If mobile not provided, get it from user
        if not mobile:
            from models import User
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.phone:
                mobile = user.phone
            else:
                # Fallback: use empty string (should not happen in production)
                mobile = ""
                logger.warning(f"Mobile not provided and user {user_id} has no phone number")
        
        # Deduct credits (atomic operation)
        if action_key:
            user_credits.used_credits += credits_to_deduct
        else:
            # For admin direct deduction, reduce total_credits
            user_credits.total_credits -= credits_to_deduct
        
        # Create transaction record with mobile field
        transaction = CreditTransaction(
            user_id=user_id,
            mobile=mobile,  # REQUIRED: Mobile in 91XXXXXXXXXX format
            type='debit',
            credits=credits_to_deduct,
            reason=reason or (f"Credit deduction for {action_key}" if action_key else "Credit deduction"),
            reference_id=reference_id,
            admin_name=admin_name  # Admin name for audit trail
        )
        db.add(transaction)
        
        # Commit transaction
        db.commit()
        
        logger.info(f"Credits deducted: user_id={user_id}, mobile={mobile}, credits={credits_to_deduct}, remaining={user_credits.available_credits if action_key else user_credits.total_credits}")
        
        return True, None
        
    except Exception as e:
        db.rollback()
        error_msg = f"Failed to deduct credits: {str(e)}"
        logger.error(f"Credit deduction error for user_id={user_id}: {error_msg}", exc_info=True)
        return False, error_msg


def add_credits(
    db: Session,
    user_id: int,
    credits: int,
    reason: Optional[str] = None,
    reference_id: Optional[str] = None,
    mobile: Optional[str] = None,
    admin_name: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Add credits to user wallet (atomic operation).
    UNIFIED FUNCTION: Used by signup, admin, and payment flows.
    
    Args:
        db: Database session
        user_id: Local user ID
        credits: Number of credits to add
        reason: Optional reason for adding credits (default: "Credits added")
        reference_id: Optional reference ID (e.g., payment_id)
        mobile: Mobile number in 91XXXXXXXXXX format (optional - auto-fetched from user if not provided)
        admin_name: Admin name who added credits (optional, for audit trail)
    
    Returns:
        tuple: (success, error_message)
    """
    try:
        # Get user credits - create if doesn't exist (for signup case)
        user_credits = get_user_credits(db, user_id)
        if not user_credits:
            # Create user credits record with 0 credits (will add credits below)
            from models import User
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False, f"User {user_id} not found"
            
            user_credits = UserCredits(
                user_id=user_id,
                total_credits=0,
                used_credits=0,
                is_active=True
            )
            db.add(user_credits)
            db.flush()  # Flush to get the record
        
        # If mobile not provided, get it from user
        if not mobile:
            from models import User
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.phone:
                mobile = user.phone
            else:
                # Fallback: use empty string (should not happen in production)
                mobile = ""
                logger.warning(f"Mobile not provided and user {user_id} has no phone number")
        
        # Add credits
        user_credits.total_credits += credits
        
        # Create transaction record with mobile field
        transaction = CreditTransaction(
            user_id=user_id,
            mobile=mobile,  # REQUIRED: Mobile in 91XXXXXXXXXX format
            type='credit',
            credits=credits,
            reason=reason or "Credits added",
            reference_id=reference_id,
            admin_name=admin_name  # Admin name for audit trail
        )
        db.add(transaction)
        
        # Commit transaction
        db.commit()
        
        logger.info(f"Credits added: user_id={user_id}, mobile={mobile}, credits={credits}, total={user_credits.total_credits}")
        
        return True, None
        
    except Exception as e:
        db.rollback()
        error_msg = f"Failed to add credits: {str(e)}"
        logger.error(f"Credit addition error for user_id={user_id}: {error_msg}", exc_info=True)
        return False, error_msg


def correct_credits(
    db: Session,
    user_id: int,
    original_transaction_id: int,
    amount: int,
    action: str,
    reason: str,
    admin_name: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[CreditTransaction]]:
    """
    Correct a credit transaction by creating a new correction transaction.
    This maintains full audit trail without modifying original transactions.
    
    Args:
        db: Database session
        user_id: Local user ID
        original_transaction_id: ID of the original transaction to correct
        amount: Amount of credits to add or deduct
        action: "add" or "deduct"
        reason: Required reason for correction
        admin_name: Optional admin name who made the correction
    
    Returns:
        tuple: (success, error_message, correction_transaction)
    """
    try:
        # Validate original transaction exists and belongs to user
        original_txn = db.query(CreditTransaction).filter(
            CreditTransaction.id == original_transaction_id,
            CreditTransaction.user_id == user_id
        ).first()
        
        if not original_txn:
            return False, "Original transaction not found or does not belong to user", None
        
        # Prevent duplicate corrections on same transaction
        existing_correction = db.query(CreditTransaction).filter(
            CreditTransaction.original_transaction_id == original_transaction_id
        ).first()
        
        if existing_correction:
            return False, "This transaction has already been corrected", None
        
        # Validate action
        if action not in ['add', 'deduct']:
            return False, "Action must be 'add' or 'deduct'", None
        
        # Validate amount
        if amount <= 0:
            return False, "Correction amount must be greater than 0", None
        
        # Get user credits
        user_credits = get_user_credits(db, user_id)
        
        # Apply correction
        if action == 'add':
            user_credits.total_credits += amount
            txn_type = 'credit'
        else:  # deduct
            # Check if user has enough credits
            if user_credits.available_credits < amount:
                return False, f"Insufficient credits. Available: {user_credits.available_credits}, Required: {amount}", None
            user_credits.used_credits += amount
            txn_type = 'debit'
        
        # Create correction transaction
        correction_txn = CreditTransaction(
            user_id=user_id,
            type=txn_type,
            credits=amount,
            reason=f"Correction: {reason}",
            original_transaction_id=original_transaction_id,
            admin_name=admin_name
        )
        db.add(correction_txn)
        
        # Commit transaction
        db.commit()
        db.refresh(correction_txn)
        
        logger.info(f"Credit correction applied: user_id={user_id}, original_txn_id={original_transaction_id}, action={action}, amount={amount}, admin={admin_name}")
        
        return True, None, correction_txn
        
    except Exception as e:
        db.rollback()
        error_msg = f"Failed to correct credits: {str(e)}"
        logger.error(f"Credit correction error for user_id={user_id}, original_txn_id={original_transaction_id}: {error_msg}", exc_info=True)
        return False, error_msg, None


def get_strategy_usage_count(
    db: Session,
    user_id: int,
    strategy_code: str,
    action_key: str
) -> int:
    """
    Get usage count for a strategy action.
    
    Args:
        db: Database session
        user_id: Local user ID
        strategy_code: Strategy code (e.g., 'STRG-XXXX')
        action_key: Action identifier (e.g., 'backtest')
    
    Returns:
        int: Usage count (0 if not found)
    """
    usage = db.query(StrategyUsage).filter(
        StrategyUsage.user_id == user_id,
        StrategyUsage.strategy_code == strategy_code,
        StrategyUsage.action_key == action_key
    ).first()
    
    return usage.usage_count if usage else 0


def increment_strategy_usage(
    db: Session,
    user_id: int,
    strategy_code: str,
    action_key: str
) -> StrategyUsage:
    """
    Increment usage count for a strategy action.
    Creates record if not exists.
    
    Args:
        db: Database session
        user_id: Local user ID
        strategy_code: Strategy code (e.g., 'STRG-XXXX')
        action_key: Action identifier (e.g., 'backtest')
    
    Returns:
        StrategyUsage: Updated or created usage record
    """
    usage = db.query(StrategyUsage).filter(
        StrategyUsage.user_id == user_id,
        StrategyUsage.strategy_code == strategy_code,
        StrategyUsage.action_key == action_key
    ).first()
    
    if usage:
        usage.usage_count += 1
    else:
        usage = StrategyUsage(
            user_id=user_id,
            strategy_code=strategy_code,
            action_key=action_key,
            usage_count=1
        )
        db.add(usage)
    
    db.commit()
    db.refresh(usage)
    
    logger.info(f"Strategy usage incremented: user_id={user_id}, strategy_code={strategy_code}, action={action_key}, count={usage.usage_count}")
    
    return usage


def check_backtest_free_limit(
    db: Session,
    user_id: int,
    strategy_code: str
) -> Tuple[bool, int]:
    """
    Check if backtest is within free limit (first 3 free).
    
    Args:
        db: Database session
        user_id: Local user ID
        strategy_code: Strategy code (e.g., 'STRG-XXXX')
    
    Returns:
        tuple: (is_free, usage_count)
    """
    usage_count = get_strategy_usage_count(db, user_id, strategy_code, 'backtest')
    is_free = usage_count < 3  # First 3 are free
    
    logger.info(f"Backtest free limit check: user_id={user_id}, strategy_code={strategy_code}, usage_count={usage_count}, is_free={is_free}")
    
    return is_free, usage_count

