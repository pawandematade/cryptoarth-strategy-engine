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

    def send_otp(self, provider="msg91") -> bool:
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
                "apiKey": config('aisensy_api_key', default=None), 
                "campaignName": config('aisensy_campaign_name', default=None),
                "destination": self.phone,
                "userName": config('aisensy_user_name', default=None),
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
            print(str(e))
            return False

    def _send_via_msg91(self) -> bool:
        try:
            url = "https://api.msg91.com/api/v5/flow"
            payload = {
                "flow_id": config('msg91_flow_id', default=None),  
                "mobiles": self.phone,
                "otp": self.otp,
                "name": "User",
                "time": "120"
            }
            
            headers = {"authkey": config('msg91_auth_key', default=None)}  

            response = requests.post(url, json=payload, headers=headers)
            logger.info(f"Msg91 OTP response: {response.status_code} {response.text}")
            return response.status_code == 200
        except Exception as e:
            print(str(e))
            return False
