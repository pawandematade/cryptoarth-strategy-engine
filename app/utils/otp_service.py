import requests
import logging
from decouple import config

logger = logging.getLogger(__name__)

class OTPService:
    def __init__(self, phone: str, otp: str):
        self.phone = str(phone)
        self.otp = str(otp)

    def send_otp(self, provider="msg91") -> bool:
        try:
            if provider == "aisensy":
                return self._send_via_aisensy()
            elif provider == "msg91":
                return self._send_via_msg91()
            return False
        except Exception as e:
            logger.exception(f"OTP sending failed: {e}")
            return False

    # -------- AISENSY (DGino EXACT) --------
    def _send_via_aisensy(self) -> bool:
        url = "https://backend.aisensy.com/campaign/t1/api/v2"

        payload = {
            "apiKey": config("aisensy_api_key"),
            "campaignName": config("aisensy_campaign_name"),
            "destination": self.phone,
            "userName": config("aisensy_user_name"),
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

        r = requests.post(url, json=payload, headers=headers, timeout=10)
        logger.warning(f"AiSensy RESPONSE: {r.status_code} {r.text}")
        return r.status_code == 200

    # -------- MSG91 --------
    def _send_via_msg91(self) -> bool:
        payload = {
            "flow_id": config("msg91_flow_id"),
            "mobiles": self.phone,
            "otp": self.otp,
            "name": "User",
            "time": "120"
        }

        headers = {"authkey": config("msg91_auth_key")}

        r = requests.post(
            "https://api.msg91.com/api/v5/flow",
            json=payload,
            headers=headers,
            timeout=10
        )
        logger.warning(f"MSG91 RESPONSE: {r.status_code} {r.text}")
        return r.status_code == 200
