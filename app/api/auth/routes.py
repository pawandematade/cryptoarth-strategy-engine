import random

# TEMP OTP SAVE (no-op)

def save_otp(phone: str, otp: str, db=None):

    # OTP sending is primary, persistence optional

    return True

"""
Authentication Routes
Clean FastAPI implementation
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
import logging

from common.db import get_db
from app.api.auth.models import SendOTPRequest, SendOTPResponse
from app.utils.otp_service import OTPService

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/send-otp/", response_model=SendOTPResponse, status_code=status.HTTP_200_OK)

@router.post("/send-otp/")
def send_otp(
    request: SendOTPRequest,
    db: Session = Depends(get_db)
):
    logger.warning("🔥 send_otp API HIT")

    phone = request.phone.strip().replace("+", "")

    # FORCE INDIA FORMAT
    if len(phone) == 10:
        phone = "91" + phone

    # Generate OTP (6 digit)
    otp = str(random.randint(100000, 999999))

    # Save OTP
    try:
        save_otp(phone=phone, otp=otp, db=db)
    except Exception:
        logger.exception("OTP save failed")
        return {"success": False, "message": "OTP save failed"}

    # Send OTP on BOTH channels
    otp_service = OTPService(phone=phone, otp=otp)

    sms = otp_service.send_otp(provider="msg91")
    whatsapp = otp_service.send_otp(provider="aisensy")

    if not sms and not whatsapp:
        return {"success": False, "message": "OTP sending failed"}

    return {"success": True, "message": "OTP sent successfully"}

