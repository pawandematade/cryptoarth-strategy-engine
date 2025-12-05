from authenticate.models import SymbolMaster, User,userStratergyPortfolio,tradeDetails,OrderDetails,customer_failorder
import requests
import json
from typing import List, Dict, Any
import uuid
from django.db.models import Q
from concurrent.futures import ThreadPoolExecutor,wait
from authenticate.serializers import UserStrategyPortfolioSerializer,PositionSerializer
from .coindcx import coindcxclient
from .deltaexchange import DeltaExchangeClient
import math

def save_products_to_db(products):
    """
    Save all Delta products to symbolmaster table using bulk_create.
    """
    objects = []

    for p in products:
        precision = p.get('settling_precision') or p.get('quoting_precision') or p.get('underlying_precision')

        obj = SymbolMaster(
            symbol=p['symbol'],
            symbolid=p['product_id'],
            precision=precision,
            minimum_qty=p.get('minimum_quantity', 1),
            Type=p.get('contract_type'),
            contract_value=p.get('contract_value',0)
        )
        objects.append(obj)

    if objects:
        # Bulk insert all records
        SymbolMaster.objects.bulk_create(objects, ignore_conflicts=True)  # ignore_conflicts avoids duplicate errors
        print(f"{len(objects)} products saved to the database.")
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


from authenticate.models import adminPosition,Position,SymbolMaster
from django.core.cache import cache



class process_exit_order:
    def __init__(self,strategy_id,symbol,side,strategy_name):
        self.symbol = symbol
        self.side = side
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.symbol_d = []
        self.order_set = []
        self.failure = []
        self.symbol_coindcx = ""
        self.leverage = 0

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
        data = cache.get(cache_key)
        if not data:
            symboldata = SymbolMaster.objects.filter(symbolid = self.symbol).first()
            if symboldata:
                data = {
                    
                    "symbol": symboldata.symbol,
                    "precision": symboldata.precision,
                    "minimum_qty": symboldata.minimum_qty,
                    "Type": symboldata.Type,
                    "contract_value": float(symboldata.contract_value) if symboldata.contract_value else 1
                }
                cache.set(cache_key, data, timeout=86400)  # Cache for 1 day
                
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
                        margin_used = float(order['result'][0]['price']) * float(order['result'][0]['total_quantity']) * float(self.symbol_d['contract_value'])
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
        symbol_data = self.get_symbol_data()
        if self.side == "buy":
            side50 = "sell"
        else:
            side50 = "buy"
        if adminPosition.objects.filter(Q(strategy_id = self.strategy_id) & Q(symbol = symbol_data['symbol']) & Q(side = side50)).exists():
            
            adminposition = adminPosition.objects.get(Q(strategy_id = self.strategy_id) & Q(symbol = symbol_data['symbol']) )
            self.leverage = adminposition.leverage
            positions = Position.objects.filter(unique = adminposition.order_id)
            dataset = PositionSerializer(positions,many = True).data
         
            with ThreadPoolExecutor(max_workers=150) as executor:
                loop_logic = [executor.submit(self.process_customer_position,user,symbol_data) for user in dataset]
                wait(loop_logic)

                print(self.order_set)
                orders = [
                    OrderDetails(
                        owner_id=order['owner'],
                        orderid=order['entry_orderid'],
                        symbol=symbol_data['symbol'],       # or dynamic if available
                        side=order['side'],             # or from order if exists
                        stratergy=self.strategy_id,
                        date=order['exit_datetime'],
                        buyprice = order['entry_price'] if order['side'] == "buy" else order['exit_price'],
                        sellprice = order['entry_price'] if order['side'] == "sell" else order['exit_price'],
                        buyquantity = order['entry_quantity'] if order['side'] == "buy" else order['exit_quantity'],
                        sellquantity = order['entry_quantity'] if order['side'] == "sell" else order['exit_quantity'],
                        status = "Completed",
                        profit = ((order['exit_price'] * order['exit_quantity'] * symbol_data['contract_value']) - (order['entry_price'] * order['entry_quantity'] * symbol_data['contract_value'])) if order['side'] == "buy" else ((order['entry_price'] * order['entry_quantity'] * symbol_data['contract_value']) - (order['exit_price'] * order['exit_quantity'] * symbol_data['contract_value'])),
                        stratergy_name = self.strategy_name,
                        broker_id = order['broker_id']

                    )
                    for order in self.order_set
                ]
                OrderDetails.objects.bulk_create(orders, batch_size=100, ignore_conflicts=True)
                trades = [
                    tradeDetails(
                        owner_id=order['owner'],
                        symbol=symbol_data['symbol'],
                        price=order['exit_price'],
                        quantity=order['exit_quantity'],
                        side=self.side,
                        unique=order['exit_orderid'],
                        date=order['exit_datetime'],
                        status=order['exit_status'],
                        orderid=order['entry_orderid'],
                        stratergy=self.strategy_id,
                        remark="Order Placed Successfully.",
                        stratergy_name = self.strategy_name,
                        margin=order['margin'],
                        broker_id = order['broker_id']
                    )
                    for order in self.order_set
                    
                ]
                tradeDetails.objects.bulk_create(trades, batch_size=100, ignore_conflicts=True)
                ids = [ order['entry_orderid'] for order in self.order_set ]
                Position.objects.filter(order_id__in=ids).delete()
                adminPosition.objects.filter(Q(strategy_id = self.strategy_id) & Q(symbol = symbol_data['symbol'])).delete()
                fail = [
                    customer_failorder(
                        owner_id=order['owner'],
                        orderid = order['orderid'],
                        strategy = self.strategy_name,
                        remarks = order['remarks']
                    )
                    for order in self.failure
                ]
                customer_failorder.objects.bulk_create(fail, batch_size=100, ignore_conflicts=True)
        else:
            pass


class process_entry_order:
    def __init__(self,symbol,side,leverage,capital,strategy_id,strategy_name):
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

    def convert_symbol(self,symbol):
        # Remove 'USD' and add 'B-' prefix and '_USDT' suffix
        base_currency = symbol.replace('USD', '')
        return f"B-{base_currency}_USDT"

    def get_symbol_data(self):
        cache_key = f"symbol_data_{self.symbol}"
        data = cache.get(cache_key)
        if not data:
            symboldata = SymbolMaster.objects.filter(symbolid = self.symbol).first()
            if symboldata:
                data = {
                    
                    "symbol": symboldata.symbol,
                    "precision": symboldata.precision,
                    "minimum_qty": symboldata.minimum_qty,
                    "Type": symboldata.Type,
                    "contract_value": float(symboldata.contract_value) if symboldata.contract_value else 1
                }
                
                cache.set(cache_key, data, timeout=86400)  # Cache for 1 day
                
            else:
                print(f"Symbol with ID {self.symbol} not found in database.")
                return None
        self.symbol_coindcx = self.convert_symbol(data['symbol'])
        self.symbol_d = data
        return data
    
    def create_admin_position(self):
        data = self.get_symbol_data()
        if data:
            adminposition = adminPosition.objects.create(
                order_id=uuid.uuid4().hex,
                symbol=data['symbol'],
                side=self.side,
                leverage=self.leverage,
                capital=self.capital,
                strategy_id=self.strategy_id   # ✅ use _id since you have the PK
            )
            return adminposition
        else:
            print("Failed to create admin position due to missing symbol data.")
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
    
    def caclulate_quantity1(self,fund):
        data = self.symbol_d
        margin = fund * int(self.leverage) * float(self.capital)
        
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
        # print(user['broker']['broker'])
        if user['broker']['broker'] == "Coindcx":
            if apikey and apisecret and user['is_active']:
                client = coindcxclient(api_key=apikey,api_secret=apisecret)
                balance_data = client.get_wallet_info()
   
                quantity = self.caclulate_quantity1(balance_data)
      
                if quantity:
                    order = client.place_order_coindcx(side = self.side,symbol = self.symbol_coindcx,qty=quantity,leverage=self.leverage)
                    print(order)
                    if order['success'] == True:
                        margin_used = float(order['result'][0]['price']) * float(order['result'][0]['total_quantity']) * float(self.symbol_d['contract_value'])
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
        position = self.create_admin_position()
        if position:
            symbol_data = self.get_symbol_data()
            if symbol_data:
                userdata = userStratergyPortfolio.objects.filter(Q(stratergy_id = self.strategy_id) & Q(is_active=True))
                dataset = UserStrategyPortfolioSerializer(userdata,many=True).data
                with ThreadPoolExecutor(max_workers=150) as executor:
                    loop_logic = [executor.submit(self.process_customer_position,user,symbol_data) for user in dataset]
                    wait(loop_logic)
                    

                    positions = [
                        Position(
                            owner_id=order['owner'],
                            order_id=order['orderid'],
                            symbol=symbol_data['symbol'],       # or dynamic if available
                            side=self.side,             # or from order if exists
                            price=order['price'],
                            quantity=order['quantity'],
                            unique=position.order_id,
                            leverage=self.leverage,
                            stratergy=self.strategy_id,
                            date=order['datetime'],
                            stratergy_name = self.strategy_name,
                            broker_id = order['broker_id']
                        )
                        for order in self.order_set
                    ]
                    Position.objects.bulk_create(positions, batch_size=100, ignore_conflicts=True)
                    trades = [
                        tradeDetails(
                            owner_id=order['owner'],
                            symbol=symbol_data['symbol'],
                            price=order['price'],
                            quantity=order['quantity'],
                            side=self.side,
                            unique=position.order_id,
                            date=order['datetime'],
                            status=order['status'],
                            orderid=order['orderid'],
                            stratergy=self.strategy_id,
                            remark="Order Placed Successfully.",
                            stratergy_name = self.strategy_name,
                            margin=order['margin'],
                            broker_id = order['broker_id']
                        )
                        for order in self.order_set
                        
                    ]
                    tradeDetails.objects.bulk_create(trades, batch_size=100, ignore_conflicts=True)
                    fail = [
                        customer_failorder(
                            owner_id=order['owner'],
                            orderid = order['orderid'],
                            strategy = self.strategy_name,
                            remarks = order['remarks']
                        )
                        for order in self.failure
                    ]
                    customer_failorder.objects.bulk_create(fail, batch_size=100, ignore_conflicts=True)


from django.utils import timezone
from datetime import datetime, time
import pytz

def get_todays_dates():
    kolkata_tz = pytz.timezone('Asia/Kolkata')
    now_kolkata = timezone.now().astimezone(kolkata_tz)

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
    return start_of_day_utc,end_of_day_utc


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



def get_live_price(symbol):
    price = cache.get(f'DELTA-{symbol}')
    if not price:
        data = requests.get(f"https://api.india.delta.exchange/v2/tickers/{symbol}").json()
        price = float(data['result']['mark_price'])
    return price



    

