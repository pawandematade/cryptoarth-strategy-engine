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
from app.services.credits_service import get_user_id_from_header

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
def create_order(request: CreateOrderRequest, authorization: Optional[str] = Header(None)):
    """
    Create a Razorpay order for credit purchase
    
    Args:
        request: CreateOrderRequest with plan_id
        authorization: Authorization header with user ID
    
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
        user_id = get_user_id_from_header(authorization)
        
        if not user_id or user_id == "anonymous":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User authentication required"
            )
        
        # Validate plan_id
        if not request.plan_id or not request.plan_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Plan ID is required"
            )
        
        plan_id = request.plan_id.strip().lower()
        
        # Create Razorpay order
        result = create_razorpay_order(plan_id, user_id)
        
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
async def razorpay_webhook(request: Request):
    """
    Razorpay webhook handler for payment events
    
    This endpoint:
    - Verifies Razorpay webhook signature (HMAC SHA256 of request body)
    - Processes payment.captured event
    - Adds credits to user account
    - Stores transaction details
    
    Args:
        request: FastAPI Request object (contains webhook payload)
    
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
        
        # Process payment.captured event
        if event == 'payment.captured':
            # Extract payment entity (Razorpay webhook structure)
            payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
            
            # Fallback: try direct payment object
            if not payment_entity:
                payment_entity = payload.get('payload', {}).get('payment', {})
            
            # Get payment details
            payment_id = payment_entity.get('id')
            order_id = payment_entity.get('order_id')
            
            if not payment_id or not order_id:
                logger.error(f"Missing payment_id or order_id in webhook: {payload}")
                return {"success": False, "message": "Missing payment_id or order_id"}
            
            # Get payment signature for additional verification
            payment_signature = payment_entity.get('signature', '')
            
            # Process payment (will verify payment signature internally)
            result = process_payment_success(order_id, payment_id, payment_signature)
            
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
def verify_payment(order_id: str, payment_id: str, signature: str, authorization: Optional[str] = Header(None)):
    """
    Verify payment manually (for frontend callback)
    
    Args:
        order_id: Razorpay order ID
        payment_id: Razorpay payment ID
        signature: Razorpay signature
        authorization: Authorization header with user ID
    
    Returns:
        dict: Payment verification result
    """
    try:
        user_id = get_user_id_from_header(authorization)
        
        if not user_id or user_id == "anonymous":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User authentication required"
            )
        
        # Verify signature
        if not verify_razorpay_signature(order_id, payment_id, signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payment signature"
            )
        
        # Process payment
        result = process_payment_success(order_id, payment_id, signature)
        
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

