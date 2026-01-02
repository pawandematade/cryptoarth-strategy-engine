"""
Order Functions - Refactored for SQLAlchemy
Converted from Django ORM to SQLAlchemy
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Dict, Any, Optional
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
import requests
import json
import math
import time as t
from datetime import datetime, time
import pytz

# SQLAlchemy models
from app.models_legacy_trading import (
    SymbolMaster, Position, OrderDetails, tradeDetails,
    userStratergyPortfolio, highLowstratergy, BrokerModels,
    adminPosition, customer_failorder, latencycheck
)
from app.models import User

# Broker clients
from order.brokers.coindcx.client import coindcxclient
from order.brokers.delta.client import DeltaExchangeClient

# Redis cache
from common.redis import redis_client

def save_products_to_db(products: List[Dict], db: Session):
    """
    Save all Delta products to symbolmaster table using bulk operations.
    Refactored from Django ORM to SQLAlchemy.
    """
    objects = []

    for p in products:
        precision = p.get('settling_precision') or p.get('quoting_precision') or p.get('underlying_precision')

        objects.append({
            'symbol': p['symbol'],
            'symbolid': p['product_id'],
            'precision': precision,
            'minimum_qty': p.get('minimum_quantity', 1),
            'Type': p.get('contract_type'),
            'contract_value': p.get('contract_value', 0)
        })

    if objects:
        try:
            # Bulk insert (SQLAlchemy equivalent of bulk_create with ignore_conflicts)
            # Note: ignore_conflicts equivalent is handled by database constraints or try/except
            db.bulk_insert_mappings(SymbolMaster, objects)
            db.commit()
            print(f"{len(objects)} products saved to the database.")
        except Exception as e:
            db.rollback()
            print(f"Error saving products: {e}")
    else:
        print("No products to save.")




def get_all_delta_products() -> List[Dict[str, Any]]:
    """
    Fetch all products from Delta Exchange with their specifications.
    
    Returns:
        List of dictionaries containing product information
    """
    base_url = 'https://api.india.delta.exchange'
    endpoint = '/v2/products'
    
    all_products = []
    after_cursor = None
    
    try:
        while True:
            # Prepare parameters for pagination
            params = {
                'page_size': '10000'  # Maximum page size
            }
            
            if after_cursor:
                params['after'] = after_cursor
            
            # Make the API request
            response = requests.get(
                f'{base_url}{endpoint}',
                params=params,
                headers={
                    'Accept': 'application/json',
                    'User-Agent': 'python-rest-client'
                },
                timeout=(3, 27)
            )
            
            # Check if request was successful
            response.raise_for_status()
            
            data = response.json()
            
            if not data.get('success', False):
                print(f"API returned error: {data}")
                break
            
            products = data.get('result', [])
            
            if not products:
                break
            
            # Process each product
            for product in products:
                product_info = {
                    'product_id': product.get('id'),
                    'symbol': product.get('symbol'),
                    'name': product.get('description', ''),
                    'contract_type': product.get('contract_type'),
                    'state': product.get('state'),
                    'trading_status': product.get('trading_status'),
                    'tick_size': product.get('tick_size'),
                    'contract_value': product.get('contract_value'),
                    'contract_unit_currency': product.get('contract_unit_currency'),
                    'minimum_quantity': 1,  # Delta Exchange uses lot sizes, minimum is 1 lot
                    'position_size_limit': product.get('position_size_limit'),
                    'underlying_asset': None,
                    'quoting_asset': None,
                    'settling_asset': None,
                    'underlying_precision': None,
                    'quoting_precision': None,
                    'settling_precision': None
                }
                
                # Extract asset information and their precisions
                if 'underlying_asset' in product and product['underlying_asset']:
                    underlying = product['underlying_asset']
                    product_info['underlying_asset'] = underlying.get('symbol')
                    product_info['underlying_precision'] = underlying.get('precision')
                
                if 'quoting_asset' in product and product['quoting_asset']:
                    quoting = product['quoting_asset']
                    product_info['quoting_asset'] = quoting.get('symbol')
                    product_info['quoting_precision'] = quoting.get('precision')
                
                if 'settling_asset' in product and product['settling_asset']:
                    settling = product['settling_asset']
                    product_info['settling_asset'] = settling.get('symbol')
                    product_info['settling_precision'] = settling.get('precision')
                
                all_products.append(product_info)
            
            # Check if there are more pages
            # Note: The API documentation doesn't specify pagination response format
            # This assumes standard cursor-based pagination
            if len(products) < 100:  # If we got less than page_size, we're done
                break
            
            # For cursor-based pagination, you'd typically get the cursor from response
            # Since the exact format isn't specified, we'll break here
            # In practice, you might need to adjust this based on actual API response
            break
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching products: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []
    
    return all_products


# Models already imported above



class process_exit_order:
    """
    Process exit orders - refactored for SQLAlchemy
    """
    def __init__(self, strategy_id: int, symbol: int, side: str, strategy_name: str, db: Session):
        self.symbol = symbol
        self.side = side
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.symbol_d = []
        self.order_set = []
        self.failure = []
        self.symbol_coindcx = ""
        self.leverage = 0
        self.db = db

    def convert_symbol(self,symbol):
        # Remove 'USD' and add 'B-' prefix and '_USDT' suffix
        base_currency = symbol.replace('USD', '')
        return f"B-{base_currency}_USDT"
    
    def convert_ms_to_kolkata_datetime(self,timestamp_ms: int):
        """
        Converts a Unix timestamp in milliseconds to a datetime object
        in Kolkata timezone (Asia/Kolkata).
        """
        try:
            kolkata_tz = pytz.timezone('Asia/Kolkata')
            return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=kolkata_tz)
        except (ValueError, TypeError):
            return None

    def decrypt_api(self,user):
        from cryptography.fernet import Fernet, InvalidToken
        from decouple import config

        FERNET_KEY = config('FERNET_KEY', default=None)
        f = Fernet(FERNET_KEY)
        try:
            key = f.decrypt(user['broker']['api_key'].encode()).decode() 
            secret = f.decrypt(user['broker']['api_secret'].encode()).decode() 
            return key, secret
        except (InvalidToken, AttributeError):
            return None, None

    def get_symbol_data(self):
        cache_key = f"symbol_data_{self.symbol}"
        data = None
        
        if redis_client:
            cached = redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
        
        if not data:
            symboldata = self.db.query(SymbolMaster).filter(SymbolMaster.symbolid == self.symbol).first()
            if symboldata:
                data = {
                    "symbol": symboldata.symbol,
                    "precision": symboldata.precision,
                    "minimum_qty": symboldata.minimum_qty,
                    "Type": symboldata.Type,
                    "contract_value": float(symboldata.contract_value) if symboldata.contract_value else 1
                }
                if redis_client:
                    redis_client.set(cache_key, json.dumps(data), ex=86400)  # Cache for 1 day
            else:
                print(f"Symbol with ID {self.symbol} not found in database.")
                return None
        
        self.symbol_d = data
        self.symbol_coindcx = self.convert_symbol(data['symbol'])
        return data
    

    def get_open_position(self,positions, symbol):
        """
        Returns the open quantity for a given trading symbol.
        If no active position, returns 0.
        """
        if not positions:  # handles [] or None
            return 0
        
        for pos in positions:
            if pos.get('pair') == symbol:
                return pos.get('active_pos', 0)  # return active position size
        
        return 0


    def process_customer_position(self,user,symbol_data):
        apikey,apisecret = self.decrypt_api(user)
        if user['broker']['broker'] == "Coindcx":
            client = coindcxclient(api_key=apikey, api_secret=apisecret)
            try:
                
                position = client.get_positions_coindcx(symbol=self.symbol_coindcx)
                quantity_balance = self.get_open_position(position, self.symbol_coindcx)
                user_qty = float(user['quantity'])
                if (user['side'] == "buy" and quantity_balance > 0) or (user['side'] == "sell" and quantity_balance < 0):
        
                    qty = min(user_qty, abs(quantity_balance))
                    order = client.place_order_coindcx(side = self.side,symbol = self.symbol_coindcx,qty=qty,leverage=self.leverage)
                    
                    if order['success'] == True:
                        margin_used = float(order['result'][0]['price']) * float(order['result'][0]['total_quantity']) 
                        self.order_set.append({'owner':user['owner']['id'],'broker_id':user['broker']['id'],'margin':margin_used,'exit_price':float(order['result'][0]['price']),'exit_orderid':order['result'][0]['id'],'exit_status':'completed','exit_quantity':order['result'][0]['total_quantity'],'exit_datetime':self.convert_ms_to_kolkata_datetime(int(order['result'][0]['created_at'])),'entry_price':float(user['price']),'entry_quantity':user_qty,'entry_orderid':user['order_id'],'side':user['side']})
                    else:
                        remarks = order['error'].args[0]['message']
                        self.failure.append({'owner':user['owner']['id'],'orderid':user['order_id'],'remarks':remarks})
                else:
                    remarks = f'Quantity is not available to close order. Quantity size - {str(quantity_balance)}'
                    self.failure.append({'owner':user['owner']['id'],'orderid':user['order_id'],'remarks':remarks})
            except:
                remarks = "Not able to fetch position."
                self.failure.append({'owner':user['owner']['id'],'orderid':user['order_id'],'remarks':remarks})

        else:
            client = DeltaExchangeClient(api_key=apikey,api_secret=apisecret)
            position = client.get_positions(product_id=self.symbol)
            
            if position['success'] == True:
            
                quantity_balance = int(position['result']['size'])
        
                user_qty = int(float(user['quantity']))
            
                if (user['side'] == "buy" and quantity_balance > 0) or (user['side'] == "sell" and quantity_balance < 0):
        
                    qty = min(user_qty, abs(quantity_balance))
                
                    order = client.place_order(product_symbol = symbol_data['symbol'],side = self.side,size=qty)
                    if order['success'] == True:  
                        margin_used = float(order['result']['average_fill_price']) * float(order['result']['size']) * float(self.symbol_d['contract_value'])     
                        self.order_set.append({'owner':user['owner']['id'],'broker_id':user['broker']['id'],'margin':margin_used,'exit_price':float(order['result']['average_fill_price']),'exit_orderid':order['result']['id'],'exit_status':order['result']['state'],'exit_quantity':order['result']['size'],'exit_datetime':order['result']['created_at'],'entry_price':float(user['price']),'entry_quantity':user_qty,'entry_orderid':user['order_id'],'side':user['side']})
                    else:
                        remarks = order['error']['code']
                        self.failure.append({'owner':user['owner']['id'],'orderid':user['order_id'],'remarks':remarks})
                else:
                    remarks = f'Quantity is not available to close order. Quantity size - {str(quantity_balance)}'
                    self.failure.append({'owner':user['owner']['id'],'orderid':user['order_id'],'remarks':remarks})
            else:
                remarks = f"Not able to fetch position. Error - {str(position['error']['code'])}"
                self.failure.append({'owner':user['owner']['id'],'orderid':user['order_id'],'remarks':remarks})




    def process(self):
        """
        Main process method - refactored for SQLAlchemy
        """
        symbol_data = self.get_symbol_data()
        if not symbol_data:
            return
        
        if self.side == "buy":
            side50 = "sell"
        else:
            side50 = "buy"
        
        # Check if admin position exists
        adminposition = self.db.query(adminPosition).filter(
            and_(
                adminPosition.strategy_id == self.strategy_id,
                adminPosition.symbol == symbol_data['symbol'],
                adminPosition.side == side50
            )
        ).first()
        
        if adminposition:
            self.leverage = adminposition.leverage
            positions = self.db.query(Position).filter(Position.unique == adminposition.order_id).all()
            
            # Convert positions to dict format (matching original serializer behavior)
            dataset = []
            for pos in positions:
                user_dict = {
                    'owner': {'id': pos.owner_id},
                    'broker': {
                        'id': pos.broker_id,
                        'broker': pos.broker.broker if pos.broker else 'DeltaExchange',
                        'api_key': pos.broker.api_key if pos.broker else None,
                        'api_secret': pos.broker.api_secret if pos.broker else None
                    },
                    'quantity': float(pos.quantity),
                    'price': float(pos.price),
                    'order_id': pos.order_id,
                    'side': pos.side
                }
                dataset.append(user_dict)
            
            kolkata_tz = pytz.timezone('Asia/Kolkata')
            start_timestamp = t.time()
            start_dt = datetime.now(kolkata_tz)
         
            with ThreadPoolExecutor(max_workers=50) as executor:
                loop_logic = [executor.submit(self.process_customer_position,user,symbol_data) for user in dataset]
                wait(loop_logic)

            end_timestamp = t.time()
            end_dt = datetime.now(kolkata_tz)
            duration_ms = int((end_timestamp - start_timestamp) * 1000)
            
            # Create latency check record
            try:
                latency = latencycheck(
                    symbol=symbol_data.get('symbol', 'NA'),
                    strategy_id=self.strategy_id,
                    time_start=start_dt,
                    time_end=end_dt,
                    time_taken=duration_ms,
                    side=self.side,
                    type="Exit",
                    user_count=len(self.order_set)
                )
                self.db.add(latency)
            except:
                pass
            
            # Create OrderDetails records
            orders_to_create = []
            for order in self.order_set:
                orders_to_create.append({
                    'owner_id': order['owner'],
                    'orderid': order['entry_orderid'],
                    'symbol': symbol_data['symbol'],
                    'side': order['side'],
                    'stratergy': str(self.strategy_id),
                    'date': order['exit_datetime'],
                    'buyprice': order['entry_price'] if order['side'] == "buy" else order['exit_price'],
                    'sellprice': order['entry_price'] if order['side'] == "sell" else order['exit_price'],
                    'buyquantity': order['entry_quantity'] if order['side'] == "buy" else order['exit_quantity'],
                    'sellquantity': order['entry_quantity'] if order['side'] == "sell" else order['exit_quantity'],
                    'status': "Completed",
                    'profit': ((order['exit_price'] * order['exit_quantity'] * symbol_data['contract_value']) - (order['entry_price'] * order['entry_quantity'] * symbol_data['contract_value'])) if order['side'] == "buy" else ((order['entry_price'] * order['entry_quantity'] * symbol_data['contract_value']) - (order['exit_price'] * order['exit_quantity'] * symbol_data['contract_value'])),
                    'stratergy_name': self.strategy_name,
                    'broker_id': order['broker_id']
                })
            
            if orders_to_create:
                self.db.bulk_insert_mappings(OrderDetails, orders_to_create)
            
            # Create tradeDetails records
            trades_to_create = []
            for order in self.order_set:
                trades_to_create.append({
                    'owner_id': order['owner'],
                    'symbol': symbol_data['symbol'],
                    'price': order['exit_price'],
                    'quantity': order['exit_quantity'],
                    'side': self.side,
                    'unique': order['exit_orderid'],
                    'date': order['exit_datetime'],
                    'status': order['exit_status'],
                    'orderid': order['entry_orderid'],
                    'stratergy': str(self.strategy_id),
                    'remark': "Order Placed Successfully.",
                    'stratergy_name': self.strategy_name,
                    'margin': order['margin'],
                    'broker_id': order['broker_id']
                })
            
            if trades_to_create:
                self.db.bulk_insert_mappings(tradeDetails, trades_to_create)
            
            # Delete positions
            order_ids = [order['entry_orderid'] for order in self.order_set]
            self.db.query(Position).filter(Position.order_id.in_(order_ids)).delete(synchronize_session=False)
            
            # Delete admin position
            self.db.query(adminPosition).filter(
                and_(
                    adminPosition.strategy_id == self.strategy_id,
                    adminPosition.symbol == symbol_data['symbol']
                )
            ).delete(synchronize_session=False)
            
            # Create failure records
            if self.failure:
                fails_to_create = []
                for fail in self.failure:
                    fails_to_create.append({
                        'owner_id': fail['owner'],
                        'orderid': fail['orderid'],
                        'strategy': self.strategy_name,
                        'remarks': fail['remarks']
                    })
                self.db.bulk_insert_mappings(customer_failorder, fails_to_create)
            
            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                print(f"Error in process_exit_order: {e}")


class process_entry_order:
    """
    Process entry orders - refactored for SQLAlchemy
    """
    def __init__(self, symbol: int, side: str, leverage: int, capital: float, strategy_id: int, strategy_name: str, db: Session):
        self.symbol = symbol
        self.side = side
        self.leverage = leverage
        self.capital = capital
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.symbol_coindcx = ""
        self.order_set = []
        self.symbol_d = []
        self.failure = []
        self.db = db

    def convert_symbol(self,symbol):
        # Remove 'USD' and add 'B-' prefix and '_USDT' suffix
        base_currency = symbol.replace('USD', '')
        return f"B-{base_currency}_USDT"

    def get_symbol_data(self):
        cache_key = f"symbol_data_{self.symbol}"
        data = None
        
        if redis_client:
            cached = redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
        
        if not data:
            symboldata = self.db.query(SymbolMaster).filter(SymbolMaster.symbolid == self.symbol).first()
            if symboldata:
                data = {
                    "symbol": symboldata.symbol,
                    "precision": symboldata.precision,
                    "minimum_qty": symboldata.minimum_qty,
                    "Type": symboldata.Type,
                    "contract_value": float(symboldata.contract_value) if symboldata.contract_value else 1
                }
                if redis_client:
                    redis_client.set(cache_key, json.dumps(data), ex=86400)
            else:
                print(f"Symbol with ID {self.symbol} not found in database.")
                return None
        
        self.symbol_coindcx = self.convert_symbol(data['symbol'])
        self.symbol_d = data
        return data
    
    def create_admin_position(self):
        data = self.get_symbol_data()
        if data:
            adminposition = adminPosition(
                order_id=uuid.uuid4().hex,
                symbol=data['symbol'],
                side=self.side,
                leverage=self.leverage,
                capital=self.capital,
                strategy_id=self.strategy_id
            )
            self.db.add(adminposition)
            self.db.commit()
            self.db.refresh(adminposition)
            return adminposition
        else:
            print("Failed to create admin position due to missing symbol data.")
            return None
        
    def decrypt_api(self,user):
        try:
            from cryptography.fernet import Fernet, InvalidToken
            from decouple import config

            FERNET_KEY = config('FERNET_KEY', default=None)
            f = Fernet(FERNET_KEY)
            try:
                key = f.decrypt(user['broker']['api_key'].encode()).decode() 
                secret = f.decrypt(user['broker']['api_secret'].encode()).decode() 
                return key, secret
            except (InvalidToken, AttributeError):
                return None, None
        except Exception as e:
            print(str(e))
            return None, None
        
    def adjust_quantity(self,quantity, contract_value):
        # Determine decimal places from contract value
        contract_str = str(contract_value)
        if '.' in contract_str:
            decimal_places = len(contract_str.split('.')[1])
        else:
            decimal_places = 0
        
        # Adjust quantity to match contract precision
        adjusted = math.floor(quantity * (10 ** decimal_places)) / (10 ** decimal_places)
        return adjusted
    
    def caclulate_quantity1(self,fund,conversion_rate):
        data = self.symbol_d
        margin = (fund/float(conversion_rate)) * int(self.leverage) * float(self.capital)
        liveprice = float(get_live_price(self.symbol_d['symbol']))
        qty = margin / liveprice
        qty = self.adjust_quantity(qty, float(data['contract_value']))
      
        if qty >= float(data['contract_value']):
            return qty
        else:
            return None
        
    def caclulate_quantity(self,fund):
        data = self.symbol_d
        margin = fund * int(self.leverage) * float(self.capital)
        
        liveprice = float(get_live_price(self.symbol_d['symbol']))
        qty = int((margin / liveprice)/float(data['contract_value']))
        if qty >= 1:
            return qty
        else:
            return None
        
    def convert_ms_to_kolkata_datetime(self,timestamp_ms: int):
        """
        Converts a Unix timestamp in milliseconds to a datetime object
        in Kolkata timezone (Asia/Kolkata).
        """
        try:
            kolkata_tz = pytz.timezone('Asia/Kolkata')
            return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=kolkata_tz)
        except (ValueError, TypeError):
            return None
        
    
    
    def process_customer_position(self,user,symbol_data):

        apikey,apisecret = self.decrypt_api(user)
        print(user['broker']['broker'])
        if user['broker']['broker'] == "Coindcx":
            if apikey and apisecret and user['is_active']:
                client = coindcxclient(api_key=apikey,api_secret=apisecret)
                balance_data = client.get_wallet_info()
                conversion_rate=client.get_usdt_conversion()[0]['conversion_price']
                
                quantity = self.caclulate_quantity1(balance_data,conversion_rate)
      
                if quantity:
                    order = client.place_order_coindcx(side = self.side,symbol = self.symbol_coindcx,qty=quantity,leverage=self.leverage)
            
                    if order['success'] == True:
                        margin_used = float(order['result'][0]['price']) * float(order['result'][0]['total_quantity']) 
                        self.order_set.append({'owner':user['owner']['id'],'broker_id':user['broker']['id'],'margin':margin_used,'price':float(order['result'][0]['price']),'orderid':order['result'][0]['id'],'status':'completed','quantity':order['result'][0]['total_quantity'],'datetime':self.convert_ms_to_kolkata_datetime(int(order['result'][0]['created_at']))})
                    else:
                        remarks = order['error'].args[0]['message']
                        self.failure.append({'owner':user['owner']['id'],'orderid':"NA",'remarks':remarks})
                else:
                    try:
                        remarks = f"You dont have sufficient funds to process {self.symbol_d['symbol']} order"
                    except:
                        remarks = f"You dont have sufficient funds to process order"
                    self.failure.append({'owner':user['owner']['id'],'orderid':"NA",'remarks':remarks})
            else:
                remarks = "apikey is not correctly binded"
                self.failure.append({'owner':user['owner']['id'],'orderid':"NA",'remarks':remarks})
        else:
            if apikey and apisecret and user['is_active']:
                client = DeltaExchangeClient(api_key=apikey,api_secret=apisecret)
                balance_data = client.get_balances()
             
                fund = float(balance_data['result'][0]['available_balance'])
                quantity = self.caclulate_quantity(fund)
                if quantity:
                    try:
                        leverage_status = client.set_leverage1(product_id=self.symbol,leverage=self.leverage)
                        
                        if leverage_status['success'] == True:
                            
                            order = client.place_order(product_symbol = symbol_data['symbol'],side = self.side,size=quantity)
                            
                            if order['success'] == True:
                                margin_used = float(order['result']['average_fill_price']) * float(order['result']['size']) * float(self.symbol_d['contract_value']) 
                                self.order_set.append({'owner':user['owner']['id'],'broker_id':user['broker']['id'],'margin':margin_used,'price':float(order['result']['average_fill_price']),'orderid':order['result']['id'],'status':order['result']['state'],'quantity':order['result']['size'],'datetime':order['result']['created_at']})
                        
                            else:
                                remarks = order['error']['code']
                                self.failure.append({'owner':user['owner']['id'],'orderid':"NA",'remarks':remarks})
                        else:
                            remarks = leverage_status['error']['code']
                            self.failure.append({'owner':user['owner']['id'],'orderid':"NA",'remarks':remarks})
                    except Exception as e:
                        remarks = str(e)
                        self.failure.append({'owner':user['owner']['id'],'orderid':"NA",'remarks':remarks})
                else:
                    try:
                        remarks = f"You dont have sufficient funds to process {self.symbol_d['symbol']} order"
                    except:
                        remarks = f"You dont have sufficient funds to process order"
                    self.failure.append({'owner':user['owner']['id'],'orderid':"NA",'remarks':remarks})
            else:
                remarks = "apikey is not correctly binded"
                self.failure.append({'owner':user['owner']['id'],'orderid':"NA",'remarks':remarks})
                

    


    def process(self):
        try:
            position = self.create_admin_position()
            if position:
                symbol_data = self.get_symbol_data()
                if symbol_data:
                    # Query user strategy portfolios
                    userdata = self.db.query(userStratergyPortfolio).join(BrokerModels).filter(
                        and_(
                            userStratergyPortfolio.stratergy_id == self.strategy_id,
                            userStratergyPortfolio.is_active == True,
                            BrokerModels.status == True
                        )
                    ).all()
                    
                    # Convert to dict format (matching original serializer)
                    dataset = []
                    for usp in userdata:
                        user_dict = {
                            'owner': {'id': usp.owner_id},
                            'broker': {
                                'id': usp.broker_id,
                                'broker': usp.broker.broker if usp.broker else 'DeltaExchange',
                                'api_key': usp.broker.api_key if usp.broker else None,
                                'api_secret': usp.broker.api_secret if usp.broker else None
                            },
                            'is_active': usp.is_active
                        }
                        dataset.append(user_dict)
                    
                    kolkata_tz = pytz.timezone('Asia/Kolkata')
                    start_timestamp = t.time()
                    start_dt = datetime.now(kolkata_tz)
                    
                    with ThreadPoolExecutor(max_workers=150) as executor:
                        loop_logic = [executor.submit(self.process_customer_position, user, symbol_data) for user in dataset]
                        wait(loop_logic)
                    
                    end_timestamp = t.time()
                    end_dt = datetime.now(kolkata_tz)
                    duration_ms = int((end_timestamp - start_timestamp) * 1000)
                    
                    # Create latency check record
                    try:
                        latency = latencycheck(
                            symbol=symbol_data.get('symbol', 'NA'),
                            strategy_id=self.strategy_id,
                            time_start=start_dt,
                            time_end=end_dt,
                            time_taken=duration_ms,
                            side=self.side,
                            type="Entry",
                            user_count=len(self.order_set)
                        )
                        self.db.add(latency)
                    except:
                        pass
                    
                    # Create Position records
                    positions_to_create = []
                    for order in self.order_set:
                        positions_to_create.append({
                            'owner_id': order['owner'],
                            'order_id': order['orderid'],
                            'symbol': symbol_data['symbol'],
                            'side': self.side,
                            'price': order['price'],
                            'quantity': order['quantity'],
                            'unique': position.order_id,
                            'leverage': self.leverage,
                            'stratergy': str(self.strategy_id),
                            'date': order['datetime'],
                            'stratergy_name': self.strategy_name,
                            'broker_id': order['broker_id']
                        })
                    
                    if positions_to_create:
                        self.db.bulk_insert_mappings(Position, positions_to_create)
                    
                    # Create tradeDetails records
                    trades_to_create = []
                    for order in self.order_set:
                        trades_to_create.append({
                            'owner_id': order['owner'],
                            'symbol': symbol_data['symbol'],
                            'price': order['price'],
                            'quantity': order['quantity'],
                            'side': self.side,
                            'unique': position.order_id,
                            'date': order['datetime'],
                            'status': order['status'],
                            'orderid': order['orderid'],
                            'stratergy': str(self.strategy_id),
                            'remark': "Order Placed Successfully.",
                            'stratergy_name': self.strategy_name,
                            'margin': order['margin'],
                            'broker_id': order['broker_id']
                        })
                    
                    if trades_to_create:
                        self.db.bulk_insert_mappings(tradeDetails, trades_to_create)
                    
                    # Create failure records
                    if self.failure:
                        fails_to_create = []
                        for fail in self.failure:
                            fails_to_create.append({
                                'owner_id': fail['owner'],
                                'orderid': fail['orderid'],
                                'strategy': self.strategy_name,
                                'remarks': fail['remarks']
                            })
                        self.db.bulk_insert_mappings(customer_failorder, fails_to_create)
                    
                    try:
                        self.db.commit()
                    except Exception as e:
                        self.db.rollback()
                        print(f"Error in process_entry_order commit: {e}")
        except Exception as e:
            self.db.rollback()
            print(f"Error in process_entry_order: {e}")


def get_todays_dates():
    """
    Get start and end of today in UTC (for database queries).
    Refactored from Django timezone to standard datetime.
    """
    kolkata_tz = pytz.timezone('Asia/Kolkata')
    now_kolkata = datetime.now(kolkata_tz)

    # Get start and end of today in Kolkata timezone
    start_of_day_kolkata = kolkata_tz.localize(
        datetime.combine(now_kolkata.date(), time.min)
    )
    end_of_day_kolkata = kolkata_tz.localize(
        datetime.combine(now_kolkata.date(), time.max)
    )

    # Convert to UTC for database query
    start_of_day_utc = start_of_day_kolkata.astimezone(pytz.UTC)
    end_of_day_utc = end_of_day_kolkata.astimezone(pytz.UTC)
    return start_of_day_utc, end_of_day_utc


def convert_date_range_to_utc(start_date_str, end_date_str):
    """
    Convert a given start and end date (YYYY-MM-DD) from Asia/Kolkata timezone to UTC.
    
    Args:
        start_date_str (str): Start date in 'YYYY-MM-DD' format.
        end_date_str (str): End date in 'YYYY-MM-DD' format.
    
    Returns:
        tuple: (start_of_day_utc, end_of_day_utc)
    """
    kolkata_tz = pytz.timezone('Asia/Kolkata')

    # Parse input strings to date objects
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    # Localize start and end times in Kolkata timezone
    start_of_day_kolkata = kolkata_tz.localize(datetime.combine(start_date, time.min))
    end_of_day_kolkata = kolkata_tz.localize(datetime.combine(end_date, time.max))

    # Convert both to UTC
    start_of_day_utc = start_of_day_kolkata.astimezone(pytz.UTC)
    end_of_day_utc = end_of_day_kolkata.astimezone(pytz.UTC)

    return start_of_day_utc, end_of_day_utc



def get_live_price(symbol: str) -> float:
    """
    Get live price for symbol from cache or API.
    Refactored from Django cache to Redis.
    """
    cache_key = f'DELTA-{symbol}'
    if redis_client:
        cached_price = redis_client.get(cache_key)
        if cached_price:
            return float(cached_price)
    
    try:
        data = requests.get(f"https://api.india.delta.exchange/v2/tickers/{symbol}").json()
        price = float(data['result']['mark_price'])
        if redis_client:
            redis_client.set(cache_key, str(price), ex=60)  # Cache for 60 seconds
        return price
    except Exception as e:
        print(f"Error getting live price: {e}")
        return 0.0

