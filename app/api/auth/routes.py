"""
Authentication Routes
Migrated from cryptoarth_backend/authenticate/views.py

Endpoints:
- POST /auth/send-otp/ - Send OTP to phone number
- POST /auth/signup/ - User signup with OTP verification
- POST /auth/login/ - OTP-based login
- GET  /auth/user/ - Get current authenticated user (JWT required)

Request/Response formats match cryptoarth_backend exactly.
"""
import fastapi
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
import random
import logging
from datetime import datetime, timedelta
import string
import json

from app.database import get_db
from app.models import User
from app.api.auth.models import (
    SendOTPRequest, SendOTPResponse,
    UserSignupRequest, UserSignupResponse, UserSignupErrorResponse,
    OTPLoginRequest, OTPLoginResponse, OTPLoginErrorResponse
)
from app.utils.jwt_helper import decode_token
from app.utils.otp_service import OTPService
import jwt  # PyJWT library (imported as jwt)
from app.store.redis_client import redis_client
from app.config import AUTH_BACKEND_URL
import requests

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/send-otp/", response_model=SendOTPResponse, status_code=status.HTTP_200_OK)
def send_otp(request: SendOTPRequest, db: Session = Depends(get_db)):
    """
    Send OTP to user's phone number.
    Creates user if not exists, generates OTP, and sends via configured providers.
    
    Matches: cryptoarth_backend/authenticate/views.py SendOTPView
    """
    try:
        phone = request.phone
        
        # Basic phone number validation
        if not phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is required."
            )
        
        # Generate 6-digit random OTP
        otp = str(random.randint(100000, 999999))
        
        created_at = datetime.utcnow()
        
        # Store OTP and timestamp in Redis cache for 5 minutes (300 seconds)
        otp_key = f"otp_{phone}"
        otp_data = {
            "otp": otp,
            "created_at": str(created_at)
        }
        redis_client.setex(otp_key, 300, json.dumps(otp_data))  # 5 minutes TTL
        
        # Send OTP via both providers for redundancy
        msg91_success = False
        aisensy_success = False
        
        try:
            OTPService(phone, otp).send_otp(provider="msg91")
            msg91_success = True
        except Exception as e:
            logger.error(f"Msg91 OTP send failed: {e}")
        
        try:
            OTPService(phone, otp).send_otp(provider="aisensy")
            aisensy_success = True
        except Exception as e:
            logger.error(f"AiSensy OTP send failed: {e}")
        
        # Return success only if at least one provider succeeded
        if not msg91_success and not aisensy_success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send OTP via all providers."
            )
        
        return SendOTPResponse(message="OTP sent successfully.")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending OTP: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to send OTP. Error: {str(e)}"
        )


def generate_unique_refercode(db: Session) -> str:
    """
    Generate a unique refercode that doesn't exist in the database.
    Format: 6-8 characters alphanumeric (uppercase letters and digits)
    """
    while True:
        # Generate refercode with 6-8 characters
        length = random.randint(6, 8)
        refercode = ''.join(random.choices(
            string.ascii_uppercase + string.digits,
            k=length
        ))
        
        # Check if refercode already exists in database
        existing = db.query(User).filter(User.username == refercode).first()
        if not existing:
            return refercode


@router.post("/signup/", response_model=UserSignupResponse, status_code=status.HTTP_201_CREATED)
def signup(request: UserSignupRequest, db: Session = Depends(get_db)):
    """
    User signup with OTP verification.
    Creates user and returns JWT tokens.
    
    Matches: cryptoarth_backend/authenticate/views.py SignupView
    """
    try:
        phone = request.phone
        email = request.email
        otp = request.otp
        
        # Validate email is required and provided
        if not email or email.strip() == '':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Email is required", "status": False}
            )
        
        # Check if email already exists
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Email already registered with another user", "status": False}
            )
        
        # Check if phone number already exists
        existing_phone = db.query(User).filter(User.phone == phone).first()
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "The phone no. is already taken", "status": False}
            )
        
        # Validate OTP presence
        if not otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "OTP is required", "status": False}
            )
        
        # Check OTP from Redis cache
        otp_key = f"otp_{phone}"
        cached_otp_data_str = redis_client.get(otp_key)
        if not cached_otp_data_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "OTP expired or not found.", "status": False}
            )
        
        # Parse cached OTP data (stored as JSON string)
        try:
            cached_otp_data = json.loads(cached_otp_data_str)
        except:
            # Fallback: try to extract OTP directly if stored as simple string
            cached_otp_data = {"otp": cached_otp_data_str}
        
        if cached_otp_data.get('otp') != otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Invalid OTP.", "status": False}
            )
        
        # Generate unique refercode and username
        refercode = generate_unique_refercode(db)
        username = refercode
        
        # CRITICAL: external_user_id must be deterministic and compatible with existing Django users
        # Strategy: Check if user exists in Django backend, reuse their ID if found
        # If new user, use sequence starting from high number to avoid conflicts with Django IDs
        external_user_id = None
        
        # Check if user exists in Django backend by phone
        try:
            django_user_url = f"{AUTH_BACKEND_URL}/auth/users/phone/{phone}/"
            django_user_response = requests.get(django_user_url, timeout=5)
            
            if django_user_response.status_code == 200:
                # User exists in Django - reuse their ID
                django_user_data = django_user_response.json()
                external_user_id = django_user_data.get("id") or django_user_data.get("user_id")
                if not external_user_id:
                    logger.warning(f"User found in Django but no ID in response: {django_user_data}")
        except requests.exceptions.RequestException as e:
            logger.debug(f"Could not check Django backend for existing user: {e}")
            # Continue - will generate new ID
        
        # If user not found in Django, check if exists in strategy-engine
        if not external_user_id:
            existing_local = db.query(User).filter(
                (User.phone == phone) | (User.email == email)
            ).first()
            if existing_local:
                # User exists locally - reuse their external_user_id
                external_user_id = existing_local.external_user_id
                user = existing_local
                # Update user data
                user.email = email
                user.phone = phone
                user.username = username
                user.first_name = request.first_name
                user.last_name = request.last_name or ""
                user.is_active = True
                db.commit()
                db.refresh(user)
            else:
                # New user - generate deterministic external_user_id
                # Use sequence starting from 1000000 to avoid conflicts with Django IDs (typically < 1000000)
                # Get max external_user_id and add 1, ensuring it's >= 1000000
                max_id_result = db.query(func.max(User.external_user_id)).scalar()
                if max_id_result and max_id_result >= 1000000:
                    external_user_id = max_id_result + 1
                else:
                    external_user_id = 1000000  # Start from 1000000 for new users
                
                # Ensure uniqueness
                while db.query(User).filter(User.external_user_id == external_user_id).first():
                    external_user_id += 1
                
                # Create new user
                user = User(
                    external_user_id=external_user_id,
                    email=email,
                    phone=phone,
                    username=username,
                    first_name=request.first_name,
                    last_name=request.last_name or "",
                    is_active=True,
                    source="auth_signup"
                )
                db.add(user)
                db.commit()
                db.refresh(user)
        else:
            # User exists in Django - check if exists locally, if not create
            existing_local = db.query(User).filter(User.external_user_id == external_user_id).first()
            if existing_local:
                # User exists locally - reuse
                user = existing_local
                # Update user data
                user.email = email
                user.phone = phone
                user.username = username
                user.first_name = request.first_name
                user.last_name = request.last_name or ""
                user.is_active = True
                db.commit()
                db.refresh(user)
            else:
                # Create new user with Django's ID
                user = User(
                    external_user_id=external_user_id,
                    email=email,
                    phone=phone,
                    username=username,
                    first_name=request.first_name,
                    last_name=request.last_name or "",
                    is_active=True,
                    source="auth_signup"
                )
                db.add(user)
                db.commit()
                db.refresh(user)
        
        # Generate JWT tokens for the new user
        tokens = user.get_tokens()
        
        # Delete OTP from cache after successful verification
        redis_client.delete(otp_key)
        
        return UserSignupResponse(
            message="User registered successfully.",
            status=True,
            access=tokens['access'],
            refresh=tokens['refresh']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in signup: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "User registration failed.", "status": False, "errors": {"detail": str(e)}}
        )


@router.post("/login/", response_model=OTPLoginResponse, status_code=status.HTTP_200_OK)
def otp_login(request: OTPLoginRequest, db: Session = Depends(get_db)):
    """
    OTP-based login.
    Validates OTP and returns JWT tokens.
    
    Matches: cryptoarth_backend/authenticate/views.py OTPLoginView
    """
    try:
        phone = request.phone
        otp = request.otp
        
        # Special test OTPs (matching cryptoarth_backend)
        test_phones = ["918369354566", "919145013254", "9199711111131"]
        test_otp = "987654"
        
        if phone in test_phones and otp == test_otp:
            user = db.query(User).filter(User.phone == phone).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found."
                )
            
            tokens = user.get_tokens()
            
            return OTPLoginResponse(
                message="Login successful.",
                access=tokens['access'],
                refresh=tokens['refresh'],
                user_id=user.external_user_id
            )
        
        # Normal OTP validation
        otp_key = f"otp_{phone}"
        cached_otp_data_str = redis_client.get(otp_key)
        
        # Check if OTP exists and matches
        if not cached_otp_data_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP expired or not found."
            )
        
        # Parse cached OTP data (stored as JSON string)
        try:
            cached_otp_data = json.loads(cached_otp_data_str)
        except:
            cached_otp_data = {"otp": cached_otp_data_str}
        
        if cached_otp_data.get('otp') != otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP."
            )
        
        # Get user by phone number
        user = db.query(User).filter(User.phone == phone).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )
        
        # Generate JWT tokens for the authenticated user
        tokens = user.get_tokens()
        
        return OTPLoginResponse(
            message="Login successful.",
            access=tokens['access'],
            refresh=tokens['refresh'],
            user_id=user.external_user_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in OTP login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(e), "status": False}
        )


@router.get("/user/", status_code=status.HTTP_200_OK)
def get_current_user(
    authorization: Optional[str] = fastapi.Header(None),
    db: Session = Depends(get_db)
):
    """
    Get current authenticated user information.
    Validates JWT token and returns user details.
    
    This is a READ-ONLY endpoint - no database writes.
    Returns 401 if token is invalid or expired.
    
    Matches: cryptoarth_backend/authenticate/views.py GetCurrentUserView
    """
    try:
        # Validate authorization header
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        # Extract token from "Bearer <token>" format
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format. Expected: Bearer <token>"
            )
        
        token = authorization.replace("Bearer ", "").strip()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is required"
            )
        
        # Decode and validate JWT token
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
        
        # Extract user_id from token payload
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: user_id not found"
            )
        
        # Query user from database using external_user_id
        user = db.query(User).filter(User.external_user_id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive"
            )
        
        # Return user data in format compatible with frontend expectations
        # Frontend expects array format or object with id, email, phone, etc.
        return {
            "id": user.external_user_id,
            "user_id": user.external_user_id,
            "email": user.email or "",
            "phone": user.phone or "",
            "username": user.username or "",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "firstname": user.first_name or "",  # Alternative field name for compatibility
            "lastname": user.last_name or "",    # Alternative field name for compatibility
            "name": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or "",
            "is_staff": False,  # Admin flag (can be extended later)
            "is_vendor": user.is_vendor or False,
            "is_active": user.is_active,
            "role": "ADMIN" if False else "USER"  # Role based on is_staff (can be extended)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user information"
        )

