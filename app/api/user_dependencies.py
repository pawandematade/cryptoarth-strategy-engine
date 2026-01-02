"""
User Dependencies for FastAPI Authentication
Provides reusable auth dependencies for all authenticated routes.
"""
from fastapi import HTTPException, Depends, Header, Request, status
from sqlalchemy.orm import Session
from typing import Optional
import logging
import requests
from common.db import get_db
from app.models import User
from common.config import AUTH_BACKEND_URL
from app.utils.jwt_helper import decode_token
import jwt

logger = logging.getLogger(__name__)


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """
    Standard auth dependency for authenticated routes.
    
    - Decodes JWT token directly (no external API call)
    - Loads user from DB using external_user_id
    - Returns User object with guaranteed external_user_id
    - Raises 401 for invalid/missing tokens
    
    CRITICAL: Always use user.external_user_id (NOT user.id) for queries.
    
    Args:
        request: FastAPI Request (for OPTIONS bypass)
        authorization: Authorization header (Bearer token)
        db: Database session
        
    Returns:
        User: Authenticated user with external_user_id set
        
    Raises:
        HTTPException(401): Invalid/missing token
        HTTPException(404): User not found in DB
        HTTPException(403): User inactive
    """
    # Bypass OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT)
    
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )
    
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is required"
        )
    
    # Decode JWT token
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    
    # Extract user_id from token (this is external_user_id)
    external_user_id = payload.get("user_id")
    if not external_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: user_id not found"
        )
    
    # Load user from DB using external_user_id
    user = db.query(User).filter(User.external_user_id == external_user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    return user


def get_current_user_strict(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Safe auto-heal user dependency with zero impact on valid users.
    
    CRITICAL SAFETY RULES:
    - Validates JWT via auth backend
    - If user exists and is valid → DO NOTHING (no DB write, zero impact)
    - If user not found → Auto-create user with JWT data
    - If user found but broken → Auto-heal ONLY broken fields
    - Never modifies valid users
    - Never overwrites existing correct data
    - Never throws 401 for valid JWT
    - BYPASSES authentication for OPTIONS requests (CORS preflight)
    
    Args:
        request: FastAPI Request object (for method detection)
        authorization: Authorization header (Bearer token)
        db: Database session
        
    Returns:
        User: User model instance from local DB, or None for OPTIONS requests
        
    Raises:
        HTTPException(401): If token invalid or auth backend unavailable
        HTTPException(500): If user creation/healing fails
    """
    # CRITICAL: Bypass authentication for OPTIONS requests (CORS preflight)
    # Browsers don't send Authorization headers in OPTIONS requests
    # FastAPI CORS middleware will handle OPTIONS, but only if dependencies don't raise 401
    # Raise 204 to let CORS middleware handle OPTIONS cleanly
    # CORS middleware handles OPTIONS before route handlers are called
    if request.method == "OPTIONS":
        raise HTTPException(status_code=204)
    
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
        
        # Log minimal JWT validation (avoid logging full payload for security)
        logger.info(f"JWT validated: external_user_id={external_user_id}")
        if external_user_id == 1:
            logger.error(f"🔴 CRITICAL: JWT returned external_user_id=1! This is wrong. Full response: {data}")
        
    except HTTPException:
        # Re-raise HTTPException as-is (401)
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Auth backend request failed: {e}")
        raise HTTPException(status_code=401, detail="Authentication service unavailable")
    except Exception as e:
        logger.error(f"Unexpected error validating token: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Authentication failed")
    
    # Step 2: Extract additional JWT data for user creation/healing
    jwt_email = user_data.get("email") or ""
    jwt_phone = user_data.get("phone") or user_data.get("mobile") or ""
    
    # Step 3: Query user from local DB
    user = db.query(User).filter(User.external_user_id == external_user_id).first()
    
    # CASE 1: User EXISTS and VALID → DO NOTHING (zero impact)
    if user:
        is_valid = (
            user.external_user_id == external_user_id and
            user.is_active == True
        )
        
        if is_valid:
            # User is valid - return immediately with NO DB write
            logger.info(f"✅ User valid: external_user_id={external_user_id}, user.id={user.id} - no changes needed")
            return user
        
        # CASE 3: User FOUND but BROKEN (legacy users only)
        # Fix ONLY missing/broken fields
        logger.warning(f"⚠️ User found but broken: external_user_id={external_user_id}, user.id={user.id}, is_active={user.is_active}")
        
        needs_fix = False
        
        # Fix external_user_id mismatch
        if user.external_user_id != external_user_id:
            logger.info(f"🔧 Fixing external_user_id mismatch: {user.external_user_id} → {external_user_id}")
            user.external_user_id = external_user_id
            needs_fix = True
        
        # Fix is_active if False
        if not user.is_active:
            logger.info(f"🔧 Fixing is_active: False → True")
            user.is_active = True
            needs_fix = True
        
        # Fix missing email (only if not set)
        if not user.email and jwt_email:
            logger.info(f"🔧 Fixing missing email: {jwt_email}")
            user.email = jwt_email
            needs_fix = True
        
        # Fix missing phone (only if not set)
        if not user.phone and jwt_phone:
            logger.info(f"🔧 Fixing missing phone: {jwt_phone}")
            user.phone = jwt_phone
            needs_fix = True
        
        # Fix missing username (only if not set)
        if not user.username:
            user.username = f"user_{external_user_id}"
            needs_fix = True
        
        if needs_fix:
            try:
                db.commit()
                db.refresh(user)
                logger.info(f"✅ User auto-healed: external_user_id={external_user_id}, user.id={user.id}")
            except Exception as e:
                logger.error(f"❌ Failed to auto-heal user: {e}", exc_info=True)
                db.rollback()
                raise HTTPException(status_code=500, detail="User auto-heal failed")
        
        return user
    
    # CASE 2: User NOT FOUND → Create user with JWT data
    logger.info(f"🆕 Creating new user: external_user_id={external_user_id}")
    
    try:
        user = User(
            external_user_id=external_user_id,
            email=jwt_email,
            phone=jwt_phone,
            username=f"user_{external_user_id}",
            is_active=True,
            source="auth_backend",
            raw_user_json=user_data
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"✅ User auto-created: external_user_id={external_user_id}, user.id={user.id}")
        return user
    except Exception as e:
        logger.error(f"❌ Failed to create user: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="User creation failed")
