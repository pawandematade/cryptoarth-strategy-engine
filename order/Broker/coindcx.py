import hmac
import hashlib
import base64
import json
import time
import requests

class coindcxclient:
    def __init__(self, api_key, api_secret, base_url='https://api.coindcx.com/exchange/v1'):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.bytes = bytes(api_secret, encoding='utf-8')

    def _generate_signature(self,body):
        return hmac.new(self.bytes, body.encode(), hashlib.sha256).hexdigest()
    
    def get_timestamp(self):
        return int(round(time.time() * 1000))
    
    def _make_authenticated_request(self, method, endpoint, body=None):
        url = self.base_url + endpoint
        if body is None:
            body = {}
       
        json_body = json.dumps(body, separators = (',', ':'))
        signature = self._generate_signature(json_body)
        
        headers = {
            'Content-Type': 'application/json',
            'X-AUTH-APIKEY': self.api_key,
            'X-AUTH-SIGNATURE': signature
        }
        
        response = requests.request(method, url, headers=headers, data=json_body if body else None)
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(response.json())


    def get_account_info(self):
        try:
            timeStamp = self.get_timestamp()

            body = {
                "timestamp": timeStamp
                }
        
            return  {'success': True, 'result': self._make_authenticated_request('POST', '/users/info',body)}
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {'success': False, 'error': str(e)}
        
    def get_wallet_info(self):
        try:
            timeStamp = self.get_timestamp()

            body = {
                "timestamp": timeStamp
                }
            data = self._make_authenticated_request('GET', '/derivatives/futures/wallets',body) 
 
            usdt_balance = next((item['balance'] for item in data if item['currency_short_name'] == 'INR'), 0)
            return round(float(usdt_balance),3)
            
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {'success': False, 'error': str(e)}
        
    def get_usdt_conversion(self):
        try:
            timeStamp = self.get_timestamp()

            body = {
                "timestamp": timeStamp
                }
            data = self._make_authenticated_request('GET', '/derivatives/futures/data/conversions',body) 
            return data
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {'success': False, 'error': str(e)}

        
    def get_positions_coindcx(self,symbol):
        try:
            timeStamp = self.get_timestamp()

            body = {
                "timestamp": timeStamp,  # EPOCH timestamp in seconds
            
                "pairs": symbol,
                "margin_currency_short_name": ["INR"]

            }
            return self._make_authenticated_request('POST', '/derivatives/futures/positions',body)
        except Exception as e:
            
            return {'success': False, 'error': str(e)}
        
    def get_order_by_id_coindcx(self,order_id):
        try:
            timeStamp = self.get_timestamp()

            body = {
            "timestamp":timeStamp, # EPOCH timestamp in seconds
           
            "order_id": order_id # order.id
            
            }
            return self._make_authenticated_request('POST', '/derivatives/futures/trades',body)
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {'success': False, 'error': str(e)}
        
    def get_orders_coindcx(self,symbol=None,limit=10):
        try:
            timeStamp = self.get_timestamp()

            body = {
            "timestamp":timeStamp, # EPOCH timestamp in seconds
            "pair": symbol,
            "size": limit
            }
           
            return self._make_authenticated_request('POST', '/derivatives/futures/trades',body)
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {'success': False, 'error': str(e)}
        
    def place_order_coindcx(self,side,symbol,qty,leverage):
        try:
            timeStamp = self.get_timestamp()
            body = {
                "timestamp":timeStamp ,
                "order": {
                "side": side, 
                "pair": symbol, 
                "order_type": "market_order", 
                "total_quantity": qty, 
                "leverage": leverage, 
                "time_in_force": "good_till_cancel", 
                "margin_currency_short_name":"INR"
                }
            }
            return {'success': True, 'result': self._make_authenticated_request('POST', '/derivatives/futures/orders/create',body)} 
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {'success': False, 'error': e}

