import os
import requests
import logging

logger = logging.getLogger(__name__)

class OTPService:
    """
    SINGLE CORRECT OTP SERVICE - DIGNO Django Backend
    Using FLOW API with EXACT working payload
    """
    
    def __init__(self, phone: str, otp: str):
        # Clean phone number
        phone = str(phone).strip()
        
        # Remove + and spaces
        phone = phone.replace("+", "").replace(" ", "")
        
        # Handle country code: if starts with 91 and 12 digits, remove 91
        if phone.startswith("91") and len(phone) == 12:
            phone = phone[2:]  # Remove 91 prefix

        # Handle leading 0
        if phone.startswith("0"):
            phone = phone[1:]

        self.phone = phone
        self.phone_msg91 = "91" + phone if not phone.startswith("91") else phone
        self.otp = otp
        
        logger.debug(f"OTPService initialized: phone={self.phone}, msg91_format={self.phone_msg91}, otp={self.otp}")
    
    def send_otp(self, provider="msg91") -> bool:
        """
        Send OTP via MSG91 Flow API - SIMPLE WORKING VERSION
        """
        try:
            # Read credentials DIRECTLY from .env.production - NO DECOUPLE, NO DJANGO SETTINGS
            env_path = "/var/www/cryptoarth/.env.production"
            
            if not os.path.exists(env_path):
                logger.error(f"❌ .env.production not found at {env_path}")
                return False
            
            auth_key = ""
            flow_id = ""
            
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('msg91_auth_key='):
                        auth_key = line.split('=', 1)[1].strip()
                    elif line.startswith('msg91_flow_id='):
                        flow_id = line.split('=', 1)[1].strip()
            
            logger.debug(f"OTP Credentials from file: auth_key={auth_key[:8] if auth_key else 'MISSING'}..., flow_id={flow_id}")
            
            if not auth_key:
                logger.error("❌ msg91_auth_key missing from .env.production")
                return False
            
            if not flow_id:
                logger.error("❌ msg91_flow_id missing from .env.production")
                return False
            
            # MSG91 Flow API endpoint
            url = "https://api.msg91.com/api/v5/flow/"
            headers = {
                "authkey": auth_key,
                "Content-Type": "application/json"
            }
            
            # WORKING PAYLOAD (based on successful test)
            payload = {
                "flow_id": flow_id,
                "sender": "TDARTH",
                "mobiles": self.phone_msg91,
                "otp": self.otp,
                "name": "User",
                "time": "120"
            }
            
            logger.debug(f"Sending OTP to MSG91 API: {payload}")
            
            # Send request
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            logger.debug(f"MSG91 Response: {response.status_code} - {response.text}")
            
            if response.status_code == 200:
                logger.info(f"✅ OTP {self.otp} sent to {self.phone} via MSG91")
                return True
            else:
                logger.error(f"❌ MSG91 API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"💥 Exception in send_otp: {str(e)}")
            return False
    
    def send_otp_via_whatsapp(self) -> bool:
        """Send OTP via WhatsApp (AiSensy) - optional"""
        try:
            # Read AiSensy credentials
            env_path = "/var/www/cryptoarth/.env.production"
            aisensy_key = ""
            
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    for line in f:
                        if line.startswith('AISENSY_API_KEY='):
                            aisensy_key = line.split('=', 1)[1].strip()
            
            if not aisensy_key:
                logger.warning("⚠️ AiSensy API key not found, falling back to SMS")
                return self.send_otp()
            
            # AiSensy API logic here (simplified)
            logger.info(f"Would send WhatsApp OTP {self.otp} to {self.phone}")
            return False  # For now, fallback to SMS
            
        except Exception as e:
            logger.error(f"💥 WhatsApp error: {e}, falling back to SMS")
            return self.send_otp()
