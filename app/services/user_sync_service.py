"""
User Sync Service
Syncs user data from auth backend and maintains local snapshot.
"""
import logging
import requests
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models import User
from app.config import AUTH_BACKEND_URL
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def fetch_user_from_auth_backend(authorization: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch user data from external auth backend.
    
    FAIL FAST: Raises exception if auth backend is unavailable.
    Prevents creating ghost users in local database.
    
    Args:
        external_user_id: User ID from auth backend
        authorization: Authorization header (Bearer token) for auth backend API
    
    Returns:
        dict: User data from auth backend
    
    Raises:
        requests.exceptions.RequestException: If auth backend is unavailable
        ValueError: If user not found or invalid response
    """
    # Auth backend endpoint: GET https://trade-api.cryptoarth.in/auth/user/
    # CRITICAL: MUST use AUTH_BACKEND_URL, NEVER STRATEGY_ENGINE_BASE_URL
    url = f"{AUTH_BACKEND_URL}/auth/user/"
    headers = {}
    
    if authorization:
        headers["Authorization"] = authorization
    
    # DEBUG: Log auth API call (remove in production if needed)
    print(f"AUTH API HIT → {url}")
    logger.info(f"AUTH API HIT → {url}")
    
    # Call auth backend user API
    response = requests.get(
        url,
        headers=headers,
        timeout=5
    )
    
    # FAIL FAST: Raise exception if auth backend unavailable
    response.raise_for_status()
    
    if response.status_code == 200:
        data = response.json()
        # Adjust based on your auth backend response structure
        # Common formats: {"user": {...}} or {"data": {...}} or direct user object
        user_data = data.get("user") or data.get("data") or data
        if isinstance(user_data, dict):
            return user_data
        else:
            raise ValueError(f"Invalid user data format from auth backend: {type(user_data)}")
    else:
        raise ValueError(f"Unexpected response from auth backend: {response.status_code} - {response.text}")


def sync_user_to_local_db(
    db: Session,
    external_user_id: int,
    authorization: Optional[str] = None,
    user_data: Optional[Dict[str, Any]] = None
) -> Optional[User]:
    """
    Sync user data from auth backend to local database.
    
    If user_data is provided, use it directly. Otherwise, fetch from auth backend.
    
    Args:
        db: Database session
        external_user_id: User ID from auth backend
        authorization: Authorization header for auth backend API
        user_data: Optional pre-fetched user data (to avoid duplicate API calls)
    
    Returns:
        User: User model instance (newly created or updated), or None if sync failed
    """
    try:
        # Fetch user data if not provided
        if user_data is None:
            if not authorization:
                raise ValueError("Authorization header required when user_data is not provided")
            # Fetch from auth backend (no external_user_id needed - extracted from response)
            user_data = fetch_user_from_auth_backend(authorization)
            # Extract external_user_id from user_data
            if not external_user_id:
                external_user_id = user_data.get("id") or user_data.get("user_id")
                if not external_user_id:
                    raise ValueError("Could not extract user ID from auth backend response")
        
        # Extract external_user_id from user_data if still not provided
        if not external_user_id:
            external_user_id = user_data.get("id") or user_data.get("user_id")
            if not external_user_id:
                raise ValueError("Could not extract user ID from user_data")
        
        # Check if user exists in local DB
        local_user = db.query(User).filter(User.external_user_id == external_user_id).first()
        
        # Extract user fields (adjust field names based on your auth backend response)
        email = user_data.get("email") or user_data.get("email_address")
        phone = user_data.get("phone") or user_data.get("phone_number")
        username = user_data.get("username") or user_data.get("user_name")
        first_name = user_data.get("first_name") or user_data.get("firstName")
        last_name = user_data.get("last_name") or user_data.get("lastName")
        broker = user_data.get("broker")
        is_active = user_data.get("is_active", user_data.get("isActive", True))
        is_vendor = user_data.get("is_vendor", user_data.get("isVendor", False))
        timezone = user_data.get("timezone", "Asia/Kolkata")
        country = user_data.get("country", "India")
        
        # Store full user data as JSON snapshot
        raw_user_json = user_data
        
        if local_user:
            # Update existing user
            local_user.email = email
            local_user.phone = phone
            local_user.username = username
            local_user.first_name = first_name
            local_user.last_name = last_name
            local_user.broker = broker
            local_user.is_active = is_active
            local_user.is_vendor = is_vendor
            local_user.timezone = timezone
            local_user.country = country
            local_user.raw_user_json = raw_user_json
            # updated_at is automatically updated via ON UPDATE CURRENT_TIMESTAMP
            
            db.commit()
            logger.info(f"Updated user snapshot: external_user_id={external_user_id}, local_id={local_user.id}")
            return local_user
        else:
            # Create new user
            new_user = User(
                external_user_id=external_user_id,
                source="auth_backend",
                email=email,
                phone=phone,
                username=username,
                first_name=first_name,
                last_name=last_name,
                broker=broker,
                is_active=is_active,
                is_vendor=is_vendor,
                timezone=timezone,
                country=country,
                raw_user_json=raw_user_json
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            logger.info(f"Created user snapshot: external_user_id={external_user_id}, local_id={new_user.id}")
            return new_user
            
    except Exception as e:
        # FAIL FAST: Re-raise exception (don't swallow errors)
        logger.error(f"Error syncing user to local DB: {e}", exc_info=True)
        db.rollback()
        raise


def get_or_sync_user(
    db: Session,
    external_user_id: Optional[int] = None,
    authorization: Optional[str] = None
) -> User:
    """
    Get user from local DB, or sync from auth backend if not exists.
    
    FAIL FAST: Raises exception if auth backend unavailable or user not found.
    Prevents creating ghost users in local database.
    
    This is the main function to use in API endpoints.
    
    If external_user_id is not provided, it will be extracted from auth backend response.
    
    Args:
        db: Database session
        external_user_id: Optional user ID from auth backend (will be extracted from auth backend if not provided)
        authorization: Authorization header for auth backend API (required if external_user_id not provided)
    
    Returns:
        User: User model instance (from local DB or newly synced)
    
    Raises:
        requests.exceptions.RequestException: If auth backend is unavailable
        ValueError: If user not found or invalid response
    """
    # If external_user_id not provided, fetch from auth backend
    if external_user_id is None:
        if not authorization:
            raise ValueError("Authorization header required when external_user_id is not provided")
        user_data = fetch_user_from_auth_backend(authorization)
        external_user_id = user_data.get("id") or user_data.get("user_id")
        if not external_user_id:
            raise ValueError("Could not extract user ID from auth backend response")
        # Use fetched user_data directly for sync
        return sync_user_to_local_db(db, external_user_id, authorization, user_data)
    
    # First, try to get from local DB
    local_user = db.query(User).filter(User.external_user_id == external_user_id).first()
    
    if local_user:
        # User exists in local DB - return cached user
        # NOTE: Periodic sync logic can be added later if needed
        return local_user
    else:
        # User not in local DB - fetch from auth backend and create snapshot
        # FAIL FAST: Raises exception if auth backend unavailable
        if not authorization:
            raise ValueError("Authorization header required to fetch user from auth backend")
        return sync_user_to_local_db(db, external_user_id, authorization)


def extract_external_user_id_from_auth(authorization: Optional[str]) -> Optional[int]:
    """
    Extract external user ID from authorization header.
    
    This function should decode JWT token or extract user ID from auth backend response.
    For now, it's a placeholder that extracts from simple header format.
    
    Args:
        authorization: Authorization header value
    
    Returns:
        int: External user ID, or None if not found
    """
    if not authorization:
        return None
    
    try:
        # Simple extraction - in production, decode JWT token
        # Format: "Bearer user_id" or "user_id"
        parts = authorization.split()
        if len(parts) >= 2:
            user_id_str = parts[-1]  # Get last part (user_id)
        else:
            user_id_str = authorization
        
        if not user_id_str or user_id_str == "Bearer":
            return None
        
        # Try to convert to int
        return int(user_id_str)
        
    except (ValueError, AttributeError):
        # If it's not a simple format, you may need to:
        # 1. Decode JWT token
        # 2. Call auth backend to validate token and get user_id
        # 3. Use a session/cookie-based approach
        logger.warning(f"Could not extract user ID from authorization header: {authorization}")
        return None
