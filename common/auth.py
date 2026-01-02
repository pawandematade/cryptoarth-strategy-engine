"""
Authentication utilities - JWT, user context
Shared infrastructure for authentication
"""
from fastapi import HTTPException, Depends, Header, Request, status
from sqlalchemy.orm import Session
from typing import Optional
import logging
import jwt
from common.db import get_db
from app.models import User
from app.utils.jwt_helper import decode_token

logger = logging.getLogger(__name__)


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """
    Standard auth dependency for authenticated routes.
    Loads user from DB using external_user_id from JWT token.
    """
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
    
    external_user_id = payload.get("user_id")
    if not external_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: user_id not found"
        )
    
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
    
