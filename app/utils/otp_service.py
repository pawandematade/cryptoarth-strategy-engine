"""
OTP Service
Sends OTP via AiSensy or Msg91 providers.
Migrated from cryptoarth_backend/authenticate/utils/otp_service.py
"""
import requests
import logging
from decouple import config

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
            # Use decouple.config like Django - matches working implementation exactly
            api_key = config('AISENSY_API_KEY', default=None) or config('aisensy_api_key', default=None)
            campaign_name = config('AISENSY_CAMPAIGN_NAME', default=None) or config('aisensy_campaign_name', default=None)
            user_name = config('AISENSY_USER_NAME', default=None) or config('aisensy_user_name', default=None)
            
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
            # Use decouple.config like Django - matches working implementation exactly
            flow_id = config('MSG91_FLOW_ID', default=None) or config('msg91_flow_id', default=None)
            auth_key = config('MSG91_AUTH_KEY', default=None) or config('msg91_auth_key', default=None)
            
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

