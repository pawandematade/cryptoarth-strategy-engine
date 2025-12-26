"""
Payment Service
Handles Razorpay payment gateway integration for credit purchases
"""
import logging
import hmac
import hashlib
import json
import time
from typing import Dict, Optional, Any
from app.store.redis_client import redis_client
from app.services.credit_service import get_rupee_to_credit_ratio
from app.models import PaymentTransaction
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

# Credit packages/plans
# CRITICAL: Single source of truth for backend pricing
# Base price: ₹10 = 1 Credit
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
        
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "notes": {
                "uid": str(user_id),
                "pid": plan_id
            }
        })
        
        if not order or 'id' not in order:
            logger.error(f"Failed to create Razorpay order: {order}")
            return {
                'success': False,
                'order_id': None,
                'amount': 0,
                'currency': 'INR',
                'key_id': None,
                'credits': 0,
                'message': 'Failed to create payment order. Please try again.'
            }
        
        order_id = order['id']
        
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
        
    except Exception as e:
        logger.error(f"Error creating Razorpay order: {e}", exc_info=True)
        return {
            'success': False,
            'order_id': None,
            'amount': 0,
            'currency': 'INR',
            'key_id': None,
            'credits': 0,
            'message': f'Error creating payment order: {str(e)}'
        }


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
    user_id: int
) -> Dict[str, Any]:
    """
    Process successful payment and add credits to user.
    
    CRITICAL: This function MUST use the JWT-authenticated user_id as the ONLY source of truth.
    NEVER use hardcoded user_id, admin user, or Redis user_id without validation.
    
    FLOW:
    1. Verify Razorpay signature
    2. Fetch order from Redis and validate
    3. Check idempotency (prevent duplicate processing)
    4. Calculate credits from base_price
    5. Update user_credits table (BALANCE)
    6. Insert credit_transactions row (LEDGER)
    7. Insert payment_transactions row (INVOICE RECORD)
    8. Return success response
    
    Args:
        db: Database session
        order_id: Razorpay order ID
        payment_id: Razorpay payment ID
        signature: Razorpay signature
        user_id: JWT-authenticated user ID (integer) - ONLY SOURCE OF TRUTH
    
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
    logger.info(f"PAYMENT PROCESS START: user_id={user_id}, order_id={order_id}, payment_id={payment_id}")
    
    try:
        # STEP 1: Verify Razorpay signature
        if not verify_razorpay_signature(order_id, payment_id, signature):
            logger.error(f"Invalid Razorpay signature for payment {payment_id}")
            return {
                'success': False,
                'user_id': user_id,
                'credits_added': 0,
                'message': 'Invalid payment signature. Payment verification failed.'
            }
        
        # STEP 2: Get order details from Redis and validate
        order_key = f"PAYMENT_ORDER:{order_id}"
        order_data_str = redis_client.get(order_key)
        
        if not order_data_str:
            logger.error(f"Order {order_id} not found in Redis")
            return {
                'success': False,
                'user_id': user_id,
                'credits_added': 0,
                'message': 'Order not found. Payment may have expired.'
            }
        
        order_data = json.loads(order_data_str)
        
        # STEP 3: Idempotency check - Prevent duplicate processing
        existing_payment = db.query(PaymentTransaction).filter(
            PaymentTransaction.gateway_payment_id == payment_id,
            PaymentTransaction.status == 'success'
        ).first()
        
        if existing_payment:
            logger.info(f"Payment {payment_id} already processed (idempotency check). Returning existing result.")
            # CRITICAL: Verify existing payment belongs to authenticated user
            if existing_payment.user_id != user_id:
                logger.error(f"Payment {payment_id} belongs to user_id={existing_payment.user_id}, but authenticated user_id={user_id}. Security violation.")
                return {
                    'success': False,
                    'user_id': user_id,
                    'credits_added': 0,
                    'message': 'Payment ownership mismatch. Security violation.'
                }
            
            # Get updated user credits for response
            from app.services.credit_service import get_user_credits
            user_credits = get_user_credits(db, user_id)
            credits_remaining = user_credits.available_credits if user_credits else 0
            
            return {
                'success': True,
                'user_id': user_id,
                'credits_added': existing_payment.credits_added,
                'credits_remaining': credits_remaining,
                'message': 'Payment already processed (idempotent response)'
            }
        
        # STEP 4: Calculate credits from base_price (₹10 = 1 credit)
        # CRITICAL: Credits are calculated from base_price, NOT total_amount (GST excluded)
        base_price = order_data.get('base_price', 0)  # Base price in INR (GST excluded)
        if base_price == 0:
            # Fallback to amount for backward compatibility (old orders)
            base_price = order_data.get('amount', 0)
        ratio = get_rupee_to_credit_ratio(db)  # Default: 10
        credits_added = int(base_price / ratio) if ratio > 0 else 0
        
        if credits_added <= 0:
            logger.error(f"Invalid credits calculation: base_price={base_price}, ratio={ratio}, credits={credits_added}")
            return {
                'success': False,
                'user_id': user_id,
                'credits_added': 0,
                'message': 'Invalid credit calculation. Payment cannot be processed.'
            }
        
        # Get total amount for payment transaction record
        total_amount = order_data.get('amount', 0)  # Total payable (base + GST) in INR
        
        # STEP 5: Get authenticated user from database (CRITICAL: JWT user is source of truth)
        from app.models import User
        current_user = db.query(User).filter(User.id == user_id).first()
        
        if not current_user:
            logger.error(f"CRITICAL: JWT-authenticated user_id={user_id} not found in database. Payment cannot be processed.")
            return {
                'success': False,
                'user_id': user_id,
                'credits_added': 0,
                'message': 'User not found. Payment cannot be processed.'
            }
        
        # Capture customer details snapshot from authenticated user record
        # CRITICAL: Customer details MUST come from users table, NOT Razorpay or frontend
        customer_name = None
        if current_user.first_name or current_user.last_name:
            customer_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip()
        elif current_user.username:
            customer_name = current_user.username
        
        customer_email = current_user.email or ""
        customer_mobile = current_user.phone or ""
        
        # STEP 6: Update user_credits table (BALANCE TABLE)
        # CRITICAL: This updates the balance that UI reads from
        # CRITICAL: MUST use current_user.id - NEVER hardcoded or admin user_id
        from app.services.credit_service import get_user_credits, UserCredits
        user_credits = get_user_credits(db, user_id)
        
        if not user_credits:
            # Create new user_credits record for this user
            logger.info(f"CREATING NEW user_credits record: user_id={user_id} (NOT admin user_id=1)")
            user_credits = UserCredits(
                user_id=user_id,  # CRITICAL: Use JWT-authenticated user_id
                total_credits=0,
                used_credits=0,
                is_active=True
            )
            db.add(user_credits)
            db.flush()  # Flush to get the record
            logger.info(f"NEW user_credits record created: user_id={user_id}")
        else:
            logger.info(f"UPDATING EXISTING user_credits: user_id={user_id}, current_total={user_credits.total_credits}, adding={credits_added}")
        
        # CRITICAL: Verify we're updating the correct user's credits
        if user_credits.user_id != user_id:
            logger.error(f"CRITICAL BUG: user_credits.user_id={user_credits.user_id} != authenticated user_id={user_id}. Rejecting payment.")
            db.rollback()
            return {
                'success': False,
                'user_id': user_id,
                'credits_added': 0,
                'message': 'User credits ownership mismatch. Security violation.'
            }
        
        # Add credits to balance
        old_total = user_credits.total_credits
        user_credits.total_credits += credits_added
        user_credits.updated_at = func.now()
        logger.info(f"user_credits UPDATE: user_id={user_id}, old_total={old_total}, new_total={user_credits.total_credits}")
        
        # STEP 7: Insert credit_transactions row (LEDGER - HISTORY ONLY)
        # CRITICAL: This is for audit trail, NOT for balance calculation
        # CRITICAL: MUST use current_user.id - NEVER hardcoded or admin user_id
        from app.models import CreditTransaction
        credit_txn = CreditTransaction(
            user_id=user_id,  # CRITICAL: Use JWT-authenticated user_id
            mobile=customer_mobile,  # REQUIRED: Mobile in 91XXXXXXXXXX format
            type='credit',
            credits=credits_added,
            reason=f"Payment for order {order_id}",
            reference_id=payment_id
        )
        db.add(credit_txn)
        logger.info(f"credit_transactions INSERT: user_id={user_id}, credits={credits_added}, payment_id={payment_id}")
        
        # STEP 8: Insert payment_transactions row (INVOICE RECORD)
        # CRITICAL: This captures customer snapshot for admin, GST, reconciliation
        # CRITICAL: MUST use current_user.id - NEVER hardcoded or admin user_id
        payment_txn = PaymentTransaction(
            user_id=user_id,  # CRITICAL: Use JWT-authenticated user_id
            provider='razorpay',
            amount=float(total_amount),  # Total payable (base + GST) in INR
            credits_added=credits_added,
            status='success',
            gateway_order_id=order_id,
            gateway_payment_id=payment_id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_mobile=customer_mobile
        )
        db.add(payment_txn)
        logger.info(f"payment_transactions INSERT: user_id={user_id}, amount={total_amount}, credits={credits_added}, customer={customer_name}")
        
        # CRITICAL: Commit all three operations atomically
        # This ensures: user_credits, credit_transactions, and payment_transactions are all saved together
        try:
            db.flush()  # Flush to catch constraint violations before commit
        except Exception as flush_error:
            logger.error(f"Error flushing payment transaction to DB: {flush_error}", exc_info=True)
            db.rollback()
            return {
                'success': False,
                'user_id': user_id,
                'credits_added': 0,
                'message': f'Failed to save payment transaction: {str(flush_error)}'
            }
        
        try:
            db.commit()
            logger.info(f"✅ PAYMENT COMMITTED: payment_id={payment_id}, user_id={user_id}, amount={total_amount}, credits={credits_added}, customer={customer_name}")
            logger.info(f"✅ DB WRITES COMPLETE: user_credits.user_id={user_id}, credit_transactions.user_id={user_id}, payment_transactions.user_id={user_id}")
        except Exception as commit_error:
            logger.error(f"CRITICAL: Failed to commit payment transaction to DB: {commit_error}", exc_info=True)
            db.rollback()
            return {
                'success': False,
                'user_id': user_id,
                'credits_added': 0,
                'message': f'Failed to save payment transaction: {str(commit_error)}'
            }
        
        # Verify payment transaction was saved
        try:
            db.refresh(payment_txn)
            if not payment_txn.id:
                logger.error(f"CRITICAL: PaymentTransaction committed but ID is None. payment_id={payment_id}")
        except Exception as refresh_error:
            logger.warning(f"Could not refresh PaymentTransaction after commit: {refresh_error}")
        
        # Get updated credits for response
        db.refresh(user_credits)
        credits_remaining = user_credits.available_credits
        
        # Update order status in Redis (non-critical - don't fail payment if this fails)
        try:
            order_data['status'] = 'completed'
            order_data['payment_id'] = payment_id
            order_data['completed_at'] = int(time.time())
            
            redis_client.setex(
                order_key,
                86400 * 30,  # 30 days TTL for completed orders
                json.dumps(order_data)
            )
        except Exception as redis_error:
            logger.warning(f"Failed to update Redis order status: {redis_error}")
            # Don't fail payment if Redis update fails
        
        # STEP 9: Send invoice email (non-blocking - don't fail payment if email fails)
        if current_user and current_user.email:
            try:
                from app.services.email_service import send_invoice_email
                from datetime import datetime
                
                # Get base_price and GST from order_data (already calculated)
                invoice_base_price = float(order_data.get('base_price', 0))
                invoice_gst = float(order_data.get('gst', 0))
                invoice_total = float(total_amount)  # Total payable (base + GST)
                
                # Fallback calculation for backward compatibility (old orders without base_price/gst)
                if invoice_base_price == 0:
                    invoice_base_price = float(total_amount) / 1.18  # Calculate base from total
                    invoice_gst = float(total_amount) - invoice_base_price
                
                # Send invoice email (non-blocking - don't fail payment if email fails)
                email_sent = send_invoice_email(
                    to_email=current_user.email,
                    user_name=customer_name or "User",
                    user_mobile=customer_mobile,
                    payment_id=payment_id,
                    amount=invoice_base_price,  # Base price (GST excluded)
                    gst_amount=invoice_gst,  # GST amount
                    total_amount=invoice_total,  # Total payable (base + GST)
                    credits_added=credits_added,
                    payment_date=payment_txn.created_at if payment_txn.created_at else datetime.now()
                )
                
                if email_sent:
                    logger.info(f"Invoice email sent to {current_user.email} for payment {payment_id}")
                else:
                    logger.warning(f"Failed to send invoice email to {current_user.email} for payment {payment_id}")
            except Exception as email_error:
                # Log error but don't fail payment processing
                logger.error(f"Error sending invoice email: {email_error}", exc_info=True)
        
        # STEP 10: Return success response
        logger.info(f"Payment processed successfully: Order {order_id}, Payment {payment_id}, User {user_id}, Credits {credits_added}, Customer={customer_name}")
        
        return {
            'success': True,
            'user_id': user_id,
            'credits_added': credits_added,
            'credits_remaining': credits_remaining,
            'message': f'Successfully added {credits_added} credits to your account'
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing payment: {e}", exc_info=True)
        return {
            'success': False,
            'user_id': user_id,
            'credits_added': 0,
            'message': f'Error processing payment: {str(e)}'
        }


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



