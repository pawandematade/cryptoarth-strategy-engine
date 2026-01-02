"""
Internal API Routes (No Authentication Required)
For internal service-to-service calls (e.g., Django backend â†’ Strategy Engine)
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from common.db import get_db
from app.services.credit_service import initialize_user_credits, get_default_free_credits
from app.services.user_sync_service import sync_user_to_local_db
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class InitializeSignupCreditsRequest(BaseModel):
    """Request model for internal signup credit initialization"""
    external_user_id: int = Field(..., description="User ID from Django backend")
    phone: str = Field(..., description="User phone number")


@router.post("/internal/signup/initialize-credits")
def initialize_signup_credits(
    request: InitializeSignupCreditsRequest,
    db: Session = Depends(get_db)
):
    """
    Internal endpoint for signup (DISABLED - free credits discontinued)
    
    Returns:
        dict: {
            "success": bool,
            "user_id": int,
            "credits": int,
            "message": str
        }
    """
    # FREE CREDITS DISCONTINUED - Return 0 credits
    # Sync user to local DB (if not exists) but do NOT initialize credits
    from app.models import User
    
    # Check if user already exists in local DB
    local_user = db.query(User).filter(
        User.external_user_id == request.external_user_id
    ).first()
    
    if not local_user:
        # Create minimal user record (no credits)
        local_user = User(
            external_user_id=request.external_user_id,
            phone=request.phone,
            source="auth_backend",
            is_active=True
        )
        db.add(local_user)
        db.commit()
        db.refresh(local_user)
        logger.info(f"Created local user record for external_user_id={request.external_user_id} (no credits initialized)")
    
    # Return 0 credits - free credits discontinued
    return {
        "success": True,
        "user_id": local_user.id,
        "external_user_id": request.external_user_id,
        "credits": 0,
        "message": "Free credits discontinued. Credits can be added via payment or admin."
    }

