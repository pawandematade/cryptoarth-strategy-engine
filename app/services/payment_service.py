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
from app.services.credit_service import add_credits, get_rupee_to_credit_ratio
from app.models import PaymentTransaction
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Credit packages/plans
# CRITICAL: All amounts must match frontend exactly
# Base price: ₹10 = 1 Credit
# GST: 18% of base price
# Total payable = base_price + gst
CREDIT_PLANS = {
    'starter': {
        'name': 'Starter Pack',
        'credits': 50,
        'base_price': 500,  # Base price in INR
        'gst': 90,  # GST (18%) in INR
        'total_amount': 590,  # Total payable (base + GST) in INR
        'description': '50 credits for AI strategy generation and backtesting'
    },
    'professional': {
        'name': 'Professional Pack',
        'credits': 150,
        'base_price': 1500,  # Base price in INR
        'gst': 270,  # GST (18%) in INR
        'total_amount': 1770,  # Total payable (base + GST) in INR
        'description': '150 credits - Best for active traders'
    },
    'enterprise': {
        'name': 'Enterprise Pack',
        'credits': 300,
        'base_price': 3000,  # Base price in INR
        'gst': 540,  # GST (18%) in INR
        'total_amount': 3540,  # Total payable (base + GST) in INR
        'description': '300 credits - For power users and teams'
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
        total_amount = plan['total_amount']  # Total payable in INR
        amount_paise = int(total_amount * 100)  # Convert to paise (Razorpay requires integer)
        
        # Create Razorpay order using exact format as specified
        # CRITICAL: Receipt must be <= 40 characters (Razorpay hard limit)
        # ENSURE receipt is ALWAYS <= 40 characters (EXACT CODE - DO NOT MODIFY)
        safe_receipt = f"cr{user_id}{int(time.time())}"
        safe_receipt = safe_receipt[:40]
        
        # Runtime verification: Log receipt before order creation (EXACT FORMAT)
        logger.error(
            "RAZORPAY RECEIPT => %s | LEN=%d",
            safe_receipt,
            len(safe_receipt)
        )
        
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": safe_receipt,
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
    Process successful payment and add credits to user
    
    Args:
        db: Database session
        order_id: Razorpay order ID
        payment_id: Razorpay payment ID
        signature: Razorpay signature
        user_id: Local user ID (integer)
    
    Returns:
        dict: {
            'success': bool,
            'user_id': int,
            'credits_added': int,
            'message': str
        }
    """
    try:
        # Verify signature first
        if not verify_razorpay_signature(order_id, payment_id, signature):
            return {
                'success': False,
                'user_id': user_id,
                'credits_added': 0,
                'message': 'Invalid payment signature. Payment verification failed.'
            }
        
        # Get order details from Redis
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
        
        # CRITICAL: Idempotency check - Check if payment_id already processed
        # This prevents duplicate credit additions if webhook is called multiple times
        existing_payment = db.query(PaymentTransaction).filter(
            PaymentTransaction.gateway_payment_id == payment_id,
            PaymentTransaction.status == 'success'
        ).first()
        
        if existing_payment:
            logger.info(f"Payment {payment_id} already processed in DB (idempotency check). Skipping duplicate processing.")
            # Get updated user credits
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
        
        # Calculate credits from base_price (₹10 = 1 credit)
        # CRITICAL: Credits are calculated from base_price, NOT total_amount (GST excluded)
        base_price = order_data.get('base_price', 0)  # Base price in INR (GST excluded)
        if base_price == 0:
            # Fallback to amount for backward compatibility (old orders)
            base_price = order_data.get('amount', 0)
        ratio = get_rupee_to_credit_ratio(db)  # Default: 10
        credits = int(base_price / ratio) if ratio > 0 else 0
        
        # Get total amount for payment transaction record
        total_amount = order_data.get('amount', 0)  # Total payable (base + GST) in INR
        
        # Add credits to user account (atomic operation)
        success, error_msg = add_credits(
            db, user_id, credits,
            reason=f"Payment for order {order_id}",
            reference_id=payment_id
        )
        
        if not success:
            logger.error(f"Failed to add credits to user {user_id}: {error_msg}")
            # Create failed payment transaction
            payment_txn = PaymentTransaction(
                user_id=user_id,
                provider='razorpay',
                amount=float(total_amount),  # Total payable (base + GST)
                credits_added=0,
                status='failed',
                gateway_order_id=order_id,
                gateway_payment_id=payment_id
            )
            db.add(payment_txn)
            db.commit()
            
            return {
                'success': False,
                'user_id': user_id,
                'credits_added': 0,
                'message': f"Failed to add credits: {error_msg}"
            }
        
        # Create payment transaction record
        payment_txn = PaymentTransaction(
            user_id=user_id,
            provider='razorpay',
            amount=float(total_amount),  # Total payable (base + GST)
            credits_added=credits,
            status='success',
            gateway_order_id=order_id,
            gateway_payment_id=payment_id
        )
        db.add(payment_txn)
        db.commit()
        
        # Update order status in Redis
        order_data['status'] = 'completed'
        order_data['payment_id'] = payment_id
        order_data['completed_at'] = int(time.time())
        
        redis_client.setex(
            order_key,
            86400 * 30,  # 30 days TTL for completed orders
            json.dumps(order_data)
        )
        
        # Get updated user credits
        from app.services.credit_service import get_user_credits
        user_credits = get_user_credits(db, user_id)
        credits_remaining = user_credits.available_credits if user_credits else 0
        
        # Get user details for invoice email
        from app.models import User
        user = db.query(User).filter(User.id == user_id).first()
        
        # Send invoice email (idempotent - only if email not sent before)
        # Check if invoice email was already sent by checking a flag in payment_txn
        # For now, we'll send email only once per payment_id (idempotency handled by email service)
        if user and user.email:
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
                
                # Get user name and mobile
                user_name = user.first_name or user.username or "User"
                if user.last_name:
                    user_name = f"{user.first_name} {user.last_name}" if user.first_name else user.last_name
                user_mobile = user.phone or ""
                
                # Send invoice email (non-blocking - don't fail payment if email fails)
                email_sent = send_invoice_email(
                    to_email=user.email,
                    user_name=user_name,
                    user_mobile=user_mobile,
                    payment_id=payment_id,
                    amount=invoice_base_price,  # Base price (GST excluded)
                    gst_amount=invoice_gst,  # GST amount
                    total_amount=invoice_total,  # Total payable (base + GST)
                    credits_added=credits,
                    payment_date=payment_txn.created_at if payment_txn.created_at else datetime.now()
                )
                
                if email_sent:
                    logger.info(f"Invoice email sent to {user.email} for payment {payment_id}")
                else:
                    logger.warning(f"Failed to send invoice email to {user.email} for payment {payment_id}")
            except Exception as email_error:
                # Log error but don't fail payment processing
                logger.error(f"Error sending invoice email: {email_error}", exc_info=True)
        
        logger.info(f"Payment processed successfully: Order {order_id}, Payment {payment_id}, User {user_id}, Credits {credits}")
        
        return {
            'success': True,
            'user_id': user_id,
            'credits_added': credits,
            'credits_remaining': credits_remaining,
            'message': f'Successfully added {credits} credits to your account'
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



