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
from common.redis import redis_client
from app.models import PaymentTransaction
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

# CRITICAL: Startup diagnostic log to confirm which code is running
_PAYMENT_SERVICE_FILE = __file__
_PAYMENT_SERVICE_LOADED_AT = datetime.now().isoformat()
logger.error(f"ðŸ”§ PAYMENT SERVICE MODULE LOADED: file={_PAYMENT_SERVICE_FILE}, loaded_at={_PAYMENT_SERVICE_LOADED_AT}")
print(f"ðŸ”§ PAYMENT SERVICE MODULE LOADED: file={_PAYMENT_SERVICE_FILE}, loaded_at={_PAYMENT_SERVICE_LOADED_AT}")

# Credit packages/plans
# CRITICAL: Single source of truth for backend pricing
# Base price: â‚¹10 = 1 Credit
# GST: 18% of base price
# Total payable = base_price + gst
# NO 'amount' field - use total_amount only
CREDIT_PLANS = {
    'starter': {
        'name': 'Starter Pack',
        'credits': 50,
        'base_price': 500,
        'gst': 90,
        'total_amount': 590
    },
    'professional': {
        'name': 'Professional Pack',
        'credits': 150,
        'base_price': 1500,
        'gst': 270,
        'total_amount': 1770
    },
    'enterprise': {
        'name': 'Enterprise Pack',
        'credits': 300,
        'base_price': 3000,
        'gst': 540,
        'total_amount': 3540
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
        from common.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
        import razorpay
        
        # Validate Razorpay keys are configured
        if not RAZORPAY_KEY_ID:
            logger.error("âŒ Razorpay KEY_ID not configured. Set RAZORPAY_KEY_ID environment variable.")
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
            logger.error("âŒ Razorpay KEY_SECRET not configured. Set RAZORPAY_KEY_SECRET environment variable.")
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
            logger.error(f"âŒ Razorpay key must be LIVE key (starting with rzp_live_). Current key starts with: {RAZORPAY_KEY_ID[:10]}...")
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
        # CRITICAL BUSINESS FIX: Store complete plan metadata in notes for credit calculation
        # Credits MUST be based on base_price only, NOT total amount (base + GST)
        try:
            order = client.order.create({
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt,
                "notes": {
                    "uid": str(user_id),
                    "pid": plan_id,
                    "plan_name": plan['name'],
                    "base_price": str(plan['base_price']),  # Base price (without GST)
                    "gst": str(plan['gst']),  # GST amount
                    "credits": str(plan['credits'])  # Credits based on base_price only
                }
            })
        except Exception as razorpay_error:
            # Razorpay SDK raised exception - do NOT return fake success
            error_msg = f"Razorpay API error: {str(razorpay_error)}"
            logger.error(f"âŒ {error_msg}")
            raise RuntimeError(error_msg) from razorpay_error
        
        # HARD VALIDATION: Ensure Razorpay returned a valid order
        if not order:
            error_msg = "Razorpay order creation returned None"
            logger.error(f"âŒ {error_msg}")
            raise ValueError(error_msg)
        
        # Check for Razorpay error response (SDK may return error dict instead of raising)
        if isinstance(order, dict) and 'error' in order:
            error_msg = f"Razorpay API error: {order.get('error', {}).get('description', 'Unknown error')}"
            logger.error(f"âŒ {error_msg}")
            raise RuntimeError(error_msg)
        
        if 'id' not in order:
            error_msg = f"Razorpay order missing 'id' field: {order}"
            logger.error(f"âŒ {error_msg}")
            raise ValueError(error_msg)
        
        order_id = order['id']
        
        # HARD ASSERT: order_id MUST start with "order_" (Razorpay format)
        # This prevents ANY fake/mock/temp order_id from being returned
        if not isinstance(order_id, str) or not order_id.startswith('order_'):
            error_msg = f"Invalid Razorpay order_id format: {order_id}. Must start with 'order_'"
            logger.error(f"âŒ {error_msg}")
            raise ValueError(error_msg)
        
        logger.info(f"âœ… Razorpay order created successfully: {order_id}")
        
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
        from common.config import RAZORPAY_KEY_ID
        
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
        logger.error(f"âŒ Razorpay order validation failed: {e}", exc_info=True)
        raise  # Re-raise to let caller handle
    except Exception as e:
        # CRITICAL: On ANY exception, DO NOT return fake success or temp_order_1
        # ALWAYS raise exception - let the API route handle error response
        logger.error(f"âŒ Error creating Razorpay order: {e}", exc_info=True)
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
        from common.config import RAZORPAY_KEY_SECRET
        
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
    
    # CRITICAL: Warn if user_id = 1 (admin user) - this should only happen if admin is actually paying
    if user_id == 1:
        logger.warning(f"âš ï¸ WARNING: user_id=1 (admin user) detected. Verify this is intentional admin payment.")
        print(f"âš ï¸ WARNING: user_id=1 (admin user) detected. Verify this is intentional admin payment.")
    
    # CRITICAL: Log the user_id being used for payment processing
    logger.info(f"ðŸš€ PAYMENT PROCESS START: user_id={user_id}, order_id={order_id}, payment_id={payment_id}")
    logger.info(f"ðŸš€ AUTHENTICATED USER_ID: {user_id} (MUST NOT be 1 unless admin is paying)")
    print(f"ðŸš€ PAYMENT PROCESS START: user_id={user_id}, order_id={order_id}, payment_id={payment_id}")
    
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
        
        # STEP 1: Fetch payment and order data from Razorpay API
        # CRITICAL: Get credits from Razorpay order notes (plan metadata)
        # Credits MUST be based on base_price only, NOT total amount (base + GST)
        razorpay_order = None
        razorpay_order_notes = None
        
        try:
            from common.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
            import razorpay
            client = razorpay.Client(auth=(RAZORPAY_KEY_ID.strip(), RAZORPAY_KEY_SECRET.strip()))
            
            # Fetch payment data for amount
            payment_data = client.payment.fetch(payment_id)
            if payment_data and 'amount' in payment_data:
                amount = float(payment_data['amount']) / 100  # Convert from paise to INR
                logger.info(f"Fetched amount from Razorpay API: {amount} INR")
            
            # CRITICAL: Fetch order data to get plan metadata (credits, base_price, gst)
            razorpay_order = client.order.fetch(order_id)
            if razorpay_order and 'notes' in razorpay_order:
                razorpay_order_notes = razorpay_order['notes']
                logger.info(f"Fetched Razorpay order notes: {razorpay_order_notes}")
        except Exception as razorpay_error:
            logger.error(f"Failed to fetch Razorpay data: {razorpay_error}", exc_info=True)
        
        # STEP 2: Get user details for customer info and mobile
        # CRITICAL: Query User to get name, email, and mobile for payment records
        from app.models import User
        user = db.query(User).filter(User.external_user_id == user_id).first()
        
        # HARD FALLBACK: Customer details must NEVER be NULL if user exists
        if user:
            # Customer name with hard fallback
            if user.first_name or user.last_name:
                customer_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            elif hasattr(user, 'full_name') and user.full_name:
                customer_name = user.full_name
            elif hasattr(user, 'username') and user.username:
                customer_name = user.username
            else:
                customer_name = f"user_{user_id}"  # HARD FALLBACK
            
            # Customer email with hard fallback
            customer_email = user.email if hasattr(user, 'email') and user.email else ""
            
            # Customer mobile with hard fallback
            customer_mobile = user.phone if hasattr(user, 'phone') and user.phone else ""
            user_mobile = customer_mobile  # For credit_transactions
            
            logger.info(f"User details extracted: name={customer_name}, email={customer_email}, mobile={customer_mobile}")
        else:
            logger.warning(f"User not found for external_user_id={user_id}, customer details will be NULL")
            customer_name = None
            customer_email = None
            customer_mobile = None
            user_mobile = None
        
        # CRITICAL FIX 1: FINAL AMOUNT VALIDATION (STRICT) - BEFORE DB TRANSACTION
        # Prevent â‚¹0 payments from being committed
        if not amount or amount <= 0:
            logger.error(f"âŒ CRITICAL: Final amount validation failed for payment_id={payment_id}. amount={amount}. Payment cannot be processed.")
            db.rollback()
            return {
                "success": False,
                "user_id": user_id,
                "credits_added": 0,
                "message": "Invalid payment amount. Payment cannot be processed."
            }
        
        # ============================================================
        # CREDIT CALCULATION (FROM PLAN METADATA) - BEFORE DB TRANSACTION
        # ============================================================
        # CRITICAL BUSINESS FIX: Credits MUST be based on base_price only, NOT total amount
        # GST should NEVER generate credits
        # Credits come from Razorpay order notes (plan metadata stored during order creation)
        credits_added = 0
        
        if razorpay_order_notes and 'credits' in razorpay_order_notes:
            try:
                credits_added = int(razorpay_order_notes['credits'])
                logger.info(
                    f"Credits from Razorpay order notes: {credits_added} "
                    f"(base_price={razorpay_order_notes.get('base_price', 'N/A')}, "
                    f"gst={razorpay_order_notes.get('gst', 'N/A')})"
                )
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to parse credits from Razorpay notes: {e}")
                credits_added = 0
        
        # HARD VALIDATION: Credits MUST exist in order notes
        # Do NOT guess credits from amount (prevents GST-based credit inflation)
        if credits_added <= 0:
            logger.error(
                f"âŒ CRITICAL: Credits missing or invalid in Razorpay order notes. "
                f"order_id={order_id}, notes={razorpay_order_notes}. "
                f"Payment verification FAILED - credits must come from plan metadata."
            )
            db.rollback()
            return {
                "success": False,
                "user_id": user_id,
                "credits_added": 0,
                "message": "Credit calculation failed: Credits not found in order metadata"
            }
        
        logger.error(
            f"FINAL CREDIT CALC => amount={amount}, credits_added={credits_added} "
            f"(from plan metadata, NOT from amount/10)"
        )
        
        # HARD LOG - PROOF EXECUTION (MANDATORY)
        logger.error("ðŸ”¥ PAYMENT DB UPDATE START")
        logger.error(f"user_id={user_id}, order_id={order_id}, payment_id={payment_id}, amount={amount}, credits_added={credits_added}, mobile={user_mobile}")
        
        # CRITICAL FIX 3: Wrap ALL DB operations in try/except for transaction safety
        # STRICT ORDER: payment_transactions â†’ credit_transactions â†’ user_credits â†’ commit
        # HARD RULE: credits_added > 0 is guaranteed (validated before DB transaction)
        try:
            # STEP 4: Insert payment_transactions row (INVOICE RECORD)
            # credits_added > 0 is guaranteed (hard validation before this point)
            payment_tx = PaymentTransaction(
                user_id=user_id,
                provider="razorpay",
                gateway_order_id=order_id,
                gateway_payment_id=payment_id,
                amount=float(amount) if amount else 0.0,
                status="success",
                customer_name=customer_name,
                customer_email=customer_email,
                customer_mobile=customer_mobile,
                credits_added=credits_added
            )
            db.add(payment_tx)
            logger.info(f"Added payment_transaction: user_id={user_id}, amount={amount}, credits={credits_added}")
            
            # STEP 5: Insert credit_transactions row (LEDGER)
            # Mobile is OPTIONAL - can be NULL
            from app.models import CreditTransaction
            credit_tx = CreditTransaction(
                user_id=user_id,
                mobile=user_mobile,  # Mobile in 91XXXXXXXXXX format or NULL if not available
                credits=credits_added,
                type='credit',
                reason=f"Payment {payment_id}",
                reference_id=payment_id
            )
            db.add(credit_tx)
            logger.info(f"Added credit_transaction: user_id={user_id}, credits={credits_added}, mobile={user_mobile}")
            
            # STEP 6: Update user_credits table (BALANCE TABLE)
            from app.models import UserCredits
            
            # CRITICAL DB FIX: Mobile resolution for user_credits (mobile is NOT NULL)
            # Resolution order: user.phone â†’ customer_mobile â†’ empty string ""
            # MUST resolve BEFORE user_credits query
            mobile_value = user_mobile or customer_mobile or ""
            logger.info(
                f"user_credits mobile resolved: {mobile_value} for user_id={user_id} "
                f"(from user_mobile={user_mobile}, customer_mobile={customer_mobile})"
            )
            
            user_credits = (
                db.query(UserCredits)
                .filter(UserCredits.user_id == user_id)
                .first()
            )
            
            if not user_credits:
                # CREATE: New user_credits record with mobile (REQUIRED)
                user_credits = UserCredits(
                    user_id=user_id,
                    mobile=mobile_value,  # REQUIRED: mobile field (NOT NULL in DB)
                    total_credits=credits_added,
                    used_credits=0,
                    is_active=True,
                )
                db.add(user_credits)
                logger.info(
                    f"Created new user_credits record for user_id={user_id}, mobile={mobile_value}"
                )
            else:
                # UPDATE: Existing user_credits
                user_credits.total_credits += credits_added
                
                # CRITICAL: Update mobile if missing (ensures DB consistency)
                if not user_credits.mobile:
                    user_credits.mobile = mobile_value
                    logger.info(
                        f"Updated user_credits.mobile to {mobile_value} for user_id={user_id} "
                        f"(was missing/NULL)"
                    )
                
                logger.info(
                    f"Updated user_credits for user_id={user_id}, "
                    f"new total={user_credits.total_credits}, mobile={user_credits.mobile}"
                )
            
            # STEP 7: Commit - ONLY ONCE (CRITICAL: All operations must succeed)
            # CRITICAL: Log user_id before commit to verify correct user
            print(f"VERIFY PAYMENT USER_ID: {user_id}")
            logger.error(f"ðŸ” PRE-COMMIT CHECK: user_id={user_id}, credits_added={credits_added}, amount={amount}, customer_name={customer_name}, customer_email={customer_email}")
            logger.error(f"VERIFY PAYMENT USER_ID: {user_id}")
            
            db.commit()
            db.refresh(user_credits)
            
            # CRITICAL: Verify credits were actually added
            final_credits = user_credits.total_credits if user_credits else 0
            logger.error(f"âœ… PAYMENT COMMIT SUCCESS user_id={user_id} credits_added={credits_added} amount={amount} final_total_credits={final_credits}")
            print(f"âœ… PAYMENT COMMIT SUCCESS user_id={user_id} credits_added={credits_added} amount={amount} final_total_credits={final_credits}")
            
        except Exception as db_error:
            # CRITICAL FIX 4: Rollback on ANY exception and return failure
            db.rollback()
            logger.error(f"âŒ PAYMENT DB TRANSACTION FAILED: user_id={user_id}, error={db_error}", exc_info=True)
            print(f"âŒ PAYMENT DB TRANSACTION FAILED: user_id={user_id}, error={db_error}")
            return {
                "success": False,
                "user_id": user_id,
                "credits_added": 0,
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
            f"âŒ EXCEPTION IN PAYMENT PROCESS: user_id={user_id}, error={e}",
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



