"""
OTP Service
Sends OTP via AiSensy or Msg91 providers.
Migrated from cryptoarth_backend/authenticate/utils/otp_service.py
"""
import requests
import logging
import os

# Try to use decouple.config (like Django), fallback to os.getenv if not available
try:
    from decouple import config as _decouple_config
    def config(key, default=None):
        """Use decouple.config if available (matches Django)"""
        return _decouple_config(key, default=default)
except ImportError:
    # Fallback to os.getenv if decouple not available
    # Ensure environment is loaded via common.config first
    from common.config import IS_PRODUCTION  # This triggers env loading
    def config(key, default=None):
        """Fallback to os.getenv if decouple not available"""
        return os.getenv(key, default) or os.getenv(key.upper(), default) or os.getenv(key.lower(), default)

logger = logging.getLogger(__name__)


class OTPService:
    """
    Base class to send OTP via AiSensy or Msg91
    """

    def __init__(self, phone: str, otp: str):
        self.phone = str(phone)
        self.otp = str(otp)

    def send_otp(self, provider: str = "msg91") -> bool:
        """
        Dispatch OTP based on provider
        """
        try:
            if provider == "aisensy":
                return self._send_via_aisensy()
            elif provider == "msg91":
                return self._send_via_msg91()
            else:
                raise ValueError(f"Unsupported provider: {provider}")
        except Exception as e:
            logger.exception(f"OTP sending failed: {str(e)}")
            return False

    def _send_via_aisensy(self) -> bool:
        try:
            # Use config (decouple or os.getenv fallback) - matches Django implementation
            api_key = config('AISENSY_API_KEY') or config('aisensy_api_key')
            campaign_name = config('AISENSY_CAMPAIGN_NAME') or config('aisensy_campaign_name')
            user_name = config('AISENSY_USER_NAME') or config('aisensy_user_name')
            
            if not api_key or not campaign_name or not user_name:
                logger.error(f"AiSensy config missing: api_key={bool(api_key)}, campaign_name={bool(campaign_name)}, user_name={bool(user_name)}")
                return False
            
            url = "https://backend.aisensy.com/campaign/t1/api/v2"
            payload = {
                "apiKey": api_key,
                "campaignName": campaign_name,
                "destination": self.phone,
                "userName": user_name,
                "templateParams": [self.otp],
                "source": "new-landing-page form",
                "media": {},
                "buttons": [
                    {
                        "type": "button",
                        "sub_type": "url",
                        "index": 0,
                        "parameters": [
                            {
                                "type": "text",
                                "text": self.otp
                            }
                        ]
                    }
                ],
                "carouselCards": [],
                "location": {},
                "attributes": {},
                "paramsFallbackValue": {
                    "FirstName": self.otp
                }
            }
            headers = {"Content-Type": "application/json"}

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            logger.info(f"AiSensy OTP response: {response.status_code} {response.text}")
            
            if response.status_code != 200:
                logger.error(f"AiSensy API returned {response.status_code}: {response.text}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"AiSensy OTP error: {str(e)}", exc_info=True)
            return False

    def _send_via_msg91(self) -> bool:
        try:
            # Use config (decouple or os.getenv fallback) - matches Django implementation
            flow_id = config('MSG91_FLOW_ID') or config('msg91_flow_id')
            auth_key = config('MSG91_AUTH_KEY') or config('msg91_auth_key')
            
            if not flow_id or not auth_key:
                logger.error(f"Msg91 config missing: flow_id={bool(flow_id)}, auth_key={bool(auth_key)}")
                return False
            
            url = "https://api.msg91.com/api/v5/flow"
            payload = {
                "flow_id": flow_id,
                "mobiles": self.phone,
                "otp": self.otp,
                "name": "User",
                "time": "120"
            }
            
            headers = {"authkey": auth_key}

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            logger.info(f"Msg91 OTP response: {response.status_code} {response.text}")
            
            if response.status_code != 200:
                logger.error(f"Msg91 API returned {response.status_code}: {response.text}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Msg91 OTP error: {str(e)}", exc_info=True)
            return False

