"""
Internal API Routes (No Authentication Required)
For internal service-to-service calls (e.g., Django backend → Strategy Engine)
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from app.database import get_db
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
    Internal endpoint to initialize credits for a new user during signup.
    Called by Django backend after user creation.
    
    This endpoint:
    1. Syncs user to local DB (if not exists)
    2. Initializes credits (10 by default)
    
    Args:
        request: InitializeSignupCreditsRequest with external_user_id and phone
    
    Returns:
        dict: {
            "success": bool,
            "user_id": int,
            "credits": int,
            "message": str
        }
    """
    try:
        # Sync user to local DB (if not exists)
        # Note: We don't have auth token here, so we'll create minimal user record
        from app.models import User
        
        # Check if user already exists in local DB
        local_user = db.query(User).filter(
            User.external_user_id == request.external_user_id
        ).first()
        
        if not local_user:
            # Create minimal user record for credit initialization
            # Full sync will happen on first API call with auth token
            local_user = User(
                external_user_id=request.external_user_id,
                phone=request.phone,
                source="auth_backend",
                is_active=True
            )
            db.add(local_user)
            db.commit()
            db.refresh(local_user)
            logger.info(f"Created local user record for external_user_id={request.external_user_id}")
        
        # Initialize credits (will use default free credits = 10)
        try:
            user_credits = initialize_user_credits(db, local_user.id)
            default_credits = get_default_free_credits(db)
            
            logger.info(f"Initialized signup credits: user_id={local_user.id}, external_id={request.external_user_id}, credits={default_credits}")
            
            return {
                "success": True,
                "user_id": local_user.id,
                "external_user_id": request.external_user_id,
                "credits": default_credits,
                "message": f"Initialized {default_credits} signup credits"
            }
        except Exception as e:
            logger.error(f"Error initializing credits for user {local_user.id}: {e}", exc_info=True)
            # Check if credits already exist (idempotent)
            from app.models import UserCredits
            existing_credits = db.query(UserCredits).filter(
                UserCredits.user_id == local_user.id
            ).first()
            if existing_credits:
                logger.info(f"Credits already exist for user {local_user.id}, returning existing")
                return {
                    "success": True,
                    "user_id": local_user.id,
                    "external_user_id": request.external_user_id,
                    "credits": existing_credits.total_credits - existing_credits.used_credits,
                    "message": "Credits already initialized"
                }
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initialize credits: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in initialize_signup_credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

