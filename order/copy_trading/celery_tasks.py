"""
Copy Trading Celery Tasks - Refactored for SQLAlchemy
Converted from Django ORM to SQLAlchemy
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from concurrent.futures import ThreadPoolExecutor
from order.orders.service import get_live_price

# SQLAlchemy models
from app.models_legacy_trading import copysignal

# Redis cache (if needed)
from common.redis import redis_client


def check_copy_tp(db: Session):
    """Check copy trading TP (take profit) for buy orders"""
    userdata = db.query(copysignal).filter(
        and_(copysignal.status == "Active", copysignal.side == "buy")
    ).all()
    tokens_set = set([user.symbol for user in userdata])
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_token_tp12, token, db) for token in tokens_set]


def check_copy_sell_tp(db: Session):
    """Check copy trading TP (take profit) for sell orders"""
    userdata = db.query(copysignal).filter(
        and_(copysignal.status == "Active", copysignal.side == "sell")
    ).all()
    tokens_set = set([user.symbol for user in userdata])
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_token_sell_tp23, token, db) for token in tokens_set]


def check_copy_limit(db: Session):
    """Check copy trading limit orders for buy"""
    userdata = db.query(copysignal).filter(
        and_(
            copysignal.status == "Pending",
            copysignal.side == "buy",
            copysignal.typeq == "limit"
        )
    ).all()
    tokens_set = set([user.symbol for user in userdata])
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_buy_limit, token, db) for token in tokens_set]


def check_copy_limit1(db: Session):
    """Check copy trading limit orders for buy (sllimit)"""
    userdata = db.query(copysignal).filter(
        and_(
            copysignal.status == "Pending",
            copysignal.side == "buy",
            copysignal.typeq == "sllimit"
        )
    ).all()
    tokens_set = set([user.symbol for user in userdata])
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_buy_limit1, token, db) for token in tokens_set]


def check_copy_sell_limit(db: Session):
    """Check copy trading limit orders for sell"""
    userdata = db.query(copysignal).filter(
        and_(
            copysignal.status == "Pending",
            copysignal.side == "sell",
            copysignal.typeq == "limit"
        )
    ).all()
    tokens_set = set([user.symbol for user in userdata])
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_sell_limit, token, db) for token in tokens_set]


def check_copy_sell_limit1(db: Session):
    """Check copy trading limit orders for sell (sllimit)"""
    userdata = db.query(copysignal).filter(
        and_(
            copysignal.status == "Pending",
            copysignal.side == "sell",
            copysignal.typeq == "sllimit"
        )
    ).all()
    tokens_set = set([user.symbol for user in userdata])
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop_logic = [executor.submit(process_sell_limit1, token, db) for token in tokens_set]


def process_token_tp12(token: str, db: Session):
    """Process take profit for buy orders"""
    price = float(get_live_price(token))
    
    # Update status to Processing
    db.query(copysignal).filter(
        and_(
            copysignal.status == "Active",
            copysignal.side == "buy",
            or_(copysignal.target < price, copysignal.stoploss > price),
            copysignal.symbol == token
        )
    ).update({"status": "Processing"}, synchronize_session=False)
    db.commit()
    
    # Get signals to process
    userdata_set = db.query(copysignal).filter(
        and_(
            copysignal.status == "Processing",
            copysignal.side == "buy",
            or_(copysignal.target < price, copysignal.stoploss > price),
            copysignal.symbol == token
        )
    ).all()
    
    # Update trailing stop loss
    trailing_signals = db.query(copysignal).filter(
        and_(
            copysignal.status == "Active",
            copysignal.side == "buy",
            copysignal.trailingprice < price,
            copysignal.target > price,
            copysignal.is_trailing == True
        )
    ).all()
    
    for signal in trailing_signals:
        signal.stoploss = signal.stoploss + signal.trailingpoints
        signal.trailingprice = signal.trailingprice + signal.trailingpoints
    db.commit()
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task, signal, db) for signal in userdata_set]


def process_token_sell_tp23(token: str, db: Session):
    """Process take profit for sell orders"""
    price = float(get_live_price(token))
    
    # Update status to Processing
    db.query(copysignal).filter(
        and_(
            copysignal.status == "Active",
            copysignal.side == "sell",
            or_(copysignal.target > price, copysignal.stoploss < price),
            copysignal.symbol == token
        )
    ).update({"status": "Processing"}, synchronize_session=False)
    db.commit()
    
    # Get signals to process
    userdata_set = db.query(copysignal).filter(
        and_(
            copysignal.status == "Processing",
            copysignal.side == "sell",
            or_(copysignal.target > price, copysignal.stoploss < price),
            copysignal.symbol == token
        )
    ).all()
    
    # Update trailing stop loss
    trailing_signals = db.query(copysignal).filter(
        and_(
            copysignal.status == "Active",
            copysignal.side == "sell",
            copysignal.trailingprice > price,
            copysignal.target < price,
            copysignal.is_trailing == True
        )
    ).all()
    
    for signal in trailing_signals:
        signal.stoploss = signal.stoploss - signal.trailingpoints
        signal.trailingprice = signal.trailingprice - signal.trailingpoints
    db.commit()
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task, signal, db) for signal in userdata_set]


def process_buy_limit(token: str, db: Session):
    """Process buy limit orders"""
    price = float(get_live_price(token))
    
    db.query(copysignal).filter(
        and_(
            copysignal.status == "Pending",
            copysignal.side == "buy",
            copysignal.typeq == "limit",
            copysignal.symbol == token,
            copysignal.entry > price
        )
    ).update({"status": "Processing"}, synchronize_session=False)
    db.commit()
    
    userdata_set = db.query(copysignal).filter(
        and_(
            copysignal.status == "Processing",
            copysignal.side == "buy",
            copysignal.typeq == "limit",
            copysignal.symbol == token,
            copysignal.entry > price
        )
    ).all()
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task1, signal, db) for signal in userdata_set]


def process_buy_limit1(token: str, db: Session):
    """Process buy limit orders (sllimit)"""
    price = float(get_live_price(token))
    
    db.query(copysignal).filter(
        and_(
            copysignal.status == "Pending",
            copysignal.side == "buy",
            copysignal.typeq == "sllimit",
            copysignal.symbol == token,
            copysignal.entry < price
        )
    ).update({"status": "Processing"}, synchronize_session=False)
    db.commit()
    
    userdata_set = db.query(copysignal).filter(
        and_(
            copysignal.status == "Processing",
            copysignal.side == "buy",
            copysignal.typeq == "sllimit",
            copysignal.symbol == token,
            copysignal.entry < price
        )
    ).all()
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task1, signal, db) for signal in userdata_set]


def process_sell_limit(token: str, db: Session):
    """Process sell limit orders"""
    price = float(get_live_price(token))
    
    db.query(copysignal).filter(
        and_(
            copysignal.status == "Pending",
            copysignal.side == "sell",
            copysignal.typeq == "limit",
            copysignal.symbol == token,
            copysignal.entry < price
        )
    ).update({"status": "Processing"}, synchronize_session=False)
    db.commit()
    
    userdata_set = db.query(copysignal).filter(
        and_(
            copysignal.status == "Processing",
            copysignal.side == "sell",
            copysignal.typeq == "limit",
            copysignal.symbol == token,
            copysignal.entry < price
        )
    ).all()
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task1, signal, db) for signal in userdata_set]


def process_sell_limit1(token: str, db: Session):
    """Process sell limit orders (sllimit)"""
    price = float(get_live_price(token))
    
    db.query(copysignal).filter(
        and_(
            copysignal.status == "Pending",
            copysignal.side == "sell",
            copysignal.typeq == "sllimit",
            copysignal.symbol == token,
            copysignal.entry > price
        )
    ).update({"status": "Processing"}, synchronize_session=False)
    db.commit()
    
    userdata_set = db.query(copysignal).filter(
        and_(
            copysignal.status == "Processing",
            copysignal.side == "sell",
            copysignal.typeq == "sllimit",
            copysignal.symbol == token,
            copysignal.entry > price
        )
    ).all()
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop_logic = [executor.submit(process_task1, signal, db) for signal in userdata_set]


def process_task(signal: copysignal, db: Session):
    """Process exit signal task"""
    try:
        import pytz
        from datetime import datetime
        import requests
        
        tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(tz)
        formatted_datetime = now.strftime("%m/%d/%Y %I:%M:%S %p")
        headers = {"Content-Type": "text/plain"}
        
        if signal.side == "buy":
            side = "sell"
        else:
            side = "buy"
        
        parts2 = [
            signal.symbol,
            str(signal.symbolid), "0", "0", "0",
            str(signal.strategy_id),
            str(signal.strategy.stratergy_code) if signal.strategy else "NA",
            "DELTA",
            side,
            formatted_datetime,
            str(signal.leverage),
            str(signal.capital),
            "Exit"
        ]
        final_string2 = "|".join(parts2) + "|"
        response = requests.post(signal.url, data=final_string2.encode("utf-8"), headers=headers)
        signal.status = "Completed"
        db.commit()
    except Exception as e:
        print(str(e))
        db.rollback()


def process_task1(signal: copysignal, db: Session):
    """Process entry signal task"""
    import pytz
    from datetime import datetime
    import requests
    
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    formatted_datetime = now.strftime("%m/%d/%Y %I:%M:%S %p")
    headers = {"Content-Type": "text/plain"}
    
    parts2 = [
        signal.symbol,
        str(signal.symbolid), "0", "0", "0",
        str(signal.strategy_id),
        str(signal.strategy.stratergy_code) if signal.strategy else "NA",
        "DELTA",
        signal.side,
        formatted_datetime,
        str(signal.leverage),
        str(signal.capital),
        "Entry"
    ]
    final_string2 = "|".join(parts2) + "|"
    response = requests.post(signal.url, data=final_string2.encode("utf-8"), headers=headers)
    signal.status = "Active"
    db.commit()
