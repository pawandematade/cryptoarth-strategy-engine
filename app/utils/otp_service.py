"""
OTP Service
Sends OTP via AiSensy or Msg91 providers.
Migrated from cryptoarth_backend/authenticate/utils/otp_service.py
"""
import requests
import logging
import os
from typing import Optional

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
            url = "https://backend.aisensy.com/campaign/t1/api/v2"
            payload = {
                "apiKey": os.getenv("aisensy_api_key"),
                "campaignName": os.getenv("aisensy_campaign_name"),
                "destination": self.phone,
                "userName": os.getenv("aisensy_user_name"),
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

            response = requests.post(url, json=payload, headers=headers)
            logger.info(f"AiSensy OTP response: {response.status_code} {response.text}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"AiSensy OTP error: {str(e)}")
            return False

    def _send_via_msg91(self) -> bool:
        try:
            url = "https://api.msg91.com/api/v5/flow"
            payload = {
                "flow_id": os.getenv("msg91_flow_id"),
                "mobiles": self.phone,
                "otp": self.otp,
                "name": "User",
                "time": "120"
            }
            
            headers = {"authkey": os.getenv("msg91_auth_key")}

            response = requests.post(url, json=payload, headers=headers)
            logger.info(f"Msg91 OTP response: {response.status_code} {response.text}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Msg91 OTP error: {str(e)}")
            return False

