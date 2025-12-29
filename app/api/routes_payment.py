import logging
import requests
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.config import INTERNAL_SERVICE_TOKEN
from app.database import get_db
from app.services.payment_service import process_payment_success, create_razorpay_order, get_credit_plans
from app.api.user_dependencies import get_current_user_strict
from app.models import User, PaymentTransaction

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Payment"])


def fetch_user_from_django(request: Request) -> Optional[int]:
    """
    Fetch user ID from Django user profile API as fallback.
    
    Args:
        request: FastAPI Request object (for Authorization header)
        
    Returns:
        Optional[int]: User ID from Django, or None if fetch fails
    """
    try:
        token = request.headers.get("Authorization")
        if not token:
            return None

        resp = requests.get(
            "https://trade-api.cryptoarth.in/auth/user/",
            headers={"Authorization": token},
            timeout=5,
        )

        if resp.status_code != 200:
            return None

        user_data = resp.json()
        user_id = user_data.get("id")
        return user_id if user_id else None
        
    except Exception as e:
        logger.warning(f"Failed to fetch user from Django: {e}")
        return None


class PaymentHistoryItem(BaseModel):
    """Payment history item"""
    id: int
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    amount: float
    credits_added: Optional[int] = None
    status: str
    provider: str
    created_at: Optional[str] = None


class PaymentHistoryData(BaseModel):
    """Paginated payment history data"""
    items: List[PaymentHistoryItem]
    total: int
    page: int
    limit: int
    total_pages: int


class PaymentHistoryResponse(BaseModel):
    """Response model for GET /payment/history"""
    success: bool
    data: PaymentHistoryData
    message: Optional[str] = None


# All user dependencies use get_current_user_strict from user_dependencies


@router.post("/payment/create-order")
def create_order(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_strict),
):
    """Create a Razorpay order for credit purchase."""
    plan_id = payload.get("plan_id")
    
    if not plan_id:
        raise HTTPException(
            status_code=400,
            detail="plan_id is required"
        )
    
    try:
        result = create_razorpay_order(plan_id=plan_id, user_id=user.id)
        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Failed to create order")
            )
        return result
    except (ValueError, RuntimeError) as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to create payment order"
        )


@router.post("/payment/verify")
def verify_payment(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    """Verify payment and add credits to user."""
    order_id = payload.get("order_id")
    payment_id = payload.get("payment_id")
    signature = payload.get("signature", "")
    amount = payload.get("amount")

    if not order_id or not payment_id:
        raise HTTPException(
            status_code=400,
            detail="order_id and payment_id are required"
        )

    try:
        # Try to resolve user_id from JWT first
        user = None
        try:
            user = get_current_user_strict(request, request.headers.get("Authorization"), db)
        except Exception:
            user = None

        if not user:
            user_id = fetch_user_from_django(request)
        else:
            user_id = user.id

        if not user_id:
            raise HTTPException(status_code=401, detail="Unable to resolve user")
        
        # CRITICAL: Call with positional arguments only (no keyword args)
        # Function signature: process_payment_success(db, order_id, payment_id, signature, user_id, amount)
        # Using tuple unpacking to ensure positional-only call
        args = (db, order_id, payment_id, signature, user_id, amount)
        result = process_payment_success(*args)
        
        # CRITICAL: Log response to verify user_id in response
        logger.info(f"VERIFY PAYMENT RESPONSE: result.user_id={result.get('user_id')}, expected={user_id}")
        print(f"VERIFY PAYMENT RESPONSE: result.user_id={result.get('user_id')}, expected={user_id}")
        
        return result
        
    except HTTPException:
        # IMPORTANT: propagate correct HTTP status
        raise

    except Exception as e:
        logger.error(f"Payment verification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Payment verification failed"
        )


# ============================================================================
# ============================================================================
# TEMP INTERNAL ENDPOINT - REMOVE AFTER DJANGO + FASTAPI MERGE
# ============================================================================
# ============================================================================
# This endpoint is a TEMPORARY bridge for Django backend to call FastAPI
# payment processing. Django has authenticated user, so it passes user_id to FastAPI.
# 
# CRITICAL: This is TEMPORARY until backends are merged and JWT flows directly to FastAPI.
# 
# REMOVAL INSTRUCTIONS:
# 1. After backend merge, delete this entire endpoint (lines below this marker)
# 2. Remove InternalPaymentVerifyPayload model
# 3. Remove INTERNAL_SERVICE_TOKEN from config.py
# 4. Update Django to call FastAPI directly with JWT
# ============================================================================
# ============================================================================

class InternalPaymentVerifyPayload(BaseModel):
    """Request model for internal payment verification (Django → FastAPI)"""
    user_id: int = Field(..., description="Authenticated user ID from Django backend")
    razorpay_order_id: str = Field(..., description="Razorpay order ID")
    razorpay_payment_id: str = Field(..., description="Razorpay payment ID")
    razorpay_signature: str = Field(..., description="Razorpay signature")
    amount: float = Field(..., description="Payment amount in INR")


@router.post("/payment/verify-internal")
def verify_payment_internal(
    payload: InternalPaymentVerifyPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    TEMPORARY: Internal endpoint for Django backend to verify payments.
    
    This endpoint is protected by INTERNAL_SERVICE_TOKEN and is only called
    by Django backend after Razorpay verification succeeds.
    
    CRITICAL RULES:
    - user_id comes from Django authenticated user (trusted internal call)
    - NO User table query in FastAPI
    - NO frontend user_id trust
    - Reuses existing process_payment_success logic
    
    Args:
        payload: InternalPaymentVerifyPayload with user_id and payment details
        request: FastAPI Request object (for Authorization header)
        db: Database session
    
    Returns:
        dict: {
            "success": bool,
            "user_id": int,
            "credits_added": int,
            "credits_remaining": int,
            "message": str
        }
    """
    # CRITICAL: Validate INTERNAL_SERVICE_TOKEN (STRICT)
    # Token must be configured - fail fast if missing
    if not INTERNAL_SERVICE_TOKEN:
        logger.error("INTERNAL_SERVICE_TOKEN not configured - internal endpoint disabled")
        raise HTTPException(
            status_code=503,
            detail="Internal service token not configured"
        )
    
    # Validate Authorization header exists and matches token
    auth = request.headers.get("Authorization")
    if not auth or auth != f"Bearer {INTERNAL_SERVICE_TOKEN}":
        logger.warning(f"Unauthorized internal call attempt - invalid or missing token")
        raise HTTPException(
            status_code=403,
            detail="Unauthorized internal call"
        )
    
    # CRITICAL: Validate user_id is positive
    if payload.user_id <= 0:
        logger.error(f"Invalid user_id={payload.user_id} in internal payment verify")
        raise HTTPException(
            status_code=400,
            detail="Invalid user_id"
        )
    
    # CRITICAL: Use user_id from Django (trusted internal call)
    # DO NOT query User table - user_id is trusted from Django authenticated user
    user_id = payload.user_id
    
    logger.info(f"🔐 INTERNAL PAYMENT VERIFY: user_id={user_id}, order_id={payload.razorpay_order_id}, payment_id={payload.razorpay_payment_id}")
    
    try:
        # Reuse existing payment processing logic
        # CRITICAL: Call with positional arguments only (no keyword args)
        # Function signature: process_payment_success(db, order_id, payment_id, signature, user_id, amount)
        args = (
            db,
            payload.razorpay_order_id,
            payload.razorpay_payment_id,
            payload.razorpay_signature,
            user_id,
            payload.amount
        )
        result = process_payment_success(*args)
        
        logger.info(f"✅ INTERNAL PAYMENT VERIFY SUCCESS: user_id={user_id}, credits_added={result.get('credits_added', 0)}")
        
        return result
        
    except HTTPException:
        # Re-raise HTTPException as-is
        raise
    except Exception as e:
        logger.error(f"❌ INTERNAL PAYMENT VERIFY ERROR: user_id={user_id}, error={e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal payment verification failed"
        )


@router.post("/payment/webhook")
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Razorpay webhook handler.
    Processes payment events from Razorpay.
    """
    try:
        payload = await request.json()
        
        # Extract payment details from webhook payload
        event = payload.get("event")
        payment_data = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_data = payload.get("payload", {}).get("order", {}).get("entity", {})
        
        if event != "payment.captured":
            # Not a payment success event, return 200 to acknowledge receipt
            return {"success": True, "message": "Event ignored"}
        
        payment_id = payment_data.get("id")
        order_id = order_data.get("id") or payment_data.get("order_id")
        amount = payment_data.get("amount", 0) / 100  # Convert from paise to INR
        signature = payload.get("payload", {}).get("payment", {}).get("entity", {}).get("signature", "")
        
        if not payment_id or not order_id:
            return {"success": False, "message": "Missing payment_id or order_id"}
        
        # Try to get user_id from order notes or Redis
        user_id = None
        try:
            # Try to get from order notes
            notes = order_data.get("notes", {})
            if "uid" in notes:
                user_id = int(notes["uid"])
        except (ValueError, KeyError):
            pass
        
        # If user_id not found, try Redis
        if not user_id:
            try:
                from app.store.redis_client import redis_client
                import json
                order_key = f"PAYMENT_ORDER:{order_id}"
                order_data_str = redis_client.get(order_key)
                if order_data_str:
                    order_meta = json.loads(order_data_str)
                    user_id = int(order_meta.get("user_id", 0))
            except Exception:
                pass
        
        if not user_id or user_id <= 0:
            return {"success": False, "message": "Invalid user_id from webhook"}
        
        # Process payment success
        try:
            args = (db, order_id, payment_id, signature, user_id, amount)
            result = process_payment_success(*args)
            return result
        except Exception as e:
            # Always return 200 to Razorpay to prevent retries
            return {"success": False, "message": f"Payment processing failed: {str(e)}"}
            
    except Exception as e:
        # Always return 200 to Razorpay to prevent retries
        return {"success": False, "message": f"Webhook processing failed: {str(e)}"}


@router.get("/payment/history")
def get_payment_history(
    page: int = 1,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_strict),
):
    """Get paginated payment history for the authenticated user."""
    try:
        # Validate pagination params
        page = max(1, page)
        limit = max(1, min(limit, 100))  # Cap at 100 per page
        
        # CRITICAL: Business tables store external_user_id in user_id column
        # Use user.external_user_id (canonical ID) NOT user.id (local ID)
        logger.error(f"JWT USER ID = {user.id}, EXTERNAL USER ID = {user.external_user_id}")
        
        query = db.query(PaymentTransaction).filter(
            PaymentTransaction.user_id == user.external_user_id
        )
        
        # Get total count before pagination
        total = query.count()
        logger.error(f"ROW COUNT = {total}")
        
        # Calculate pagination
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        
        # Apply pagination
        offset = (page - 1) * limit
        payments = query.order_by(
            PaymentTransaction.created_at.desc()
        ).offset(offset).limit(limit).all()
        
        logger.info(f"[Payment History] Found {len(payments)} payments for external_user_id={user.external_user_id}, page={page}, limit={limit}")
        
        history = []
        for payment in payments:
            history.append({
                "id": payment.id,
                "order_id": payment.gateway_order_id,
                "payment_id": payment.gateway_payment_id,
                "amount": payment.amount,
                "credits_added": payment.credits_added,
                "status": payment.status,
                "provider": payment.provider,
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
            })
        
        return {
            "success": True,
            "data": {
                "items": history,
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching payment history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch payment history"
        )


@router.get("/payment/plans")
def get_plans():
    """Get available credit plans."""
    return get_credit_plans()
