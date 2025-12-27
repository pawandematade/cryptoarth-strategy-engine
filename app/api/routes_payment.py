from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional
import inspect

from app.database import get_db
from app.services import payment_service
from app.services.user_sync_service import get_or_sync_user
from app.models import User

# Import function
process_payment_success = payment_service.process_payment_success

# Lazy signature validation (only logs warning, doesn't crash on import)
def _validate_signature():
    """Validate function signature and log warning if mismatch"""
    try:
        sig = inspect.signature(process_payment_success)
        expected_params = ['db', 'order_id', 'payment_id', 'signature', 'user_id', 'amount']
        actual_params = list(sig.parameters.keys())
        if actual_params != expected_params:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"⚠️ Function signature mismatch! Expected {expected_params}, got {actual_params}. "
                f"Please restart the server and clear Python cache."
            )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Could not validate function signature: {e}")

router = APIRouter(prefix="/payment", tags=["Payment"])


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Failed to authenticate user")
    
    return user


@router.post("/verify")
def verify_payment(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
        # Validate signature on first call (lazy validation)
        _validate_signature()
        
        # CRITICAL: Call with positional arguments only (no keyword args)
        # Function signature: process_payment_success(db, order_id, payment_id, signature, user_id, amount)
        # Using tuple unpacking to ensure positional-only call
        args = (db, order_id, payment_id, signature, user.id, amount)
        result = process_payment_success(*args)
        return result
        
    except HTTPException:
        # IMPORTANT: propagate correct HTTP status (400)
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Payment verification failed"
        )
