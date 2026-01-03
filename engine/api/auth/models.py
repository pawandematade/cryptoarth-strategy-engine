"""
Pydantic models for authentication requests and responses.
Matches Django REST Framework serializer format exactly.
"""
from pydantic import BaseModel, Field
from typing import Optional


class SendOTPRequest(BaseModel):
    """Request model for sending OTP"""
    phone: str = Field(..., max_length=15, description="Phone number")


class SendOTPResponse(BaseModel):
    """Response model for sending OTP"""
    message: str


class UserSignupRequest(BaseModel):
    """Request model for user signup"""
    phone: str = Field(..., max_length=15)
    refercode: Optional[str] = Field(None, max_length=100)
    email: str = Field(..., max_length=255)
    first_name: str = Field(..., max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    otp: str = Field(..., min_length=6, max_length=6)


class UserSignupResponse(BaseModel):
    """Response model for user signup"""
    message: str
    status: bool
    access: str
    refresh: str


class UserSignupErrorResponse(BaseModel):
    """Error response model for user signup"""
    message: str
    status: bool
    errors: dict


class OTPLoginRequest(BaseModel):
    """Request model for OTP login"""
    phone: str = Field(..., max_length=15)
    otp: str = Field(..., max_length=6)


class OTPLoginResponse(BaseModel):
    """Response model for OTP login"""
    message: str
    access: str
    refresh: str
    user_id: int


class OTPLoginErrorResponse(BaseModel):
    """Error response model for OTP login"""
    message: str
    status: bool

