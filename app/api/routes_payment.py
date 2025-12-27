from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.services import payment_service
from app.services.user_sync_service import get_or_sync_user
from app.models import User

# Import function directly to avoid any import caching issues
process_payment_success = payment_service.process_payment_success

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
        # Call with positional arguments matching function signature:
        # process_payment_success(db, order_id, payment_id, signature, user_id, amount)
        result = process_payment_success(
            db,              # Position 1: db: Session
            order_id,        # Position 2: order_id: str
            payment_id,      # Position 3: payment_id: str
            signature,       # Position 4: signature: str
            user.id,         # Position 5: user_id: int
            amount           # Position 6: amount: Optional[float] = None
        )
        return result
        
    except HTTPException:
        # IMPORTANT: propagate correct HTTP status (400)
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Payment verification failed"
        )
