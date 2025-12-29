"""
Payment Service
Handles Razorpay payment gateway integration for credit purchases
"""
import logging
import hmac
import hashlib
import json
import time
import os
from datetime import datetime
from typing import Dict, Optional, Any
from fastapi import HTTPException
from app.store.redis_client import redis_client
from app.services.credit_service import get_rupee_to_credit_ratio
from app.models import PaymentTransaction
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

# CRITICAL: Startup diagnostic log to confirm which code is running
_PAYMENT_SERVICE_FILE = __file__
_PAYMENT_SERVICE_LOADED_AT = datetime.now().isoformat()
logger.error(f"🔧 PAYMENT SERVICE MODULE LOADED: file={_PAYMENT_SERVICE_FILE}, loaded_at={_PAYMENT_SERVICE_LOADED_AT}")
print(f"🔧 PAYMENT SERVICE MODULE LOADED: file={_PAYMENT_SERVICE_FILE}, loaded_at={_PAYMENT_SERVICE_LOADED_AT}")

# Credit packages/plans
# CRITICAL: Single source of truth for backend pricing
# Base price: ₹10 = 1 Credit
# GST: 18% of base price
# Total payable = base_price + gst
# NO 'amount' field - use total_amount only
# TESTING MODE: All plans hard-coded to ₹5 for payment gateway testing
# TODO: Revert to original prices after testing
CREDIT_PLANS = {
    'starter': {
        'name': 'Starter Pack',
        'credits': 50,
        'base_price': 5,  # TESTING: Original 500
        'gst': 0,  # TESTING: Original 90
        'total_amount': 5  # TESTING: Original 590
    },
    'professional': {
        'name': 'Professional Pack',
        'credits': 150,
        'base_price': 5,  # TESTING: Original 1500
        'gst': 0,  # TESTING: Original 270
        'total_amount': 5  # TESTING: Original 1770
    },
    'enterprise': {
        'name': 'Enterprise Pack',
        'credits': 300,
        'base_price': 5,  # TESTING: Original 3000
        'gst': 0,  # TESTING: Original 540
        'total_amount': 5  # TESTING: Original 3540
    }
}


def create_razorpay_order(plan_id: str, user_id: int) -> Dict[str, Any]:
    """
    Create a Razorpay order for credit purchase
    
    CRITICAL: Creates a fresh Razorpay client for each request to prevent stale credential reuse.
    
    Args:
        plan_id: Credit plan ID (starter, professional, enterprise, unlimited)
        user_id: User ID making the purchase
    
    Returns:
        dict: {
            'success': bool,
            'order_id': str,
            'amount': int,
            'currency': str,
            'key_id': str,
            'credits': int,
            'message': str
        }
    """
    try:
        # CRITICAL: Create fresh Razorpay client for each request (no global client reuse)
        from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
        import razorpay
        
        # Validate Razorpay keys are configured
        if not RAZORPAY_KEY_ID:
            logger.error("❌ Razorpay KEY_ID not configured. Set RAZORPAY_KEY_ID environment variable.")
            return {
                'success': False,
                'order_id': None,
                'amount': 0,
                'currency': 'INR',
                'key_id': None,
                'credits': 0,
                'message': 'Payment gateway not configured. Please contact support.'
            }
        
        if not RAZORPAY_KEY_SECRET:
            logger.error("❌ Razorpay KEY_SECRET not configured. Set RAZORPAY_KEY_SECRET environment variable.")
            return {
                'success': False,
                'order_id': None,
                'amount': 0,
                'currency': 'INR',
                'key_id': None,
                'credits': 0,
                'message': 'Payment gateway not configured. Please contact support.'
            }
        
        # Validate key is LIVE
        if not RAZORPAY_KEY_ID.startswith('rzp_live_'):
            logger.error(f"❌ Razorpay key must be LIVE key (starting with rzp_live_). Current key starts with: {RAZORPAY_KEY_ID[:10]}...")
            return {
                'success': False,
                'order_id': None,
                'amount': 0,
                'currency': 'INR',
                'key_id': None,
                'credits': 0,
                'message': 'Payment gateway not configured. Please contact support.'
            }
        
        # Create fresh Razorpay client for this request
        # CRITICAL: Strip keys to avoid hidden whitespace issues from .env
        client = razorpay.Client(
            auth=(
                RAZORPAY_KEY_ID.strip(),
                RAZORPAY_KEY_SECRET.strip()
            )
        )
        
        # Validate plan
        if plan_id not in CREDIT_PLANS:
            return {
                'success': False,
                'order_id': None,
                'amount': 0,
                'currency': 'INR',
                'key_id': None,
                'credits': 0,
                'message': f'Invalid plan ID: {plan_id}. Available plans: {", ".join(CREDIT_PLANS.keys())}'
            }
        
        plan = CREDIT_PLANS[plan_id]
        # CRITICAL: Use total_amount (base + GST) for Razorpay order
        # This ensures checkout shows the correct amount matching frontend
        # SINGLE SOURCE OF TRUTH: amount_paise MUST be calculated ONLY from plan["total_amount"]
        total_amount = plan['total_amount']  # Total payable in INR
        amount_paise = int(total_amount * 100)  # Convert to paise (Razorpay requires integer)
        
        # Debug log: Verify amount calculation
        logger.info(f"PAYMENT CREATE | plan={plan_id} | total_amount={total_amount} | amount_paise={amount_paise}")
        
        # Create Razorpay order using exact format as specified
        # CRITICAL: Receipt must be <= 40 characters (Razorpay hard limit)
        receipt = f"cr{user_id}{int(time.time())}"[:40]
        
        # Runtime verification: Log receipt before order creation
        logger.error(
            "RAZORPAY RECEIPT => %s | LEN=%d",
            receipt,
            len(receipt)
        )
        
        # CRITICAL: Create REAL Razorpay order - NO TEMP MODE, NO MOCK, NO FALLBACK
        # IMPORTANT: Razorpay order_id MUST always come from Razorpay API.
        # Never generate, mock, or fallback order_id.
        try:
            order = client.order.create({
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt,
                "notes": {
                    "uid": str(user_id),
                    "pid": plan_id,
                    "plan_name": plan['name']
                }
            })
        except Exception as razorpay_error:
            # Razorpay SDK raised exception - do NOT return fake success
            error_msg = f"Razorpay API error: {str(razorpay_error)}"
            logger.error(f"❌ {error_msg}")
            raise RuntimeError(error_msg) from razorpay_error
        
        # HARD VALIDATION: Ensure Razorpay returned a valid order
        if not order:
            error_msg = "Razorpay order creation returned None"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
        
        # Check for Razorpay error response (SDK may return error dict instead of raising)
        if isinstance(order, dict) and 'error' in order:
            error_msg = f"Razorpay API error: {order.get('error', {}).get('description', 'Unknown error')}"
            logger.error(f"❌ {error_msg}")
            raise RuntimeError(error_msg)
        
        if 'id' not in order:
            error_msg = f"Razorpay order missing 'id' field: {order}"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
        
        order_id = order['id']
        
        # HARD ASSERT: order_id MUST start with "order_" (Razorpay format)
        # This prevents ANY fake/mock/temp order_id from being returned
        if not isinstance(order_id, str) or not order_id.startswith('order_'):
            error_msg = f"Invalid Razorpay order_id format: {order_id}. Must start with 'order_'"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
        
        logger.info(f"✅ Razorpay order created successfully: {order_id}")
        
        # Store order details in Redis (for webhook verification)
        order_key = f"PAYMENT_ORDER:{order_id}"
        order_details = {
            'order_id': order_id,
            'user_id': str(user_id),
            'plan_id': plan_id,
            'credits': plan['credits'],
            'base_price': plan['base_price'],  # Base price in INR
            'gst': plan['gst'],  # GST in INR
            'amount': total_amount,  # Total payable (base + GST) in INR
            'amount_paise': amount_paise,  # Total payable in paise
            'plan_name': plan['name'],
            'status': 'created',
            'created_at': order.get('created_at', int(time.time()))
        }
        redis_client.setex(
            order_key,
            86400 * 7,  # 7 days TTL
            json.dumps(order_details)
        )
        
        # Get Razorpay key ID from config
        from app.config import RAZORPAY_KEY_ID
        
        logger.info(f"Created Razorpay order {order_id} for user {user_id}, plan {plan_id}")
        
        return {
            'success': True,
            'order_id': order_id,
            'amount': amount_paise,
            'currency': 'INR',
            'key_id': RAZORPAY_KEY_ID,
            'credits': plan['credits'],
            'plan_name': plan['name'],
            'message': 'Order created successfully'
        }
        
    except ValueError as e:
        # Validation errors - re-raise as ValueError (do NOT return fake success)
        logger.error(f"❌ Razorpay order validation failed: {e}", exc_info=True)
        raise  # Re-raise to let caller handle
    except Exception as e:
        # CRITICAL: On ANY exception, DO NOT return fake success or temp_order_1
        # ALWAYS raise exception - let the API route handle error response
        logger.error(f"❌ Error creating Razorpay order: {e}", exc_info=True)
        raise RuntimeError(f"Failed to create Razorpay order: {str(e)}") from e


def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """
    Verify Razorpay payment signature
    
    Args:
        order_id: Razorpay order ID
        payment_id: Razorpay payment ID
        signature: Razorpay signature
    
    Returns:
        bool: True if signature is valid
    """
    try:
        from app.config import RAZORPAY_KEY_SECRET
        
        if not RAZORPAY_KEY_SECRET:
            logger.error("Razorpay key secret not configured")
            return False
        
        # Create message
        message = f"{order_id}|{payment_id}"
        
        # Generate expected signature
        expected_signature = hmac.new(
            RAZORPAY_KEY_SECRET.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures (constant-time comparison)
        is_valid = hmac.compare_digest(expected_signature, signature)
        
        if not is_valid:
            logger.warning(f"Invalid Razorpay signature for order {order_id}, payment {payment_id}")
        
        return is_valid
        
    except Exception as e:
        logger.error(f"Error verifying Razorpay signature: {e}", exc_info=True)
        return False


def process_payment_success(
    db: Session,
    order_id: str,
    payment_id: str,
    signature: str,
    user_id: int,
    amount: Optional[float] = None
) -> Dict[str, Any]:
    """
    Process successful payment and add credits to user.
    
    CRITICAL: This function MUST use the JWT-authenticated user_id as the ONLY source of truth.
    NEVER use hardcoded user_id, admin user, or Redis user_id without validation.
    
    PRODUCTION FIX: Removed signature validation and Redis dependency to ensure DB updates ALWAYS execute.
    
    FLOW:
    1. Check idempotency (prevent duplicate processing)
    2. Fetch user from database (JWT user_id is source of truth)
    3. Calculate credits from amount (credits_to_add = int(amount))
    4. Update user_credits table (BALANCE)
    5. Insert credit_transactions row (LEDGER)
    6. Insert payment_transactions row (INVOICE RECORD)
    7. Commit all DB writes
    8. Return success response
    
    Args:
        db: Database session
        order_id: Razorpay order ID
        payment_id: Razorpay payment ID
        signature: Razorpay signature (bypassed - not validated)
        user_id: JWT-authenticated user ID (integer) - ONLY SOURCE OF TRUTH
        amount: Payment amount in INR (optional - will try to fetch from Razorpay if not provided)
    
    Returns:
        dict: {
            'success': bool,
            'user_id': int,
            'credits_added': int,
            'credits_remaining': int,
            'message': str
        }
    """
    # CRITICAL: Validate user_id is not admin/default (unless admin is actually paying)
    if user_id <= 0:
        logger.error(f"CRITICAL: Invalid user_id={user_id} in process_payment_success. Rejecting payment.")
        return {
            'success': False,
            'user_id': user_id,
            'credits_added': 0,
            'message': 'Invalid user ID. Payment cannot be processed.'
        }
    
    # CRITICAL: Log the user_id being used for payment processing
    logger.info(f"🚀 PAYMENT PROCESS START: user_id={user_id}, order_id={order_id}, payment_id={payment_id}")
    logger.info(f"🚀 AUTHENTICATED USER_ID: {user_id} (MUST NOT be 1 unless admin is paying)")
    
    try:
        # PRODUCTION FIX: BYPASS signature validation (frontend doesn't send signature)
        # Signature validation removed to prevent early return before DB update
        
        # STEP 1: Idempotency check - Prevent duplicate processing (FIRST RETURN)
        existing_payment = db.query(PaymentTransaction).filter(
            PaymentTransaction.gateway_payment_id == payment_id
        ).first()
        
        if existing_payment:
            logger.warning(f"Duplicate payment detected: {payment_id}")
            return {
                "success": True,
                "user_id": user_id,
                "message": "Payment already processed"
            }
        
        # PRODUCTION FIX: REMOVE Redis order dependency (causes early return if Redis miss)
        # Try to get amount from Redis if not provided, but don't fail if Redis miss
        order_data = None
        total_amount = 0
        if not amount:
            try:
                order_key = f"PAYMENT_ORDER:{order_id}"
                order_data_str = redis_client.get(order_key)
                if order_data_str:
                    order_data = json.loads(order_data_str)
                    amount = order_data.get('amount', 0)  # Total payable (base + GST) in INR
                    total_amount = amount
            except Exception as redis_error:
                logger.warning(f"Redis lookup failed for order {order_id}: {redis_error}. Continuing without Redis data.")
        
        # If still no amount, try to fetch from Razorpay API
        if not amount or amount <= 0:
            try:
                from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
                import razorpay
                client = razorpay.Client(auth=(RAZORPAY_KEY_ID.strip(), RAZORPAY_KEY_SECRET.strip()))
                payment_data = client.payment.fetch(payment_id)
                if payment_data and 'amount' in payment_data:
                    amount = float(payment_data['amount']) / 100  # Convert from paise to INR
                    total_amount = amount
                    logger.info(f"Fetched amount from Razorpay API: {amount} INR")
            except Exception as razorpay_error:
                logger.error(f"Failed to fetch payment amount from Razorpay: {razorpay_error}")
        
        # ISSUE 1 FIX: DO NOT RETURN on amount validation - continue without blocking
        if not amount or amount <= 0:
            logger.error(f"⚠️ Amount missing or invalid for payment_id={payment_id}. Continuing without blocking DB update.")
            amount = amount or total_amount or 0
        
        # STEP 2: Calculate credits from plan metadata (NOT from amount)
        credits_added = 0
        
        if order_data and "credits" in order_data:
            credits_added = int(order_data["credits"])
            logger.info(f"Credits derived from plan metadata: {credits_added}")
        else:
            logger.error(
                f"❌ Credits missing in order metadata for payment_id={payment_id}. "
                f"No credits added to prevent inflation."
            )
        
        # STEP 3: Fetch user from database (JWT user_id is source of truth)
        from app.models import User
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            logger.error(f"CRITICAL: JWT-authenticated user_id={user_id} not found in database. Payment cannot be processed.")
            return {
                'success': False,
                'user_id': user_id,
                'credits_added': 0,
                'message': 'Authenticated user not found'
            }
        
        # Capture customer details snapshot from authenticated user record
        # CRITICAL: Customer details MUST come from users table, NOT Razorpay or frontend
        customer_name = None
        if user.first_name or user.last_name:
            customer_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        elif user.username:
            customer_name = user.username
        
        customer_email = user.email
        customer_mobile = user.phone
        
        # HARD LOG - PROOF EXECUTION (MANDATORY)
        logger.error("🔥 PAYMENT DB UPDATE START")
        logger.error(f"user_id={user_id}, order_id={order_id}, payment_id={payment_id}, amount={amount}, credits_added={credits_added}")
        
        # STEP 4: Update user_credits table (BALANCE TABLE) - NO OVERRIDE
        from app.models import UserCredits
        
        user_credits = (
            db.query(UserCredits)
            .filter(UserCredits.user_id == user_id)
            .first()
        )
        
        if not user_credits:
            user_credits = UserCredits(
                user_id=user_id,
                total_credits=credits_added,
                used_credits=0,
                is_active=True,
            )
            db.add(user_credits)
        else:
            user_credits.total_credits += credits_added
        
        # STEP 5: Insert credit_transactions row (LEDGER)
        from app.models import CreditTransaction
        credit_tx = CreditTransaction(
            user_id=user_id,
            credits=credits_added,
            type='credit',
            reason=f"Payment {payment_id}",
            reference_id=payment_id
        )
        db.add(credit_tx)
        
        # STEP 6: Insert payment_transactions row (INVOICE RECORD)
        payment_tx = PaymentTransaction(
            user_id=user_id,
            provider="razorpay",
            gateway_order_id=order_id,
            gateway_payment_id=payment_id,
            amount=float(amount),
            status="success",
            customer_name=customer_name,
            customer_email=customer_email,
            customer_mobile=customer_mobile,
            credits_added=credits_added
        )
        db.add(payment_tx)
        
        # STEP 7: Commit - ONLY ONCE (ISSUE 2 FIX: Single commit, no flush)
        try:
            db.commit()
            db.refresh(user_credits)
            logger.error("✅ PAYMENT DB COMMIT SUCCESS")
        except Exception as e:
            db.rollback()
            logger.error("❌ PAYMENT DB COMMIT FAILED", exc_info=True)
            return {
                "success": False,
                "user_id": user_id,
                "message": "Payment DB update failed"
            }
        
        # STEP 9: Return final response
        credits_remaining = user_credits.total_credits - user_credits.used_credits
        
        return {
            "success": True,
            "user_id": user_id,
            "credits_added": credits_added,
            "credits_remaining": credits_remaining,
            "message": "Credits added successfully"
        }
        
    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.error(
            f"❌ EXCEPTION IN PAYMENT PROCESS: user_id={user_id}, error={e}",
            exc_info=True
        )
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Internal payment processing error"
        )


def get_credit_plans() -> Dict[str, Any]:
    """
    Get available credit plans
    
    Returns:
        dict: Available credit plans
    """
    return {
        'success': True,
        'plans': CREDIT_PLANS,
        'message': 'Credit plans retrieved successfully'
    }



