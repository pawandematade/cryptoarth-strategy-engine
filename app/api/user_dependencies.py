"""
Strict Read-Only User Dependencies
For GET/READ APIs that should NOT create or sync users.
Returns 401 (not 400) for authentication failures.
"""
from fastapi import HTTPException, Depends, Header, Request
from sqlalchemy.orm import Session
from typing import Optional
import logging
import requests
from app.database import get_db
from app.models import User
from app.config import AUTH_BACKEND_URL

logger = logging.getLogger(__name__)


def get_current_user_strict(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Strict read-only user dependency for GET/READ APIs.
    
    CRITICAL RULES:
    - Validates JWT via auth backend
    - Queries local DB ONLY (no user creation/sync)
    - Returns 401 (never 400) for auth failures
    - Fails fast if user not found locally
    - BYPASSES authentication for OPTIONS requests (CORS preflight)
    
    Args:
        request: FastAPI Request object (for method detection)
        authorization: Authorization header (Bearer token)
        db: Database session
        
    Returns:
        User: User model instance from local DB, or None for OPTIONS requests
        
    Raises:
        HTTPException(401): If token invalid, user not found, or auth backend unavailable
    """
    # CRITICAL: Bypass authentication for OPTIONS requests (CORS preflight)
    # Browsers don't send Authorization headers in OPTIONS requests
    # FastAPI CORS middleware will handle OPTIONS, but only if dependencies don't raise 401
    # Returning None is safe because route handlers never execute for OPTIONS requests
    # CORS middleware handles OPTIONS before route handlers are called
    if request.method == "OPTIONS":
        return None
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    # Step 1: Validate token with auth backend (but don't sync)
    try:
        url = f"{AUTH_BACKEND_URL}/auth/user/"
        headers = {"Authorization": authorization}
        
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 401:
            logger.warning("Auth backend returned 401 - invalid token")
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        elif response.status_code == 403:
            logger.warning("Auth backend returned 403 - access forbidden")
            raise HTTPException(status_code=401, detail="Access forbidden")
        elif response.status_code != 200:
            logger.error(f"Auth backend returned {response.status_code}: {response.text}")
            raise HTTPException(status_code=401, detail="Authentication failed")
        
        # Extract user ID from auth backend response
        data = response.json()
        user_data = data.get("user") or data.get("data") or data
        if not isinstance(user_data, dict):
            raise HTTPException(status_code=401, detail="Invalid user data format")
        
        external_user_id = user_data.get("id") or user_data.get("user_id")
        if not external_user_id:
            logger.error("Could not extract user ID from auth backend response")
            raise HTTPException(status_code=401, detail="Invalid token payload")
        
        # DEBUG: Log JWT payload (as requested)
        logger.info(f"JWT PAYLOAD: external_user_id={external_user_id}, user_data_keys={list(user_data.keys())}")
        
    except HTTPException:
        # Re-raise HTTPException as-is (401)
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Auth backend request failed: {e}")
        raise HTTPException(status_code=401, detail="Authentication service unavailable")
    except Exception as e:
        logger.error(f"Unexpected error validating token: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Authentication failed")
    
    # Step 2: Get user from local DB ONLY (no creation, no sync)
    user = db.query(User).filter(User.external_user_id == external_user_id).first()
    
    if not user:
        logger.warning(f"User not found in local DB: external_user_id={external_user_id}")
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

