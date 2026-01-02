"""
Position Sync - Refactored for SQLAlchemy
Converted from Django ORM to SQLAlchemy
"""
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor, wait
from order.brokers.coindcx.client import coindcxclient
from order.brokers.delta.client import DeltaExchangeClient
from order.orders.functions import get_live_price

# SQLAlchemy models
from app.models_legacy_trading import Position, OrderDetails, tradeDetails, BrokerModels

def check_all_position(db: Session):
    """
    Check all positions - refactored for SQLAlchemy
    Note: Celery decorator removed (can be added back if needed for task scheduling)
    """
    userdata = db.query(Position).all()
    futures = []
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all tasks
        futures = [executor.submit(process_position, user, db) for user in userdata]
        
        # Wait for ALL tasks to complete
        wait(futures)

def get_open_position1(positions, symbol):
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

def convert_symbol(symbol):
    # Remove 'USD' and add 'B-' prefix and '_USDT' suffix
    base_currency = symbol.replace('_USDT', 'USD')
    base_currency1 = base_currency.replace('B-', '')
    return base_currency1

def decrypt_api_credentials(broker: BrokerModels):
    """Decrypt API credentials from BrokerModels"""
    from cryptography.fernet import Fernet, InvalidToken
    from decouple import config
    
    FERNET_KEY = config('FERNET_KEY', default=None)
    if not FERNET_KEY:
        return None, None
    
    f = Fernet(FERNET_KEY)
    try:
        key = f.decrypt(broker.api_key.encode()).decode() if broker.api_key else None
        secret = f.decrypt(broker.api_secret.encode()).decode() if broker.api_secret else None
        return key, secret
    except (InvalidToken, AttributeError):
        return None, None


def process_position(user: Position, db: Session):
    """
    Process position - refactored for SQLAlchemy
    """
    # Get broker and decrypt credentials
    broker = db.query(BrokerModels).filter(BrokerModels.id == user.broker_id).first()
    if not broker:
        return
    
    apikey, apisecret = decrypt_api_credentials(broker)
    
    if user.side == "buy":
        side12 = "sell"
    else:
        side12 = "buy"
    
    if broker.broker == "Coindcx":
        client = coindcxclient(api_key=apikey, api_secret=apisecret)
        position = client.get_positions_coindcx(symbol=user.symbol)
        quantity_balance = get_open_position1(position, user.symbol)
        user_qty = float(user.quantity)
        
        if user.side == "buy" and quantity_balance > 0:
            pass
        else:
            symbol = convert_symbol(user.symbol)
            price = get_live_price(symbol)
            margin_used = float(price) * float(user_qty)
            
            order_detail = OrderDetails(
                owner_id=user.owner_id,
                orderid=user.order_id,
                symbol=user.symbol,
                side=user.side,
                stratergy=user.stratergy,
                buyprice=user.price,
                sellprice=float(price),
                buyquantity=user.quantity,
                sellquantity=user_qty,
                status="Completed",
                profit=((user_qty * float(price)) - (float(user.quantity) * float(user.price))),
                stratergy_name=user.stratergy_name,
                broker_id=user.broker_id
            )
            db.add(order_detail)
            
            trade_detail = tradeDetails(
                owner_id=user.owner_id,
                symbol=user.symbol,
                price=float(price),
                quantity=user_qty,
                side=side12,
                unique=user.order_id,
                status="Completed",
                orderid=user.order_id,
                stratergy=user.stratergy,
                remark="Order Already closed at broker end.",
                stratergy_name=user.stratergy_name,
                margin=margin_used,
                broker_id=user.broker_id
            )
            db.add(trade_detail)
            db.delete(user)
            db.commit()
        
        if user.side == "sell" and quantity_balance < 0:
            pass
        else:
            symbol = convert_symbol(user.symbol)
            price = get_live_price(symbol)
            margin_used = float(price) * float(user_qty)
            
            order_detail = OrderDetails(
                owner_id=user.owner_id,
                orderid=user.order_id,
                symbol=user.symbol,
                side=user.side,
                stratergy=user.stratergy,
                sellprice=user.price,
                buyprice=float(price),
                sellquantity=user.quantity,
                buyquantity=user_qty,
                status="Completed",
                profit=((float(user.quantity) * float(user.price)) - (user_qty * float(price))),
                stratergy_name=user.stratergy_name,
                broker_id=user.broker_id
            )
            db.add(order_detail)
            
            trade_detail = tradeDetails(
                owner_id=user.owner_id,
                symbol=user.symbol,
                price=float(price),
                quantity=user_qty,
                side=side12,
                unique=user.order_id,
                status="Completed",
                orderid=user.order_id,
                stratergy=user.stratergy,
                remark="Order Already closed at broker end.",
                stratergy_name=user.stratergy_name,
                margin=margin_used,
                broker_id=user.broker_id
            )
            db.add(trade_detail)
            db.delete(user)
            db.commit()
    else:
        client = DeltaExchangeClient(api_key=apikey, api_secret=apisecret)
        position = client.get_positions(product_id=user.symbol)
        if position['success'] == True:
            quantity_balance = int(position['result']['size'])
            user_qty = int(float(user.quantity))
            
            if user.side == "buy" and quantity_balance > 0:
                pass
            else:
                price = get_live_price(user.symbol)
                margin_used = float(price) * float(user_qty)
                
                order_detail = OrderDetails(
                    owner_id=user.owner_id,
                    orderid=user.order_id,
                    symbol=user.symbol,
                    side=user.side,
                    stratergy=user.stratergy,
                    buyprice=user.price,
                    sellprice=float(price),
                    buyquantity=user.quantity,
                    sellquantity=user_qty,
                    status="Completed",
                    profit=((user_qty * float(price)) - (float(user.quantity) * float(user.price))),
                    stratergy_name=user.stratergy_name,
                    broker_id=user.broker_id
                )
                db.add(order_detail)
                
                trade_detail = tradeDetails(
                    owner_id=user.owner_id,
                    symbol=user.symbol,
                    price=float(price),
                    quantity=user_qty,
                    side=side12,
                    unique=user.order_id,
                    status="Completed",
                    orderid=user.order_id,
                    stratergy=user.stratergy,
                    remark="Order Already closed at broker end.",
                    stratergy_name=user.stratergy_name,
                    margin=margin_used,
                    broker_id=user.broker_id
                )
                db.add(trade_detail)
                db.delete(user)
                db.commit()
            
            if user.side == "sell" and quantity_balance < 0:
                pass
            else:
                price = get_live_price(user.symbol)
                margin_used = float(price) * float(user_qty)
                
                order_detail = OrderDetails(
                    owner_id=user.owner_id,
                    orderid=user.order_id,
                    symbol=user.symbol,
                    side=user.side,
                    stratergy=user.stratergy,
                    sellprice=user.price,
                    buyprice=float(price),
                    sellquantity=user.quantity,
                    buyquantity=user_qty,
                    status="Completed",
                    profit=((float(user.quantity) * float(user.price)) - (user_qty * float(price))),
                    stratergy_name=user.stratergy_name,
                    broker_id=user.broker_id
                )
                db.add(order_detail)
                
                trade_detail = tradeDetails(
                    owner_id=user.owner_id,
                    symbol=user.symbol,
                    price=float(price),
                    quantity=user_qty,
                    side=side12,
                    unique=user.order_id,
                    status="Completed",
                    orderid=user.order_id,
                    stratergy=user.stratergy,
                    remark="Order Already closed at broker end.",
                    stratergy_name=user.stratergy_name,
                    margin=margin_used,
                    broker_id=user.broker_id
                )
                db.add(trade_detail)
                db.delete(user)
                db.commit()
    


   

