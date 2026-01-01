"""
JWT Token Helper
Generates JWT tokens compatible with rest_framework_simplejwt format.
"""
import jwt
from datetime import datetime, timedelta
from typing import Dict
from app.config import SECRET_KEY
import logging

logger = logging.getLogger(__name__)

# JWT settings matching Django REST Framework SimpleJWT defaults
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_LIFETIME = timedelta(minutes=60)  # 1 hour
REFRESH_TOKEN_LIFETIME = timedelta(days=1)     # 1 day


def generate_tokens(user_id: int, username: str = None) -> Dict[str, str]:
    """
    Generate JWT access and refresh tokens for a user.
    Compatible with rest_framework_simplejwt format.
    
    Args:
        user_id: User ID (external_user_id from User model)
        username: Optional username
        
    Returns:
        Dict with 'access' and 'refresh' tokens
    """
    now = datetime.utcnow()
    
    # Access token payload
    access_payload = {
        "token_type": "access",
        "exp": now + ACCESS_TOKEN_LIFETIME,
        "iat": now,
        "jti": f"access_{user_id}_{int(now.timestamp())}",
        "user_id": user_id,
    }
    if username:
        access_payload["username"] = username
    
    # Refresh token payload
    refresh_payload = {
        "token_type": "refresh",
        "exp": now + REFRESH_TOKEN_LIFETIME,
        "iat": now,
        "jti": f"refresh_{user_id}_{int(now.timestamp())}",
        "user_id": user_id,
    }
    if username:
        refresh_payload["username"] = username
    
    # Generate tokens
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=JWT_ALGORITHM)
    refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    return {
        "access": access_token,
        "refresh": refresh_token
    }


def decode_token(token: str) -> Dict:
    """
    Decode and validate JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload
        
    Raises:
        jwt.ExpiredSignatureError: If token is expired
        jwt.InvalidTokenError: If token is invalid
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])

