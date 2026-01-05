# Fix MSG91 variable names in otp_service.py
file_path = 'apps/delta_backend/auth_app/utils/otp_service.py'

with open(file_path, 'r') as f:
    content = f.read()

# Find and fix the _send_via_msg91 method
# Current payload uses 'otp', 'name', 'time'
# Should use 'VAR1', 'VAR2', 'VAR3' (or whatever the flow expects)

# The message template shows:
# "Hello , Your One-Time Password (OTP) / Verification code for login is {{VAR1}}. valid for {{VAR2}} seconds."
# So we need VAR1=otp, VAR2=time
# VAR3 might be for name if needed

new_method = '''    def _send_via_msg91(self) -> bool:
        try:
            url = "https://api.msg91.com/api/v5/flow"
            payload = {
                "flow_id": config('MSG91_FLOW_ID', default=None),
                "mobiles": self.phone,
                "VAR1": self.otp,      # OTP code
                "VAR2": "120",         # Time in seconds (2 minutes)
                # "VAR3": "User",      # Name if needed by template
            }

            headers = {"authkey": config('MSG91_AUTH_KEY', default=None)}

            response = requests.post(url, json=payload, headers=headers)
            logger.info(f"Msg91 OTP response: {response.status_code} {response.text}")
            return response.status_code == 200
        except Exception as e:
            print(str(e))
            return False'''

# Find and replace the method
import re
pattern = r'def _send_via_msg91\(self\) -> bool:[\s\S]*?except Exception as e:[\s\S]*?print\(str\(e\)\)[\s\S]*?return False'
content = re.sub(pattern, new_method, content, flags=re.DOTALL)

with open(file_path, 'w') as f:
    f.write(content)

print("Fixed MSG91 variable names to match flow template (VAR1=OTP, VAR2=time)")
