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
from app.services.credits_service import add_credits

logger = logging.getLogger(__name__)

# Razorpay client (will be initialized if keys are available)
razorpay_client = None

# Credit packages/plans
CREDIT_PLANS = {
    'starter': {
        'name': 'Starter Pack',
        'credits': 50,
        'amount': 99,  # in INR (paise will be calculated)
        'description': '50 credits for AI strategy generation and backtesting'
    },
    'professional': {
        'name': 'Professional Pack',
        'credits': 200,
        'amount': 299,
        'description': '200 credits - Best for active traders'
    },
    'enterprise': {
        'name': 'Enterprise Pack',
        'credits': 500,
        'amount': 699,
        'description': '500 credits - For power users and teams'
    },
    'unlimited': {
        'name': 'Unlimited Pack',
        'credits': 1000,
        'amount': 1299,
        'description': '1000 credits - Maximum value'
    }
}


def initialize_razorpay():
    """Initialize Razorpay client if API keys are available"""
    global razorpay_client
    
    try:
        from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
        
        if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            logger.warning("Razorpay keys not configured. Payment features will be disabled.")
            return False
        
        if RAZORPAY_KEY_ID == "your_razorpay_key_id" or RAZORPAY_KEY_SECRET == "your_razorpay_key_secret":
            logger.warning("Razorpay keys are placeholder values. Payment features will be disabled.")
            return False
        
        try:
            import razorpay
            razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
            logger.info("Razorpay client initialized successfully")
            return True
        except ImportError:
            logger.error("Razorpay Python SDK not installed. Install with: pip install razorpay")
            return False
            
    except Exception as e:
        logger.error(f"Error initializing Razorpay: {e}", exc_info=True)
        return False


def create_razorpay_order(plan_id: str, user_id: str) -> Dict[str, Any]:
    """
    Create a Razorpay order for credit purchase
    
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
        # Check if Razorpay is initialized
        if not razorpay_client:
            if not initialize_razorpay():
                return {
                    'success': False,
                    'order_id': None,
                    'amount': 0,
                    'currency': 'INR',
                    'key_id': None,
                    'credits': 0,
                    'message': 'Payment gateway not configured. Please contact support.'
                }
        
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
        amount_paise = plan['amount'] * 100  # Convert to paise
        
        # Create Razorpay order
        order_data = {
            'amount': amount_paise,  # Amount in paise
            'currency': 'INR',
            'receipt': f'credits_{user_id}_{plan_id}',
            'notes': {
                'user_id': user_id,
                'plan_id': plan_id,
                'credits': plan['credits'],
                'plan_name': plan['name']
            }
        }
        
        order = razorpay_client.order.create(data=order_data)
        
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
            'user_id': user_id,
            'plan_id': plan_id,
            'credits': plan['credits'],
            'amount': plan['amount'],
            'amount_paise': amount_paise,
            'status': 'created',
            'created_at': order.get('created_at', 0)
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


def process_payment_success(order_id: str, payment_id: str, signature: str) -> Dict[str, Any]:
    """
    Process successful payment and add credits to user
    
    Args:
        order_id: Razorpay order ID
        payment_id: Razorpay payment ID
        signature: Razorpay signature
    
    Returns:
        dict: {
            'success': bool,
            'user_id': str,
            'credits_added': int,
            'message': str
        }
    """
    try:
        # Verify signature first
        if not verify_razorpay_signature(order_id, payment_id, signature):
            return {
                'success': False,
                'user_id': None,
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
                'user_id': None,
                'credits_added': 0,
                'message': 'Order not found. Payment may have expired.'
            }
        
        order_data = json.loads(order_data_str)
        
        # Check if already processed
        if order_data.get('status') == 'completed':
            logger.warning(f"Order {order_id} already processed")
            return {
                'success': True,
                'user_id': order_data['user_id'],
                'credits_added': order_data['credits'],
                'message': 'Payment already processed'
            }
        
        user_id = order_data['user_id']
        credits = order_data['credits']
        
        # Add credits to user account
        credit_result = add_credits(user_id, credits)
        
        if not credit_result['success']:
            logger.error(f"Failed to add credits to user {user_id}: {credit_result['message']}")
            return {
                'success': False,
                'user_id': user_id,
                'credits_added': 0,
                'message': f"Failed to add credits: {credit_result['message']}"
            }
        
        # Update order status
        order_data['status'] = 'completed'
        order_data['payment_id'] = payment_id
        order_data['completed_at'] = int(time.time())
        
        redis_client.setex(
            order_key,
            86400 * 30,  # 30 days TTL for completed orders
            json.dumps(order_data)
        )
        
        # Store transaction record
        transaction_key = f"PAYMENT_TXN:{payment_id}"
        transaction_data = {
            'payment_id': payment_id,
            'order_id': order_id,
            'user_id': user_id,
            'plan_id': order_data['plan_id'],
            'credits': credits,
            'amount': order_data['amount'],
            'status': 'completed',
            'completed_at': int(time.time())
        }
        redis_client.setex(
            transaction_key,
            86400 * 365,  # 1 year TTL
            json.dumps(transaction_data)
        )
        
        logger.info(f"Payment processed successfully: Order {order_id}, Payment {payment_id}, User {user_id}, Credits {credits}")
        
        return {
            'success': True,
            'user_id': user_id,
            'credits_added': credits,
            'credits_remaining': credit_result['credits_remaining'],
            'message': f'Successfully added {credits} credits to your account'
        }
        
    except Exception as e:
        logger.error(f"Error processing payment: {e}", exc_info=True)
        return {
            'success': False,
            'user_id': None,
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


# Initialize Razorpay on module load
try:
    initialize_razorpay()
except Exception as e:
    logger.warning(f"Could not initialize Razorpay on module load: {e}")

