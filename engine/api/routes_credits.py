"""
Credits API Routes
Manages user credits for AI and backtesting operations
"""
from fastapi import APIRouter, HTTPException, status, Header, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
from sqlalchemy.orm import Session
from core.services.credit_service import (
    get_user_credits,
    deduct_credits,
    add_credits
)
from api.user_dependencies import get_current_user_strict
from common.db import get_db
from models import User, UserCredits

logger = logging.getLogger(__name__)

router = APIRouter()


class CreditsData(BaseModel):
    """Data payload for GET /auth/user/credits"""
    credits: int
    total_credits: Optional[int] = None
    used_credits: Optional[int] = None
    available_credits: Optional[int] = None


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


class CreditTransactionsData(BaseModel):
    """Paginated credit transactions data"""
    items: List[CreditTransactionItem]
    total: int
    page: int
    limit: int
    total_pages: int


class CreditTransactionsResponse(BaseModel):
    """Response model for GET /auth/credits/transactions"""
    success: bool
    data: CreditTransactionsData
    message: Optional[str] = None


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


class AdminAddCreditRequest(BaseModel):
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
        # CRITICAL: ALL business tables store external_user_id in user_id column
        # user_credits.user_id stores external_user_id (canonical ID), NOT users.id (local ID)
        # This is consistent with credit_transactions, payment_transactions, etc.
        logger.debug(f"JWT USER ID = {user.id}, EXTERNAL USER ID = {user.external_user_id}")
        
        query = db.query(UserCredits).filter(
            UserCredits.user_id == user.external_user_id
        )
        
        # Debug: Log row count
        row_count = query.count()
        logger.debug(f"ROW COUNT = {row_count}")
        
        user_credits = query.first()
        
        # Calculate available credits
        if user_credits:
            total_credits = user_credits.total_credits or 0
            used_credits = user_credits.used_credits or 0
            available_credits = max(0, total_credits - used_credits)
            logger.info(f"[Credits Balance] Found: external_user_id={user.external_user_id}, total={total_credits}, used={used_credits}, available={available_credits}")
            
            return CreditsResponse(
                success=True,
                data=CreditsData(
                    credits=int(available_credits),
                    total_credits=int(total_credits),
                    used_credits=int(used_credits),
                    available_credits=int(available_credits)
                )
            )
        else:
            # No credits record - return 0
            logger.info(f"[Credits Balance] No record found for external_user_id={user.external_user_id}, returning 0")
            return CreditsResponse(
                success=True,
                data=CreditsData(
                    credits=0,
                    total_credits=0,
                    used_credits=0,
                    available_credits=0
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


@router.post("/user/initialize-credits")
def initialize_credits(authorization: Optional[str] = Header(None)):
    """
    Initialize credits endpoint (DISABLED - free credits discontinued)
    
    Returns:
        dict: {
            "success": bool,
            "credits": int,
            "message": str
        }
    """
    # FREE CREDITS DISCONTINUED - Return 0 credits
    return {
        "success": True,
        "credits": 0,
        "message": "Free credits discontinued. Credits can be added via payment or admin."
    }


@router.post("/admin/add-credits")
def admin_add_credits(
    user_id: str,
    request: ManualCreditUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to add credits to a user account
    (For future payment integration or admin operations)
    
    Args:
        user_id: external_user_id (canonical user ID) to add credits to
        request: AddCreditRequest with amount
        db: Database session
    
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
        
        # Validate external_user_id exists in users table
        user = db.query(User).filter(User.external_user_id == int(user_id)).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with external_user_id={user_id} not found"
            )
        
        # CRITICAL: Business tables use external_user_id, not user.id
        business_user_id = user.external_user_id
        
        # Admin name (JWT parsing not implemented)
        admin_name = "SYSTEM_ADMIN"
        
        # Add credits using external_user_id
        success, error_msg = add_credits(
            db=db,
            user_id=business_user_id,
            credits=request.amount,
            reason=request.reason,
            reference_id=None,
            mobile=user.phone or "",
            admin_name=admin_name
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg or "Failed to add credits"
            )
        
        # Get updated user credits
        user_credits = get_user_credits(db, business_user_id)
        total_credits = user_credits.total_credits if user_credits else 0
        used_credits = user_credits.used_credits if user_credits else 0
        credits_remaining = max(0, total_credits - used_credits)
        
        return {
            "success": True,
            "credits_remaining": credits_remaining,
            "credits_added": request.amount,
            "message": f"Successfully added {request.amount} credits"
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
        from models import CreditTransaction
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
        
        # CRITICAL: original_txn.user_id already stores external_user_id (business table)
        # No need to look up user - use transaction's user_id directly
        business_user_id = original_txn.user_id
        
        # Get user mobile for correction transaction (optional, for logging)
        from models import User
        user = db.query(User).filter(User.external_user_id == business_user_id).first()
        user_mobile = user.phone if user and user.phone else ""
        
        # Get admin name from auth context (TODO: extract from JWT token)
        admin_name = "Admin"  # TODO: Extract from JWT token
        
        # Apply correction using external_user_id
        action_lower = request.action.lower()
        if action_lower == 'add':
            success, error_msg = add_credits(
                db=db,
                user_id=business_user_id,
                credits=request.amount,
                reason=f"Correction: {request.remark}",
                reference_id=None,
                mobile=user_mobile,  # REQUIRED: Pass user mobile
                admin_name=admin_name  # REQUIRED: Pass admin name
            )
        else:  # deduct
            success, error_msg = deduct_credits(
                db=db,
                user_id=business_user_id,
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
            CreditTransaction.user_id == business_user_id
        ).order_by(CreditTransaction.created_at.desc()).first()
        
        # Link correction to original transaction
        if correction_txn:
            correction_txn.original_transaction_id = request.original_transaction_id
            # TODO: Extract admin name from JWT token
            correction_txn.admin_name = "Admin"  # TODO: Get from session
            db.commit()
        
        # Get updated balance using external_user_id
        user_credits = get_user_credits(db, business_user_id)
        
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
        from models import User, CreditTransaction, UserCredits
        from sqlalchemy.orm import joinedload
        
        user = db.query(User).filter(
            (User.phone == normalized_mobile) | (User.phone == phone)
        ).first()
        
        if not user:
            # STANDARDIZED: Always return { found, user, transactions }
            return {
                "found": False,
                "user": None,
                "transactions": []
            }
        
        # CRITICAL: Business tables use external_user_id, not user.id
        business_user_id = user.external_user_id
        
        # Get user credits using external_user_id
        user_credits = get_user_credits(db, business_user_id)
        total_credits = user_credits.total_credits if user_credits else 0
        
        # Get recent credit transactions (last 10 only)
        # CRITICAL: Business tables store external_user_id in user_id column
        transactions_query = db.query(CreditTransaction).options(
            joinedload(CreditTransaction.user)
        ).filter(
            CreditTransaction.user_id == user.external_user_id
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
        from models import User
        user = db.query(User).filter(
            (User.phone == normalized_mobile) | (User.phone == request.user_phone)
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not registered with this mobile number"
            )
        
        # Admin name (JWT parsing not implemented)
        admin_name = "SYSTEM_ADMIN"
        
        # CRITICAL: Business tables use external_user_id, not user.id
        business_user_id = user.external_user_id
        
        # Add credits (this will create user_credits if it doesn't exist)
        # CRITICAL: Pass normalized_mobile and admin_name, use external_user_id
        success, error_msg = add_credits(
            db=db,
            user_id=business_user_id,
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
        
        # Get updated user credits using external_user_id
        user_credits = get_user_credits(db, business_user_id)
        
        # Get the last transaction (the one we just created)
        # CRITICAL: Business tables store external_user_id in user_id column
        from models import CreditTransaction
        last_transaction = db.query(CreditTransaction).filter(
            CreditTransaction.user_id == user.external_user_id
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
    request: AdminAddCreditRequest,
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
        from models import User
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
        
        # CRITICAL: Business tables use external_user_id, not user.id
        business_user_id = user.external_user_id
        
        # Add credits (this will create user_credits if it doesn't exist)
        # CRITICAL: Pass normalized_mobile and admin_name, use external_user_id
        success, error_msg = add_credits(
            db=db,
            user_id=business_user_id,
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
        
        # Get updated user credits using external_user_id
        user_credits = get_user_credits(db, business_user_id)
        
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
        from models import User
        user = db.query(User).filter(
            (User.phone == normalized_mobile) | (User.phone == request.mobile)
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # CRITICAL: Business tables use external_user_id, not user.id
        business_user_id = user.external_user_id
        
        # Check available credits using external_user_id
        user_credits = get_user_credits(db, business_user_id)
        if not user_credits or user_credits.total_credits < request.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient credits. Available: {user_credits.total_credits if user_credits else 0}"
            )
        
        # Get admin name from auth context (TODO: extract from JWT token)
        admin_name = "Admin"  # TODO: Extract from JWT token
        
        # Deduct credits using external_user_id
        # CRITICAL: Pass normalized_mobile and admin_name
        success, error_msg = deduct_credits(
            db=db,
            user_id=business_user_id,
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
        
        # Get updated user credits using external_user_id
        user_credits = get_user_credits(db, business_user_id)
        
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
        from models import CreditTransaction, User
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
    page: int = 1,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_strict)
):
    """
    Get paginated credit transaction history for the authenticated user
    
    Returns:
        dict: {
            "success": bool,
            "data": {
                "items": [...],
                "total": int,
                "page": int,
                "limit": int,
                "total_pages": int
            },
            "message": str
        }
    """
    try:
        # Validate pagination params
        page = max(1, page)
        limit = max(1, min(limit, 100))  # Cap at 100 per page
        
        # CRITICAL: Business tables store external_user_id in user_id column
        # Use user.external_user_id (canonical ID) NOT user.id (local ID)
        logger.debug(f"JWT USER ID = {user.id}, EXTERNAL USER ID = {user.external_user_id}")
        
        from models import UserCredits
        user_credits_query = db.query(UserCredits).filter(
            UserCredits.user_id == user.external_user_id
        )
        user_credits = user_credits_query.first()
        
        # Calculate available credits
        if user_credits:
            current_balance = max(0, user_credits.total_credits - user_credits.used_credits)
        else:
            current_balance = 0
        
        # Get credit transactions for user - Use external_user_id (canonical ID)
        from models import CreditTransaction
        query = db.query(CreditTransaction).filter(
            CreditTransaction.user_id == user.external_user_id
        )
        
        # Get total count before pagination
        total = query.count()
        logger.debug(f"ROW COUNT = {total}")
        
        # Calculate pagination
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        
        # Apply pagination
        offset = (page - 1) * limit
        transactions = query.order_by(CreditTransaction.created_at.desc()).offset(offset).limit(limit).all()
        
        logger.info(f"[Credit Transactions] Found {len(transactions)} transactions for external_user_id={user.external_user_id}, page={page}, limit={limit}")
        
        # Format credit transactions with running balance
        # We need to calculate balance backwards from current balance
        # For pagination, we need to calculate balance from the FIRST transaction on the page
        # This requires getting all transactions up to the current page to calculate running balance correctly
        # However, for performance, we'll calculate balance from the start of the page
        # This means balance_after might not be 100% accurate for paginated results, but it's acceptable for UX
        
        # Get all transactions up to current page to calculate accurate running balance
        all_transactions_up_to_page = db.query(CreditTransaction).filter(
            CreditTransaction.user_id == user.external_user_id
        ).order_by(CreditTransaction.created_at.desc()).limit(offset + limit).all()
        
        # Calculate running balance from the end (most recent)
        running_balance = current_balance
        balance_map = {}  # Map transaction ID to balance_after
        
        for txn in reversed(all_transactions_up_to_page):
            if txn.type == 'credit':
                balance_after = running_balance
                running_balance -= txn.credits
            else:  # debit
                balance_after = running_balance
                running_balance += txn.credits
            balance_map[txn.id] = balance_after
            
        transaction_list = []
        for txn in transactions:
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
                balance_after=balance_map.get(txn.id, current_balance),
                reason=txn.reason or ""
            ))
        
        return CreditTransactionsResponse(
            success=True,
            data=CreditTransactionsData(
                items=transaction_list,
                total=total,
                page=page,
                limit=limit,
                total_pages=total_pages
            ),
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

