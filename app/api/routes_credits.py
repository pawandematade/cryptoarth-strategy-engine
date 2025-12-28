"""
Credits API Routes
Manages user credits for AI and backtesting operations
"""
from fastapi import APIRouter, HTTPException, status, Header, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
from datetime import date, datetime, timezone
from sqlalchemy.orm import Session
from app.services.credit_service import (
    get_user_credits,
    check_credits_available,
    deduct_credits,
    add_credits,
    correct_credits
)
from app.services.user_sync_service import get_or_sync_user
from app.api.user_dependencies import get_current_user_strict
from app.database import get_db
from app.models import User, UserCredits

logger = logging.getLogger(__name__)

router = APIRouter()


class CreditsData(BaseModel):
    """Data payload for GET /auth/user/credits"""
    credits: int


class CreditsResponse(BaseModel):
    """Response model for GET /auth/user/credits"""
    success: bool
    data: CreditsData
    message: Optional[str] = None


class CreditTransactionItem(BaseModel):
    """Credit transaction item"""
    id: int
    date: str
    type: str
    credits: int
    source: str
    balance_after: int
    reason: str


class CreditTransactionsResponse(BaseModel):
    """Response model for GET /auth/credits/transactions"""
    success: bool
    data: List[CreditTransactionItem]
    message: Optional[str] = None


def get_credits_by_phone(db: Session, user: User) -> dict:
    """
    Get credits for user by phone number (production-safe).
    🔒 FINAL LOGIC - NEVER RETURNS None:
    - 10 credits ONLY IF user signed up TODAY
    - Otherwise, return actual DB credits (never override for old users)
    - ALWAYS returns a number (never None/null)
    
    Args:
        db: Database session
        user: User model instance with phone field
    
    Returns:
        dict: {
            "success": True,
            "data": {
                "credits": int  # ALWAYS a number, never None
            }
        }
    """
    phone = user.phone
    
    # Get today's date (timezone-aware)
    today = datetime.now(timezone.utc).date()
    
    # Get user's signup date (created_at) - timezone-aware comparison
    user_joined_date = None
    if user.created_at:
        # Handle both timezone-aware and naive datetimes
        if user.created_at.tzinfo is not None:
            user_joined_date = user.created_at.date()
        else:
            # If naive, assume UTC
            user_joined_date = user.created_at.date()
    
    # CRITICAL: Query credits by joining UserCredits with User table
    user_credits = (
        db.query(UserCredits)
        .join(User, UserCredits.user_id == User.id)
        .filter(User.phone == phone)
        .first()
    )
    
    # 🔒 FINAL RULE: Extract credits - NEVER return None
    if user_credits:
        # Credits record exists - use DB value
        credits_value = user_credits.available_credits
        
        # 🚫 STRICTLY FORBIDDEN: Never return None
        if credits_value is None:
            credits_value = 0
        elif not isinstance(credits_value, (int, float)):
            # Convert to int if not numeric
            try:
                credits_value = int(float(credits_value))
            except (ValueError, TypeError):
                credits_value = 0
        
        # Ensure it's an integer
        credits = int(credits_value) if credits_value is not None else 0
        
        logger.info(f"[CREDITS_API] DB credits found: phone={phone}, credits={credits}")
    else:
        # No credits record found
        # 🔒 FINAL RULE: 10 credits ONLY if user signed up TODAY
        if user_joined_date and user_joined_date == today:
            # New signup today - return 10 credits
            credits = 10
            logger.info(f"[CREDITS_API] New signup today - returning 10 credits for phone={phone}")
        else:
            # Old user or no signup date - return 0 (never return 10 for old users)
            credits = 0
            logger.info(f"[CREDITS_API] No credits record - returning 0 for phone={phone}, joined_date={user_joined_date}, today={today}")
    
    # 🚫 FINAL SAFETY CHECK: Ensure credits is ALWAYS a number
    if credits is None:
        logger.error(f"[CREDITS_API] CRITICAL: credits is None for phone={phone}, forcing to 0")
        credits = 0
    
    # Ensure integer type
    credits = int(credits) if credits is not None else 0
    
    # CRITICAL: Always return data object with number (never None)
    return {
        "success": True,
        "data": {
            "credits": credits  # ALWAYS a number
        }
    }


def normalize_mobile(mobile: str) -> str:
    """
    Normalize mobile number to 91XXXXXXXXXX format.
    
    Args:
        mobile: 10-digit mobile number (from frontend)
    
    Returns:
        str: Mobile number in 91XXXXXXXXXX format
    
    Raises:
        ValueError: If mobile format is invalid
    """
    if not mobile:
        raise ValueError("Mobile number cannot be empty")
    
    # Remove any non-digit characters
    mobile_clean = ''.join(filter(str.isdigit, mobile))
    
    # If already has country code (91XXXXXXXXXX), return as is
    if mobile_clean.startswith('91') and len(mobile_clean) == 12:
        return mobile_clean
    # If 10 digits, prepend 91
    elif len(mobile_clean) == 10:
        return f"91{mobile_clean}"
    else:
        raise ValueError(f"Invalid mobile number format: {mobile} (expected 10 digits, got {len(mobile_clean)})")


def format_mobile_display(mobile: str) -> str:
    """
    Format mobile number for display (remove 91 prefix if present).
    
    Args:
        mobile: Mobile number in 91XXXXXXXXXX or XXXXXXXXXX format
    
    Returns:
        str: 10-digit mobile number for display
    """
    if mobile.startswith('91') and len(mobile) == 12:
        return mobile[2:]
    return mobile


class ConsumeCreditRequest(BaseModel):
    """Request model for consuming credits"""
    action_type: str = Field(..., description="Action type: 'ai_generate', 'ai_improve', or 'backtest'")
    amount: Optional[int] = Field(None, description="Optional custom credit amount (uses default cost if not provided)")


class AddCreditRequest(BaseModel):
    """Request model for adding credits (for admin/future payment integration)"""
    amount: int = Field(..., gt=0, description="Amount of credits to add")


class CorrectCreditRequest(BaseModel):
    """Request model for correcting credits"""
    original_transaction_id: int = Field(..., description="ID of the original transaction to correct")
    action: str = Field(..., description="Action: 'ADD' or 'DEDUCT'")
    amount: int = Field(..., gt=0, description="Amount of credits to add or deduct")
    remark: str = Field(..., min_length=1, description="Required remark for correction")


class ManualCreditUpdateRequest(BaseModel):
    """Request model for manual credit update by admin"""
    user_phone: str = Field(..., min_length=10, max_length=10, description="10-digit mobile number")
    amount: int = Field(..., gt=0, description="Amount of credits to add")
    reason: str = Field(..., min_length=1, description="Required reason for adding credits")
    admin_name: Optional[str] = Field(None, description="Optional admin name who added the credits")


class AddCreditRequest(BaseModel):
    """Request model for adding credits by admin"""
    mobile: str = Field(..., min_length=10, max_length=10, description="10-digit mobile number")
    amount: int = Field(..., gt=0, description="Amount of credits to add")
    remark: str = Field(..., min_length=1, description="Required remark for adding credits")


class DeductCreditRequest(BaseModel):
    """Request model for deducting credits by admin"""
    mobile: str = Field(..., min_length=10, max_length=10, description="10-digit mobile number")
    amount: int = Field(..., gt=0, description="Amount of credits to deduct")
    remark: str = Field(..., min_length=1, description="Required remark for deducting credits")


@router.get("/user/credits", response_model=CreditsResponse)
def get_credits(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_strict)
):
    """
    Get current credit balance for the authenticated user
    CRITICAL: Credits are queried by phone number (production-safe)
    
    Returns:
        dict: {
            "success": bool,
            "data": {
                "credits": int  # Always present, even if 0
            }
        }
    """
    try:
        # CRITICAL: Get credits directly by user_id (JWT source of truth)
        # NO phone-based queries, NO admin overrides
        logger.error(f"JWT USER ID = {user.id}")
        
        query = db.query(UserCredits).filter(
            UserCredits.user_id == user.id
        )
        
        # Debug: Log row count
        row_count = query.count()
        logger.error(f"ROW COUNT = {row_count}")
        
        user_credits = query.first()
        
        # Calculate available credits
        if user_credits:
            credits = max(0, user_credits.total_credits - user_credits.used_credits)
            logger.info(f"[Credits Balance] Found: user_id={user.id}, total={user_credits.total_credits}, used={user_credits.used_credits}, available={credits}")
        else:
            # No credits record - return 0
            credits = 0
            logger.info(f"[Credits Balance] No record found for user_id={user.id}, returning 0")
        
        return CreditsResponse(
            success=True,
            data=CreditsData(
                credits=int(credits)  # ALWAYS a number
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting credits: {e}", exc_info=True)
        # 🚫 ALWAYS return number on error (never None)
        return CreditsResponse(
            success=True,
            data=CreditsData(credits=0)
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


@router.post("/admin/credits/correct")
def admin_correct_credits(
    request: CorrectCreditRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to correct a credit transaction.
    Creates a new correction transaction linked to the original transaction.
    Original transaction is NEVER modified (immutable ledger).
    
    Args:
        request: CorrectCreditRequest with original_transaction_id, action (ADD | DEDUCT), amount, remark
        authorization: Authorization header (admin required)
        db: Database session
    
    Returns:
        dict: {
            "success": bool,
            "message": str,
            "balance": int
        }
    """
    try:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # TODO: Add admin authentication check here
        # For now, we'll allow any authenticated user (should be restricted to admin only)
        
        # Validate action
        if request.action.upper() not in ['ADD', 'DEDUCT']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action must be 'ADD' or 'DEDUCT'"
            )
        
        # Get original transaction
        from app.models import CreditTransaction
        original_txn = db.query(CreditTransaction).filter(
            CreditTransaction.id == request.original_transaction_id
        ).first()
        
        if not original_txn:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original transaction not found"
            )
        
        # Check if already corrected
        if original_txn.original_transaction_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This transaction is already a correction. Cannot correct a correction."
            )
        
        # Get user mobile for correction transaction
        from app.models import User
        user = db.query(User).filter(User.id == original_txn.user_id).first()
        user_mobile = user.phone if user and user.phone else ""
        
        # Get admin name from auth context (TODO: extract from JWT token)
        admin_name = "Admin"  # TODO: Extract from JWT token
        
        # Apply correction
        action_lower = request.action.lower()
        if action_lower == 'add':
            success, error_msg = add_credits(
                db=db,
                user_id=original_txn.user_id,
                credits=request.amount,
                reason=f"Correction: {request.remark}",
                reference_id=None,
                mobile=user_mobile,  # REQUIRED: Pass user mobile
                admin_name=admin_name  # REQUIRED: Pass admin name
            )
        else:  # deduct
            success, error_msg = deduct_credits(
                db=db,
                user_id=original_txn.user_id,
                credits=request.amount,
                reason=f"Correction: {request.remark}",
                reference_id=None,
                mobile=user_mobile,  # REQUIRED: Pass user mobile
                admin_name=admin_name  # REQUIRED: Pass admin name
            )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        
        # Get the last transaction (the correction we just created)
        correction_txn = db.query(CreditTransaction).filter(
            CreditTransaction.user_id == original_txn.user_id
        ).order_by(CreditTransaction.created_at.desc()).first()
        
        # Link correction to original transaction
        if correction_txn:
            correction_txn.original_transaction_id = request.original_transaction_id
            # TODO: Extract admin name from JWT token
            correction_txn.admin_name = "Admin"  # TODO: Get from session
            db.commit()
        
        # Get updated balance
        user_credits = get_user_credits(db, original_txn.user_id)
        
        return {
            "success": True,
            "message": f"Credit correction applied successfully",
            "balance": user_credits.total_credits if user_credits else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error correcting credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/admin/credits/lookup")
def admin_credits_lookup(
    phone: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to lookup user credit information by phone number.
    Returns user details and recent credit transactions.
    
    Args:
        phone: 10-digit mobile number
        authorization: Authorization header (admin required)
        db: Database session
    
    Returns:
        dict: {
            "success": bool,
            "user_exists": bool,
            "user_id": int,
            "user_phone": str,
            "total_credits": int,
            "transactions": [...],
            "message": str
        }
    """
    try:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # Validate phone number (exactly 10 digits)
        if not phone or not phone.isdigit() or len(phone) != 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number must be exactly 10 digits"
            )
        
        # Normalize to 91XXXXXXXXXX format for DB query
        normalized_mobile = normalize_mobile(phone)
        
        # Find user by phone (check both formats for compatibility)
        from app.models import User, CreditTransaction, UserCredits
        from sqlalchemy.orm import joinedload
        
        user = db.query(User).filter(
            (User.phone == normalized_mobile) | (User.phone == phone)
        ).first()
        
        if not user:
            return {
                "found": False,
                "message": "Number not present in credit database"
            }
        
        # Get user credits
        user_credits = get_user_credits(db, user.id)
        total_credits = user_credits.total_credits if user_credits else 0
        
        # Get recent credit transactions (last 10 only)
        transactions_query = db.query(CreditTransaction).options(
            joinedload(CreditTransaction.user)
        ).filter(
            CreditTransaction.user_id == user.id
        ).order_by(
            CreditTransaction.created_at.desc()
        ).limit(10)
        
        transactions = transactions_query.all()
        
        # Calculate balance after each transaction (in reverse chronological order)
        running_balance = total_credits
        transaction_list = []
        for txn in transactions:
            # Calculate balance before this transaction
            if txn.type == 'credit':
                balance_after = running_balance
                running_balance -= txn.credits  # Subtract to get previous balance
            else:  # debit
                balance_after = running_balance
                running_balance += txn.credits  # Add to get previous balance
            
            # Determine source from reason
            source = "Other"
            reason_lower = (txn.reason or "").lower()
            if "payment" in reason_lower or "order" in reason_lower:
                source = "Payment"
            elif "ai_strategy_generate" in reason_lower or "generate" in reason_lower:
                source = "AI Generate"
            elif "backtest" in reason_lower:
                source = "Backtest"
            elif "correction" in reason_lower:
                source = "Correction"
            elif "manual" in reason_lower:
                source = "Manual"
            
            transaction_list.append({
                "id": txn.id,
                "user_id": txn.user_id,
                "mobile": format_mobile_display(user.phone) if user else phone,
                "date": txn.created_at.isoformat() if txn.created_at else "",
                "action": txn.type.upper(),  # ADD, DEDUCT, CORRECTION
                "credits": txn.credits,
                "balance_after": balance_after,
                "remark": txn.reason or "",
                "admin": txn.admin_name or "",
                "original_transaction_id": txn.original_transaction_id
            })
        
        return {
            "found": True,
            "user": {
                "mobile": format_mobile_display(user.phone),
                "balance": total_credits
            },
            "transactions": transaction_list
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in credits lookup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/admin/credits/manual-update")
def admin_manual_credit_update(
    request: ManualCreditUpdateRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to manually add credits to a user by phone number.
    Works even if user has no credit history (creates first transaction).
    
    Args:
        request: ManualCreditUpdateRequest with user_phone, amount, reason
        authorization: Authorization header (admin required)
        db: Database session
    
    Returns:
        dict: {
            "success": bool,
            "message": str,
            "credits_added": int,
            "total_credits": int,
            "transaction_id": int
        }
    """
    try:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # TODO: Add admin authentication check here
        # For now, we'll allow any authenticated user (should be restricted to admin only)
        
        # Validate phone number (exactly 10 digits)
        if not request.user_phone.isdigit() or len(request.user_phone) != 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number must be exactly 10 digits"
            )
        
        # Normalize to 91XXXXXXXXXX format for DB query
        normalized_mobile = normalize_mobile(request.user_phone)
        
        # Find user by phone (check both formats for compatibility)
        from app.models import User
        user = db.query(User).filter(
            (User.phone == normalized_mobile) | (User.phone == request.user_phone)
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not registered with this mobile number"
            )
        
        # Get admin name from auth context (TODO: extract from JWT token)
        admin_name = request.admin_name or "Admin"  # TODO: Extract from JWT token
        
        # Add credits (this will create user_credits if it doesn't exist)
        # CRITICAL: Pass normalized_mobile and admin_name
        success, error_msg = add_credits(
            db=db,
            user_id=user.id,
            credits=request.amount,
            reason=request.reason or f"Manual credit addition by admin",
            reference_id=None,
            mobile=normalized_mobile,  # REQUIRED: Pass normalized mobile
            admin_name=admin_name  # REQUIRED: Pass admin name
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg or "Failed to add credits"
            )
        
        # Get updated user credits
        user_credits = get_user_credits(db, user.id)
        
        # Get the last transaction (the one we just created)
        from app.models import CreditTransaction
        last_transaction = db.query(CreditTransaction).filter(
            CreditTransaction.user_id == user.id
        ).order_by(CreditTransaction.created_at.desc()).first()
        
        return {
            "success": True,
            "message": f"Successfully added {request.amount} credits to user {request.user_phone}",
            "credits_added": request.amount,
            "total_credits": user_credits.total_credits if user_credits else request.amount,
            "transaction_id": last_transaction.id if last_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in manual credit update: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/admin/credits/add")
def admin_add_credits_by_mobile(
    request: AddCreditRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to add credits to a user by mobile number.
    User must exist in database - returns 404 if user not found.
    
    Args:
        request: AddCreditRequest with mobile (10 digits), amount, remark
        authorization: Authorization header (admin required)
        db: Database session
    
    Returns:
        dict: {
            "success": bool,
            "message": str,
            "balance": int
        }
    """
    try:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # Validate mobile number (exactly 10 digits)
        if not request.mobile.isdigit() or len(request.mobile) != 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mobile number must be exactly 10 digits"
            )
        
        # CRITICAL: Normalize to 91XXXXXXXXXX format BEFORE any DB operation
        normalized_mobile = normalize_mobile(request.mobile)
        
        # MANDATORY: Check user existence ONLY from users table (NOT credit-related tables)
        from app.models import User
        # Use phone column (matches User model) - check both normalized and raw for compatibility
        user = db.query(User).filter(
            (User.phone == normalized_mobile) | (User.phone == request.mobile)
        ).first()
        
        # MANDATORY: User must exist in users table - return 404 if not found
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not registered with this mobile number"
            )
        
        # Note: user_credits table is NOT used for existence check
        # If user exists but user_credits row does not, add_credits() will create it
        
        # Get admin name from auth context (TODO: extract from JWT token)
        # For now, use placeholder - should be extracted from authorization header
        admin_name = "Admin"  # TODO: Extract from JWT token
        
        # Add credits (this will create user_credits if it doesn't exist)
        # CRITICAL: Pass normalized_mobile and admin_name
        success, error_msg = add_credits(
            db=db,
            user_id=user.id,
            credits=request.amount,
            reason=request.remark,
            reference_id=None,
            mobile=normalized_mobile,  # REQUIRED: Pass normalized mobile
            admin_name=admin_name  # REQUIRED: Pass admin name
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg or "Failed to add credits"
            )
        
        # Get updated user credits
        user_credits = get_user_credits(db, user.id)
        
        return {
            "success": True,
            "message": f"Successfully added {request.amount} credits",
            "balance": user_credits.total_credits if user_credits else request.amount
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/admin/credits/deduct")
def admin_deduct_credits_by_mobile(
    request: DeductCreditRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to deduct credits from a user by mobile number.
    
    Args:
        request: DeductCreditRequest with mobile (10 digits), amount, remark
        authorization: Authorization header (admin required)
        db: Database session
    
    Returns:
        dict: {
            "success": bool,
            "message": str,
            "balance": int
        }
    """
    try:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # Validate mobile number (exactly 10 digits)
        if not request.mobile.isdigit() or len(request.mobile) != 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mobile number must be exactly 10 digits"
            )
        
        # CRITICAL: Normalize to 91XXXXXXXXXX format BEFORE any DB operation
        normalized_mobile = normalize_mobile(request.mobile)
        
        # Find user (use normalized_mobile for DB query)
        from app.models import User
        user = db.query(User).filter(
            (User.phone == normalized_mobile) | (User.phone == request.mobile)
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check available credits
        user_credits = get_user_credits(db, user.id)
        if not user_credits or user_credits.total_credits < request.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient credits. Available: {user_credits.total_credits if user_credits else 0}"
            )
        
        # Get admin name from auth context (TODO: extract from JWT token)
        admin_name = "Admin"  # TODO: Extract from JWT token
        
        # Deduct credits
        # CRITICAL: Pass normalized_mobile and admin_name
        success, error_msg = deduct_credits(
            db=db,
            user_id=user.id,
            credits=request.amount,  # Direct credit amount
            reason=request.remark,
            reference_id=None,
            mobile=normalized_mobile,  # REQUIRED: Pass normalized mobile
            admin_name=admin_name  # REQUIRED: Pass admin name
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg or "Failed to deduct credits"
            )
        
        # Get updated user credits
        user_credits = get_user_credits(db, user.id)
        
        return {
            "success": True,
            "message": f"Successfully deducted {request.amount} credits",
            "balance": user_credits.total_credits if user_credits else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deducting credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/admin/credits/transactions")
def admin_get_all_credit_transactions(
    limit: int = 50,
    offset: int = 0,
    user_phone: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to get all credit transactions (with pagination and filtering)
    
    Args:
        limit: Number of transactions to return (default: 50, max: 200)
        offset: Number of transactions to skip (default: 0)
        user_phone: Optional filter by user phone number
        authorization: Authorization header (admin required)
        db: Database session
    
    Returns:
        dict: {
            "success": bool,
            "transactions": [
                {
                    "id": int,
                    "user_id": int,
                    "user_phone": str,
                    "date": str,
                    "type": str,
                    "credits": int,
                    "source": str,
                    "reason": str,
                    "admin_name": str,
                    "original_transaction_id": int,
                    "balance_after": int
                }
            ],
            "total": int,
            "message": str
        }
    """
    try:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # TODO: Add admin authentication check here
        # For now, we'll allow any authenticated user (should be restricted to admin only)
        
        # Validate limit
        limit = min(max(1, limit), 200)
        offset = max(0, offset)
        
        # Build query
        from app.models import CreditTransaction, User
        from sqlalchemy.orm import joinedload
        
        # If user_phone is provided, validate user exists first
        user_id = None
        user_exists = None
        if user_phone:
            # Validate phone is exactly 10 digits
            if not user_phone.isdigit() or len(user_phone) != 10:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Phone number must be exactly 10 digits"
                )
            
            # CRITICAL: Normalize to 91XXXXXXXXXX format BEFORE DB query
            normalized_mobile = normalize_mobile(user_phone)
            
            # Check if user exists (use normalized_mobile for DB query)
            user = db.query(User).filter(
                (User.phone == normalized_mobile) | (User.phone == user_phone)
            ).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not registered with this mobile number"
                )
            
            user_id = user.id
            user_exists = True
        
        # Query with eager loading of user relationship
        query = db.query(CreditTransaction).options(
            joinedload(CreditTransaction.user)
        )
        
        # Filter by user phone if provided (requires join)
        if user_phone:
            # Use normalized mobile for query
            normalized_mobile = normalize_mobile(user_phone)
            query = query.join(User).filter(
                (User.phone == normalized_mobile) | (User.phone == user_phone)
            )
        
        # Get total count (before pagination)
        total = query.count()
        
        # Get transactions with pagination
        transactions = query.order_by(
            CreditTransaction.created_at.desc()
        ).offset(offset).limit(limit).all()
        
        # Format transactions
        transaction_list = []
        for txn in transactions:
            # Get user from relationship (eagerly loaded)
            user = txn.user
            
            # Determine source from reason
            source = "Other"
            reason_lower = (txn.reason or "").lower()
            if "payment" in reason_lower or "order" in reason_lower:
                source = "Payment"
            elif "ai_strategy_generate" in reason_lower or "generate" in reason_lower:
                source = "AI Generate"
            elif "backtest" in reason_lower:
                source = "Backtest"
            elif "correction" in reason_lower:
                source = "Correction"
            
            transaction_list.append({
                "id": txn.id,
                "user_id": txn.user_id,
                "user_phone": user.phone if user and user.phone else "",
                "date": txn.created_at.isoformat() if txn.created_at else "",
                "type": txn.type,
                "credits": txn.credits,
                "source": source,
                "reason": txn.reason or "",
                "admin_name": txn.admin_name or "",
                "original_transaction_id": txn.original_transaction_id,
                "balance_after": 0  # Will be calculated if needed
            })
        
        return {
            "success": True,
            "transactions": transaction_list,
            "total": total,
            "limit": limit,
            "offset": offset,
            "user_exists": user_exists if user_phone else None,
            "user_id": user_id if user_phone else None,
            "message": f"Retrieved {len(transaction_list)} credit transactions"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting admin credit transactions: {e}", exc_info=True)
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/credits/transactions", response_model=CreditTransactionsResponse)
def get_credit_transactions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_strict)
):
    """
    Get credit transaction history for the authenticated user
    
    Returns:
        dict: {
            "success": bool,
            "transactions": [
                {
                    "id": int,
                    "date": str,
                    "type": str,
                    "credits": int,
                    "source": str,
                    "balance_after": int,
                    "reason": str
                }
            ],
            "message": str
        }
    """
    try:
        # CRITICAL: Get user credits directly by user_id (JWT source of truth)
        # NO phone-based queries, NO admin overrides
        logger.error(f"JWT USER ID = {user.id}")
        
        from app.models import UserCredits
        user_credits_query = db.query(UserCredits).filter(
            UserCredits.user_id == user.id
        )
        user_credits = user_credits_query.first()
        
        # Calculate available credits
        if user_credits:
            current_balance = max(0, user_credits.total_credits - user_credits.used_credits)
        else:
            current_balance = 0
        
        # Get credit transactions for user - JWT user.id is ONLY source of truth
        from app.models import CreditTransaction
        query = db.query(CreditTransaction).filter(
            CreditTransaction.user_id == user.id
        )
        
        # Debug: Log row count
        row_count = query.count()
        logger.error(f"ROW COUNT = {row_count}")
        
        transactions = query.order_by(CreditTransaction.created_at.desc()).all()
        logger.info(f"[Credit Transactions] Found {len(transactions)} transactions for user_id={user.id}")
        
        # Format credit transactions with running balance
        # We need to calculate balance backwards from current balance
        transaction_list = []
        running_balance = current_balance
        
        for txn in transactions:
            # Calculate balance after this transaction
            if txn.type == 'credit':
                balance_after = running_balance
                running_balance -= txn.credits  # Subtract to get previous balance
            else:  # debit
                balance_after = running_balance
                running_balance += txn.credits  # Add to get previous balance
            
            # Determine source from reason
            source = "Other"
            reason_lower = (txn.reason or "").lower()
            if "payment" in reason_lower or "order" in reason_lower:
                source = "Payment"
            elif "ai_strategy_generate" in reason_lower or "generate" in reason_lower:
                source = "AI Generate"
            elif "backtest" in reason_lower:
                source = "Backtest"
            
            transaction_list.append(CreditTransactionItem(
                id=txn.id,
                date=txn.created_at.isoformat() if txn.created_at else "",
                type=txn.type,
                credits=txn.credits,
                source=source,
                balance_after=balance_after,
                reason=txn.reason or ""
            ))
        
        return CreditTransactionsResponse(
            success=True,
            data=transaction_list,
            message=f"Retrieved {len(transaction_list)} credit transactions"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting credit transactions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

