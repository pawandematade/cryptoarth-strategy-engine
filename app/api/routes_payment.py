"""
Payment API Routes
Handles Razorpay payment gateway integration for credit purchases
"""
from fastapi import APIRouter, HTTPException, status, Header, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
import json
import hmac
import hashlib
from app.services.payment_service import (
    create_razorpay_order,
    process_payment_success,
    get_credit_plans,
    verify_razorpay_signature
)
from app.services.user_sync_service import get_or_sync_user
from app.database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateOrderRequest(BaseModel):
    """Request model for creating payment order"""
    plan_id: str = Field(..., description="Credit plan ID: 'starter', 'professional', 'enterprise', or 'unlimited'")


class WebhookRequest(BaseModel):
    """Request model for Razorpay webhook"""
    event: str = Field(..., description="Webhook event type")
    payload: Dict[str, Any] = Field(..., description="Webhook payload")


@router.get("/payment/plans")
def get_plans():
    """
    Get available credit plans
    
    Returns:
        dict: Available credit plans with pricing
    """
    try:
        result = get_credit_plans()
        return result
    except Exception as e:
        logger.error(f"Error getting credit plans: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/payment/create-order")
def create_order(
    request: CreateOrderRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Create a Razorpay order for credit purchase
    
    Args:
        request: CreateOrderRequest with plan_id
        authorization: Authorization header (Bearer token)
        db: Database session
    
    Returns:
        dict: {
            "success": bool,
            "order_id": str,
            "amount": int,
            "currency": str,
            "key_id": str,
            "credits": int,
            "plan_name": str,
            "message": str
        }
    """
    try:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # Sync user and get local user ID
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate user"
            )
        
        # Validate plan_id
        if not request.plan_id or not request.plan_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Plan ID is required"
            )
        
        plan_id = request.plan_id.strip().lower()
        
        # Create Razorpay order (user.id is integer)
        result = create_razorpay_order(plan_id, user.id)
        
        if not result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result['message']
            )
        
        return {
            "success": True,
            "order_id": result['order_id'],
            "amount": result['amount'],
            "currency": result['currency'],
            "key_id": result['key_id'],
            "credits": result['credits'],
            "plan_name": result.get('plan_name', ''),
            "message": result['message']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating payment order: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/payment/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Razorpay webhook handler for payment events
    
    CRITICAL: Webhook is the source of truth for payment processing.
    Credits must NEVER depend only on frontend callback (unreliable).
    
    This endpoint:
    - Verifies Razorpay webhook signature (HMAC SHA256 of request body)
    - Processes payment.captured and order.paid events
    - Checks idempotency (payment_id already processed) before adding credits
    - Adds credits to user account only if payment_id not already processed
    - Stores transaction details in database
    
    Events handled:
    - payment.captured: Payment successfully captured
    - order.paid: Order marked as paid (alternative event)
    - payment.failed: Payment failed (logged only)
    
    Idempotency:
    - Checks PaymentTransaction table by gateway_payment_id
    - If payment_id already exists with status='success', returns existing result
    - Prevents duplicate credit additions on webhook retries
    
    Args:
        request: FastAPI Request object (contains webhook payload)
        db: Database session
    
    Returns:
        dict: Webhook processing result (always returns 200 to Razorpay)
    """
    try:
        # Get raw request body for signature verification
        body = await request.body()
        body_str = body.decode('utf-8')
        
        # Get Razorpay signature from headers
        razorpay_signature = request.headers.get('X-Razorpay-Signature')
        
        if not razorpay_signature:
            logger.warning("Razorpay webhook received without signature")
            # Return 200 to prevent Razorpay retries
            return {"success": False, "message": "Missing Razorpay signature"}
        
        # Verify webhook signature (Razorpay signs the entire request body)
        from app.config import RAZORPAY_KEY_SECRET
        if RAZORPAY_KEY_SECRET:
            expected_signature = hmac.new(
                RAZORPAY_KEY_SECRET.encode('utf-8'),
                body_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(expected_signature, razorpay_signature):
                logger.warning("Invalid Razorpay webhook signature")
                # Return 200 to prevent retries, but log for investigation
                return {"success": False, "message": "Invalid webhook signature"}
        
        # Parse payload
        payload = json.loads(body_str)
        
        # Extract event type
        event = payload.get('event')
        
        if not event:
            logger.warning("Webhook payload missing event type")
            return {"success": False, "message": "Missing event type"}
        
        logger.info(f"Received Razorpay webhook event: {event}")
        
        # Process payment.captured and order.paid events
        # Both events indicate successful payment
        # CRITICAL: Webhook is the source of truth - credits must NEVER depend only on frontend callback
        if event == 'payment.captured' or event == 'order.paid':
            # Extract payment entity (Razorpay webhook structure varies by event)
            payment_entity = None
            order_entity = None
            
            if event == 'payment.captured':
                # payment.captured event structure: payload.payment.entity
                payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
                if not payment_entity:
                    payment_entity = payload.get('payload', {}).get('payment', {})
            elif event == 'order.paid':
                # order.paid event structure: payload.order.entity contains payments array
                order_entity = payload.get('payload', {}).get('order', {}).get('entity', {})
                if not order_entity:
                    order_entity = payload.get('payload', {}).get('order', {})
                # Extract payment from order.payments array
                payments = order_entity.get('payments', [])
                if payments and len(payments) > 0:
                    payment_entity = payments[0]  # Get first payment (usually only one)
            
            # Get payment details
            payment_id = payment_entity.get('id') if payment_entity else None
            order_id = payment_entity.get('order_id') if payment_entity else (order_entity.get('id') if order_entity else None)
            
            if not payment_id or not order_id:
                logger.error(f"Missing payment_id or order_id in webhook event {event}: {payload}")
                return {"success": False, "message": "Missing payment_id or order_id"}
            
            # Get payment signature for additional verification
            payment_signature = payment_entity.get('signature', '') if payment_entity else ''
            
            # Extract user_id from order notes (stored in Redis)
            from app.store.redis_client import redis_client
            order_data_str = redis_client.get(f"PAYMENT_ORDER:{order_id}")
            if not order_data_str:
                logger.error(f"Order {order_id} not found in Redis")
                return {"success": False, "message": "Order not found"}
            
            order_data = json.loads(order_data_str)
            user_id_str = order_data.get('user_id')
            
            if not user_id_str:
                logger.error(f"User ID not found in order {order_id}")
                return {"success": False, "message": "User ID not found in order"}
            
            # Get user from database (user_id in Redis is external_user_id as string)
            from app.models import User
            try:
                external_user_id = int(user_id_str)
                user = db.query(User).filter(User.external_user_id == external_user_id).first()
                if not user:
                    logger.error(f"User not found for external_user_id={external_user_id}")
                    return {"success": False, "message": "User not found"}
            except ValueError:
                logger.error(f"Invalid user_id format in order: {user_id_str}")
                return {"success": False, "message": "Invalid user ID format"}
            
            # Process payment (will verify payment signature internally)
            result = process_payment_success(db, order_id, payment_id, payment_signature, user.id)
            
            if not result['success']:
                logger.error(f"Failed to process payment: {result['message']}")
                # Return 200 to Razorpay to prevent retries, but log error
                return {
                    "success": False,
                    "message": result['message']
                }
            
            logger.info(f"Payment processed successfully: {result['message']}")
            
            return {
                "success": True,
                "message": "Payment processed successfully",
                "user_id": result['user_id'],
                "credits_added": result['credits_added']
            }
        
        elif event == 'payment.failed':
            # Log failed payment
            payment_data = payload.get('payload', {}).get('payment', {})
            entity = payment_data.get('entity', {})
            payment_id = entity.get('id') or payment_data.get('id')
            order_id = entity.get('order_id') or payment_data.get('order_id')
            
            logger.warning(f"Payment failed: Payment {payment_id}, Order {order_id}")
            
            # Store failed transaction
            if order_id:
                from app.store.redis_client import redis_client
                import json
                order_key = f"PAYMENT_ORDER:{order_id}"
                order_data_str = redis_client.get(order_key)
                if order_data_str:
                    order_data = json.loads(order_data_str)
                    order_data['status'] = 'failed'
                    order_data['payment_id'] = payment_id
                    order_data['failure_reason'] = entity.get('error_description', 'Payment failed')
                    redis_client.setex(order_key, 86400 * 7, json.dumps(order_data))
            
            return {
                "success": True,
                "message": "Payment failure logged"
            }
        
        else:
            # Log other events but don't process
            logger.info(f"Unhandled webhook event: {event}")
            return {
                "success": True,
                "message": f"Event {event} received but not processed"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Razorpay webhook: {e}", exc_info=True)
        # Return 200 to Razorpay even on error (to prevent retries)
        # Log error for manual investigation
        return {
            "success": False,
            "message": f"Error processing webhook: {str(e)}"
        }


@router.post("/payment/verify")
def verify_payment(
    order_id: str,
    payment_id: str,
    signature: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Verify payment manually (for frontend callback)
    
    Args:
        order_id: Razorpay order ID
        payment_id: Razorpay payment ID
        signature: Razorpay signature
        authorization: Authorization header (Bearer token)
        db: Database session
    
    Returns:
        dict: Payment verification result
    """
    try:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # Sync user and get local user ID
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate user"
            )
        
        # Verify signature
        if not verify_razorpay_signature(order_id, payment_id, signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payment signature"
            )
        
        # Process payment (user.id is integer)
        result = process_payment_success(db, order_id, payment_id, signature, user.id)
        
        if not result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result['message']
            )
        
        return {
            "success": True,
            "message": result['message'],
            "credits_added": result['credits_added'],
            "credits_remaining": result.get('credits_remaining', 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying payment: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/payment/history")
def get_payment_history(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Get payment history for the authenticated user
    
    Returns:
        dict: {
            "success": bool,
            "payments": [
                {
                    "id": int,
                    "date": str,
                    "amount": float,
                    "payment_id": str,
                    "status": str,
                    "plan_name": str,
                    "credits_added": int
                }
            ],
            "message": str
        }
    """
    try:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # Sync user and get local user ID
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate user"
            )
        
        # Get payment transactions for user
        from app.models import PaymentTransaction
        payments = db.query(PaymentTransaction).filter(
            PaymentTransaction.user_id == user.id
        ).order_by(PaymentTransaction.created_at.desc()).all()
        
        # Format payment history
        payment_history = []
        for payment in payments:
            # Get plan name from order data in Redis (if available)
            plan_name = "Credit Purchase"
            if payment.gateway_order_id:
                from app.store.redis_client import redis_client
                order_key = f"PAYMENT_ORDER:{payment.gateway_order_id}"
                order_data_str = redis_client.get(order_key)
                if order_data_str:
                    try:
                        order_data = json.loads(order_data_str)
                        plan_name = order_data.get('plan_name', 'Credit Purchase')
                    except:
                        pass
            
            payment_history.append({
                "id": payment.id,
                "date": payment.created_at.isoformat() if payment.created_at else "",
                "amount": float(payment.amount) if payment.amount else 0.0,
                "payment_id": payment.gateway_payment_id or "",
                "status": payment.status,
                "plan_name": plan_name,
                "credits_added": payment.credits_added
            })
        
        return {
            "success": True,
            "payments": payment_history,
            "message": f"Retrieved {len(payment_history)} payment records"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting payment history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

