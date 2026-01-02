import hashlib
import hmac
import requests
import time
import json
from typing import Optional, List, Dict, Any

class DeltaExchangeClient:
    def __init__(self, api_key, api_secret, base_url='https://api.india.delta.exchange'):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
    
    def generate_signature(self, secret, message):
        """Generate HMAC SHA256 signature for authentication"""
        message = bytes(message, 'utf-8')
        secret = bytes(secret, 'utf-8')
        hash = hmac.new(secret, message, hashlib.sha256)
        return hash.hexdigest()
    

    
    def place_order(self, product_symbol=None, product_id=None, size=None, side=None, 
                   order_type='market_order', limit_price=None, stop_price=None, 
                   stop_order_type=None, time_in_force='gtc', post_only=False, 
                   reduce_only=False, client_order_id=None):
        """
        Place an order on Delta Exchange
        
        Args:
            product_symbol (str): Product symbol (e.g., 'BTCUSD') - use either this or product_id
            product_id (int): Product ID - use either this or product_symbol
            size (int): Order size (must be integer, no fractional values)
            side (str): 'buy' or 'sell'
            order_type (str): 'limit_order' or 'market_order'
            limit_price (str): Price for limit orders (required for limit orders)
            stop_price (str): Stop price for stop orders
            stop_order_type (str): 'stop_loss_order' or 'take_profit_order'
            time_in_force (str): 'gtc' or 'ioc'
            post_only (bool): Post only order flag
            reduce_only (bool): Reduce only order flag
            client_order_id (str): Custom client order ID
        
        Returns:
            dict: API response containing order details
        """
        
        # Validate required parameters
        if not product_symbol and not product_id:
            raise ValueError("Either product_symbol or product_id must be provided")
        
        if not size or not isinstance(size, int):
            raise ValueError("Size must be provided as an integer (no fractional values allowed)")
        
        if side not in ['buy', 'sell']:
            raise ValueError("Side must be 'buy' or 'sell'")
        
        if order_type not in ['limit_order', 'market_order']:
            raise ValueError("Order type must be 'limit_order' or 'market_order'")
        
        if order_type == 'limit_order' and not limit_price:
            raise ValueError("Limit price is required for limit orders")
        
        # Prepare order payload
        order_data = {
            'size': size,
            'side': side,
            'order_type': order_type,
            'time_in_force': time_in_force,
            'post_only': str(post_only).lower(),
            'reduce_only': str(reduce_only).lower()
        }
        
        # Add product identifier
        if product_symbol:
            order_data['product_symbol'] = product_symbol
        else:
            order_data['product_id'] = product_id
        
        # Add optional parameters
        if limit_price:
            order_data['limit_price'] = str(limit_price)
        
        if stop_price:
            order_data['stop_price'] = str(stop_price)
        
        if stop_order_type:
            order_data['stop_order_type'] = stop_order_type
        
        if client_order_id:
            order_data['client_order_id'] = str(client_order_id)
        
        # Prepare request
        method = 'POST'
        timestamp = str(int(time.time()))
        path = '/v2/orders'
        url = f'{self.base_url}{path}'
        query_string = ''
        payload = json.dumps(order_data)
        
        # Generate signature
        signature_data = method + timestamp + path + query_string + payload
        signature = self.generate_signature(self.api_secret, signature_data)
        
        # Prepare headers
        headers = {
            'api-key': self.api_key,
            'timestamp': timestamp,
            'signature': signature,
            'User-Agent': 'python-rest-client',
            'Content-Type': 'application/json'
        }
        
        try:
            # Make the request
            response = requests.request(
                method, url, data=payload, params={}, 
                timeout=(3, 27), headers=headers
            )
            
            # Parse response
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('success'):
                print("Order placed successfully!")
                return response_data
            else:
                print(f"Error placing order: {response_data}")
                return response_data
                
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"Failed to parse response: {e}")
            return None
        
    
    def _make_authenticated_request(self, method: str, path: str, params: Dict = None) -> Dict:
        """Make an authenticated request to Delta Exchange API"""
        timestamp = str(int(time.time()))
        url = f'{self.base_url}{path}'
        
        # Build query string for GET requests
        query_string = ''
        if params:
            query_params = []
            for key, value in params.items():
                if value is not None:
                    if isinstance(value, list):
                        query_params.append(f"{key}={','.join(map(str, value))}")
                    else:
                        query_params.append(f"{key}={value}")
            if query_params:
                query_string = '?' + '&'.join(query_params)
        
        payload = ''
        signature_data = method + timestamp + path + query_string + payload
        signature = self.generate_signature(self.api_secret, signature_data)
        
        headers = {
            'api-key': self.api_key,
            'timestamp': timestamp,
            'signature': signature,
            'User-Agent': 'python-rest-client',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.request(
                method, url, data=payload, params=params,
                timeout=(3, 27), headers=headers
            )
            
            response_data = response.json()
            if response.status_code == 200 and response_data.get('success'):
                return response_data
            else:
                print(f"API Error: {response_data}")
                return response_data
                
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {'success': False, 'error': str(e)}
        
    def get_orders_history(self, 
                    product_ids: Optional[List[int]] = None,
                    states: Optional[List[str]] = None,
                    contract_types: Optional[List[str]] = None,
                    order_types: Optional[List[str]] = None,
                    start_time: Optional[int] = None,
                    end_time: Optional[int] = None,
                    after: Optional[str] = None,
                    before: Optional[str] = None,
                    page_size: int = 10) -> Dict:
        """
        Get active orders with various filtering options
        
        Args:
            product_ids: List of product IDs to filter by
            states: List of order states ('open', 'pending', 'closed', 'cancelled')
            contract_types: List of contract types ('futures', 'perpetual_futures', 'call_options', 'put_options')
            order_types: List of order types ('market', 'limit', 'stop_market', 'stop_limit', 'all_stop')
            start_time: Start time in microseconds (epoch)
            end_time: End time in microseconds (epoch)
            after: Cursor for pagination (next page)
            before: Cursor for pagination (previous page)
            page_size: Number of records per page (default: 10)
        
        Returns:
            Dict containing order list and pagination metadata
        """
        params = {}
        
        if product_ids:
            params['product_ids'] = product_ids
        if states:
            params['states'] = states
        if contract_types:
            params['contract_types'] = contract_types
        if order_types:
            params['order_types'] = order_types
        if start_time:
            params['start_time'] = start_time
        if end_time:
            params['end_time'] = end_time
        if after:
            params['after'] = after
        if before:
            params['before'] = before
        if page_size:
            params['page_size'] = page_size
        
        return self._make_authenticated_request('GET', '/v2/orders/history', params)

    def get_orders(self, 
                   product_ids: Optional[List[int]] = None,
                   states: Optional[List[str]] = None,
                   contract_types: Optional[List[str]] = None,
                   order_types: Optional[List[str]] = None,
                   start_time: Optional[int] = None,
                   end_time: Optional[int] = None,
                   after: Optional[str] = None,
                   before: Optional[str] = None,
                   page_size: int = 10) -> Dict:
        """
        Get active orders with various filtering options
        
        Args:
            product_ids: List of product IDs to filter by
            states: List of order states ('open', 'pending', 'closed', 'cancelled')
            contract_types: List of contract types ('futures', 'perpetual_futures', 'call_options', 'put_options')
            order_types: List of order types ('market', 'limit', 'stop_market', 'stop_limit', 'all_stop')
            start_time: Start time in microseconds (epoch)
            end_time: End time in microseconds (epoch)
            after: Cursor for pagination (next page)
            before: Cursor for pagination (previous page)
            page_size: Number of records per page (default: 10)
        
        Returns:
            Dict containing order list and pagination metadata
        """
        params = {}
        
        if product_ids:
            params['product_ids'] = product_ids
        if states:
            params['states'] = states
        if contract_types:
            params['contract_types'] = contract_types
        if order_types:
            params['order_types'] = order_types
        if start_time:
            params['start_time'] = start_time
        if end_time:
            params['end_time'] = end_time
        if after:
            params['after'] = after
        if before:
            params['before'] = before
        if page_size:
            params['page_size'] = page_size
        
        return self._make_authenticated_request('GET', '/v2/orders', params)


    def get_order_by_id(self, order_id: int) -> Dict:
        """
        Get a specific order by its ID
        
        Args:
            order_id: The order ID to retrieve
        
        Returns:
            Dict containing order details
        """
        path = f'/v2/orders/{order_id}'
        return self._make_authenticated_request('GET', path)
    

    def set_leverage1(self, product_id: int, leverage: int) -> Dict:
        method = 'POST'
        timestamp = str(int(time.time()))
        path = f'/v2/products/{product_id}/orders/leverage'
        url = f'{self.base_url}{path}'
        query_string = ''
        payload1 = {"leverage": str(leverage)}
        payload = json.dumps(payload1)
        
        # Generate signature
        signature_data = method + timestamp + path + query_string + payload
        signature = self.generate_signature(self.api_secret, signature_data)
        
        # Prepare headers
        headers = {
            'api-key': self.api_key,
            'timestamp': timestamp,
            'signature': signature,
            'User-Agent': 'python-rest-client',
            'Content-Type': 'application/json'
        }
        
        try:
            # Make the request
            response = requests.request(
                method, url, data=payload, params={}, 
                timeout=(3, 27), headers=headers
            )
            
            # Parse response
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('success'):
                print("Leverage changes successfully.")
                return response_data
            else:
                print(f"Error changing order: {response_data}")
                return response_data
                
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"Failed to parse response: {e}")
            return None


    def set_leverage(self, product_id: int, leverage: int) -> Dict:
        """
        Set leverage for a specific product
        """
        path = f'/v2/products/{product_id}/orders/leverage'
        payload = {"leverage": str(leverage)}
        return self._make_authenticated_request('POST', path, payload=payload)

    def get_open_orders(self, product_ids: Optional[List[int]] = None) -> Dict:
        """
        Convenience method to get only open orders
        
        Args:
            product_ids: List of product IDs to filter by
        
        Returns:
            Dict containing open orders
        """
        return self.get_orders(product_ids=product_ids, states=['open'])
    
    def get_pending_orders(self, product_ids: Optional[List[int]] = None) -> Dict:
        """
        Convenience method to get only pending orders
        
        Args:
            product_ids: List of product IDs to filter by
        
        Returns:
            Dict containing pending orders
        """
        return self.get_orders(product_ids=product_ids, states=['pending'])
    
    def get_account_info(self) -> Dict:
        """
        Get account profile and balance information

        Returns:
            Dict containing account details (balances, margin info, etc.)
        """
        path = '/v2/profile'
        return self._make_authenticated_request('GET', path)

    
    def get_balances(self, currency_codes: Optional[List[str]] = None) -> Dict:
        """
        Get wallet balances for all currencies or specific currencies
        
        Args:
            currency_codes: List of currency codes to filter by (e.g., ['BTC', 'USDT', 'ETH'])
                           If None, returns all balances
        
        Returns:
            Dict containing wallet balances
        """
        path = '/v2/wallet/balances'
        params = {}
        
        if currency_codes:
            params['currency_codes'] = currency_codes
        
        return self._make_authenticated_request('GET', path, params)
    
    def _make_authenticated_request1(self, method: str, path: str, params: Dict = None, payload: Dict = None) -> Dict:
        """Make an authenticated request to Delta Exchange API"""
        timestamp = str(int(time.time()))
        url = f'{self.base_url}{path}'
        
        # Build query string for GET requests
        query_string = ''
        if method == 'GET' and params:
            query_params = []
            for key, value in params.items():
                if value is not None:
                    if isinstance(value, list):
                        query_params.append(f"{key}={','.join(map(str, value))}")
                    else:
                        query_params.append(f"{key}={value}")
            if query_params:
                query_string = '?' + '&'.join(query_params)
        
        # Handle payload for POST/PUT requests
        payload_str = ''
        if method in ['POST', 'PUT'] and payload:
            payload_str = json.dumps(payload)
        
        signature_data = method + timestamp + path + query_string + payload_str
        signature = self.generate_signature(self.api_secret, signature_data)
        
        headers = {
            'api-key': self.api_key,
            'timestamp': timestamp,
            'signature': signature,
            'User-Agent': 'python-rest-client',
            'Content-Type': 'application/json'
        }
        
        try:
            if method == 'GET':
                response = requests.request(
                    method, url, params=params,
                    timeout=(3, 27), headers=headers
                )
            else:  # POST/PUT
                response = requests.request(
                    method, url, data=payload_str,
                    timeout=(3, 27), headers=headers
                )
            
            # Handle empty response
            if response.text.strip() == '':
                return {'success': False, 'error': 'Empty response from server'}
            
            response_data = response.json()
            if response.status_code == 200 and response_data.get('success'):
                return response_data
            else:
                print(f"API Error: {response_data}")
                return response_data
                
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return {'success': False, 'error': str(e)}
        except json.JSONDecodeError as e:
            print(f"Failed to parse response: {response.text}")
            return {'success': False, 'error': f'JSON decode error: {e}'}
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {'success': False, 'error': str(e)}

    def get_user_id(self) -> str:
        """
        Get the current user's ID from profile
        
        Returns:
            str: User ID or None if failed
        """
        try:
            profile_data = self.get_account_info()
            if profile_data.get('success') and 'result' in profile_data:
                user_id = profile_data['result'].get('id')
                return str(user_id) if user_id else None
            return None
        except Exception as e:
            print(f"Failed to get user ID: {e}")
            return None

    def set_margin_type_portfolio(self, subaccount_user_id: str = None) -> Dict:
        """
        Set margin type to portfolio (cross margin equivalent)
        
        Args:
            subaccount_user_id: User ID (if None, will fetch automatically)
        
        Returns:
            Dict containing API response
        """
        if not subaccount_user_id:
            subaccount_user_id = self.get_user_id()
            if not subaccount_user_id:
                return {'success': False, 'error': 'Could not retrieve user ID'}
        
        path = '/v2/users/margin_mode'
        payload = {
            "margin_mode": "cross",
            "subaccount_user_id": str(subaccount_user_id)
        }
        
        try:
            response_data = self._make_authenticated_request1('PUT', path, payload=payload)
            
            if response_data.get('success'):
                print(f"Margin type set to portfolio (cross) successfully!")
            else:
                print(f"Error setting margin type: {response_data}")
            
            return response_data
            
        except Exception as e:
            print(f"Failed to set margin type: {e}")
            return {'success': False, 'error': str(e)}

    def set_margin_type_isolated(self, subaccount_user_id: str = None) -> Dict:
        """
        Set margin type to isolated
        
        Args:
            subaccount_user_id: User ID (if None, will fetch automatically)
        
        Returns:
            Dict containing API response
        """
        if not subaccount_user_id:
            subaccount_user_id = self.get_user_id()
            if not subaccount_user_id:
                return {'success': False, 'error': 'Could not retrieve user ID'}
        
        path = '/v2/users/margin_mode'
        payload = {
            "margin_mode": "isolated",
            "subaccount_user_id": str(subaccount_user_id)
        }
        
        try:
            response_data = self._make_authenticated_request1('PUT', path, payload=payload)
            
            if response_data.get('success'):
                print(f"Margin type set to isolated successfully!")
            else:
                print(f"Error setting margin type: {response_data}")
            
            return response_data
            
        except Exception as e:
            print(f"Failed to set margin type: {e}")
            return {'success': False, 'error': str(e)}

    # For backward compatibility, you can keep this method name
    def set_margin_type_cross(self, subaccount_user_id: str = None) -> Dict:
        """
        Set margin type to cross (portfolio mode)
        This is an alias for set_margin_type_portfolio
        """
        return self.set_margin_type_portfolio(subaccount_user_id)


    def get_positions(self, product_id: Optional[str] = None, underlying_asset: Optional[str] = None) -> Dict:
        
        if product_id and underlying_asset:
            raise ValueError("Cannot specify both symbol and underlying_asset. Use one or the other.")
        
        if not product_id and not underlying_asset:
            raise ValueError("Must specify either symbol or underlying_asset")
        
        if product_id:
           
            path = '/v2/positions'
            params = {'product_id': product_id}
        else:
            # Use underlying asset
            path = '/v2/positions'
            params = {'underlying_asset_symbol': underlying_asset}
        
        return self._make_authenticated_request('GET', path, params)

