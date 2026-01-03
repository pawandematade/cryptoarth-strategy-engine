"""
Position Management Routes
Migrated from cryptoarth_backend/authenticate/views.py
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import logging
from datetime import datetime
import pytz

from common.db import get_db
from common.auth import get_current_user
from engine.models import User
from engine.models_legacy_trading import Position, BrokerModels, SymbolMaster, OrderDetails, tradeDetails
from order.brokers.delta.client import DeltaExchangeClient
from order.brokers.coindcx.client import coindcxclient
from common.security import get_broker_credentials

logger = logging.getLogger(__name__)

router = APIRouter()


def get_open_position1(positions, symbol):
    """Returns the open quantity for a given trading symbol"""
    if not positions:
        return 0
    for pos in positions:
        if pos.get('pair') == symbol:
            return pos.get('active_pos', 0)
    return 0


def convert_symbol(symbol):
    """Convert symbol format for CoinDCX"""
    base_currency = symbol.replace('USD', '')
    return f"B-{base_currency}_USDT"


def convert_ms_to_kolkata_datetime(timestamp_ms: int):
    """Convert Unix timestamp in milliseconds to datetime object in Kolkata timezone"""
    try:
        kolkata_tz = pytz.timezone('Asia/Kolkata')
        return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=kolkata_tz)
    except (ValueError, TypeError):
        return None


class ClosePositionRequest(BaseModel):
    position_id: int


class AdminClosePositionRequest(BaseModel):
    symbol: str
    quantity: float
    side: str
    broker_id: int


class GetOpenPositionRequest(BaseModel):
    strategy_id: int
    symbol: str


@router.post("/open", status_code=status.HTTP_200_OK)
def get_open_positions(
    request: GetOpenPositionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get open positions for strategy"""
    try:
        symbolmaster = db.query(SymbolMaster).filter(SymbolMaster.symbol == request.symbol).first()
        if not symbolmaster:
            raise HTTPException(status_code=404, detail="Symbol not found")
        
        users_coindcx = db.query(Position).join(BrokerModels).filter(
            BrokerModels.broker == "Coindcx",
            Position.stratergy == str(request.strategy_id)
        ).all()
        
        users_delta = db.query(Position).join(BrokerModels).filter(
            BrokerModels.broker == "DeltaExchange",
            Position.stratergy == str(request.strategy_id)
        ).all()
        
        dataset = []
        
        # Process CoinDCX users
        for pos in users_coindcx:
            try:
                apikey, apisecret = get_broker_credentials(pos.broker)
                if not apikey or not apisecret:
                    continue
                client = coindcxclient(api_key=apikey, api_secret=apisecret)
                symbol_coindcx = convert_symbol(request.symbol)
                position = client.get_positions_coindcx(symbol=symbol_coindcx)
                quantity_balance = get_open_position1(position, symbol_coindcx)
                if float(quantity_balance) != 0:
                    dataset.append({
                        'user_id': pos.owner_id,
                        'user_phone': pos.owner.phone if pos.owner else None,
                        'user_name': pos.owner.first_name if pos.owner else None,
                        'broker': pos.broker_id,
                        'broker_name': pos.broker.broker if pos.broker else 'Coindcx',
                        'open_quantity': quantity_balance
                    })
            except Exception as e:
                logger.error(f"Error processing CoinDCX position: {e}")
                continue
        
        # Process Delta users
        for pos in users_delta:
            try:
                apikey, apisecret = get_broker_credentials(pos.broker)
                if not apikey or not apisecret:
                    continue
                client = DeltaExchangeClient(api_key=apikey, api_secret=apisecret)
                position = client.get_positions(product_id=symbolmaster.symbolid)
                if position['success'] == True:
                    quantity_balance = int(position['result']['size'])
                else:
                    quantity_balance = 0
                if float(quantity_balance) != 0:
                    dataset.append({
                        'user_id': pos.owner_id,
                        'user_phone': pos.owner.phone if pos.owner else None,
                        'user_name': pos.owner.first_name if pos.owner else None,
                        'broker': pos.broker_id,
                        'broker_name': pos.broker.broker if pos.broker else 'DeltaExchange',
                        'open_quantity': quantity_balance
                    })
            except Exception as e:
                logger.error(f"Error processing Delta position: {e}")
                continue
        
        return dataset
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting open positions: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/close", status_code=status.HTTP_200_OK)
def close_position(
    request: ClosePositionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Close user's position"""
    try:
        position = db.query(Position).filter(
            Position.id == request.position_id,
            Position.owner_id == user.id
        ).first()
        
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        
        apikey, apisecret = get_broker_credentials(position.broker)
        if not apikey or not apisecret:
            raise HTTPException(status_code=400, detail="Broker credentials not available")
        
        if position.side == "buy":
            side12 = "sell"
        else:
            side12 = "buy"
        
        if position.broker.broker == "Coindcx":
            client = coindcxclient(api_key=apikey, api_secret=apisecret)
            broker_position = client.get_positions_coindcx(symbol=position.symbol)
            quantity_balance = get_open_position1(broker_position, position.symbol)
            user_qty = float(position.quantity)
            
            if position.side == "buy" and quantity_balance > 0:
                qty = min(user_qty, abs(quantity_balance))
                order = client.place_order_coindcx(side=side12, symbol=position.symbol, qty=qty, leverage=position.leverage)
                margin_used = float(order['result'][0]['price']) * float(order['result'][0]['total_quantity'])
                
                order_detail = OrderDetails(
                    owner_id=position.owner_id,
                    orderid=position.order_id,
                    symbol=position.symbol,
                    side=position.side,
                    stratergy=position.stratergy,
                    date=convert_ms_to_kolkata_datetime(int(order['result'][0]['created_at'])),
                    buyprice=position.price,
                    sellprice=float(order['result'][0]['price']),
                    buyquantity=position.quantity,
                    sellquantity=order['result'][0]['total_quantity'],
                    status="Completed",
                    profit=((order['result'][0]['total_quantity'] * float(order['result'][0]['price'])) - (float(position.quantity) * float(position.price))),
                    stratergy_name=position.stratergy_name,
                    broker_id=position.broker_id
                )
                db.add(order_detail)
                
                trade_detail = tradeDetails(
                    owner_id=position.owner_id,
                    symbol=position.symbol,
                    price=float(order['result'][0]['price']),
                    quantity=order['result'][0]['total_quantity'],
                    side=side12,
                    unique=order['result'][0]['id'],
                    date=convert_ms_to_kolkata_datetime(int(order['result'][0]['created_at'])),
                    status=order['result'][0].get('state', 'completed'),
                    orderid=position.order_id,
                    stratergy=position.stratergy,
                    remark="Order Placed Successfully.",
                    stratergy_name=position.stratergy_name,
                    margin=margin_used,
                    broker_id=position.broker_id
                )
                db.add(trade_detail)
                db.delete(position)
                db.commit()
                return {"message": "Position closed successfully."}
            elif position.side == "sell" and quantity_balance < 0:
                qty = min(user_qty, abs(quantity_balance))
                order = client.place_order_coindcx(side=side12, symbol=position.symbol, qty=qty, leverage=position.leverage)
                margin_used = float(order['result'][0]['price']) * float(order['result'][0]['total_quantity'])
                
                order_detail = OrderDetails(
                    owner_id=position.owner_id,
                    orderid=position.order_id,
                    symbol=position.symbol,
                    side=position.side,
                    stratergy=position.stratergy,
                    date=convert_ms_to_kolkata_datetime(int(order['result'][0]['created_at'])),
                    sellprice=position.price,
                    buyprice=float(order['result'][0]['price']),
                    sellquantity=position.quantity,
                    buyquantity=order['result'][0]['total_quantity'],
                    status="Completed",
                    profit=((float(position.quantity) * float(position.price)) - (order['result'][0]['total_quantity'] * float(order['result'][0]['price']))),
                    stratergy_name=position.stratergy_name,
                    broker_id=position.broker_id
                )
                db.add(order_detail)
                
                trade_detail = tradeDetails(
                    owner_id=position.owner_id,
                    symbol=position.symbol,
                    price=float(order['result'][0]['price']),
                    quantity=order['result'][0]['total_quantity'],
                    side=side12,
                    unique=order['result'][0]['id'],
                    date=convert_ms_to_kolkata_datetime(int(order['result'][0]['created_at'])),
                    status=order['result'][0].get('state', 'completed'),
                    orderid=position.order_id,
                    stratergy=position.stratergy,
                    remark="Order Placed Successfully.",
                    stratergy_name=position.stratergy_name,
                    margin=margin_used,
                    broker_id=position.broker_id
                )
                db.add(trade_detail)
                db.delete(position)
                db.commit()
                return {"message": "Position closed successfully."}
            else:
                raise HTTPException(status_code=400, detail="No open position found.")
        else:
            client = DeltaExchangeClient(api_key=apikey, api_secret=apisecret)
            broker_position = client.get_positions(product_id=position.symbol)
            if broker_position['success'] == True:
                quantity_balance = int(broker_position['result']['size'])
                user_qty = int(float(position.quantity))
                
                if position.side == "buy" and quantity_balance > 0:
                    qty = min(user_qty, abs(quantity_balance))
                    order = client.place_order(product_symbol=position.symbol, side=side12, size=qty)
                    
                    margin_used = float(order['result']['average_fill_price']) * float(order['result']['size']) * 1.0
                    
                    order_detail = OrderDetails(
                        owner_id=position.owner_id,
                        orderid=position.order_id,
                        symbol=position.symbol,
                        side=position.side,
                        stratergy=position.stratergy,
                        date=order['result']['created_at'],
                        buyprice=position.price,
                        sellprice=float(order['result']['average_fill_price']),
                        buyquantity=position.quantity,
                        sellquantity=order['result']['size'],
                        status="Completed",
                        profit=((order['result']['size'] * float(order['result']['average_fill_price'])) - (float(position.quantity) * float(position.price))),
                        stratergy_name=position.stratergy_name,
                        broker_id=position.broker_id
                    )
                    db.add(order_detail)
                    
                    trade_detail = tradeDetails(
                        owner_id=position.owner_id,
                        symbol=position.symbol,
                        price=float(order['result']['average_fill_price']),
                        quantity=order['result']['size'],
                        side=side12,
                        unique=order['result']['id'],
                        date=order['result']['created_at'],
                        status=order['result']['state'],
                        orderid=position.order_id,
                        stratergy=position.stratergy,
                        remark="Order Placed Successfully.",
                        stratergy_name=position.stratergy_name,
                        margin=margin_used,
                        broker_id=position.broker_id
                    )
                    db.add(trade_detail)
                    db.delete(position)
                    db.commit()
                    return {"message": "Position closed successfully."}
                elif position.side == "sell" and quantity_balance < 0:
                    qty = min(user_qty, abs(quantity_balance))
                    order = client.place_order(product_symbol=position.symbol, side=side12, size=qty)
                    
                    margin_used = float(order['result']['average_fill_price']) * float(order['result']['size']) * 1.0
                    
                    order_detail = OrderDetails(
                        owner_id=position.owner_id,
                        orderid=position.order_id,
                        symbol=position.symbol,
                        side=position.side,
                        stratergy=position.stratergy,
                        date=order['result']['created_at'],
                        sellprice=position.price,
                        buyprice=float(order['result']['average_fill_price']),
                        sellquantity=position.quantity,
                        buyquantity=order['result']['size'],
                        status="Completed",
                        profit=((float(position.quantity) * float(position.price)) - (order['result']['size'] * float(order['result']['average_fill_price']))),
                        stratergy_name=position.stratergy_name,
                        broker_id=position.broker_id
                    )
                    db.add(order_detail)
                    
                    trade_detail = tradeDetails(
                        owner_id=position.owner_id,
                        symbol=position.symbol,
                        price=float(order['result']['average_fill_price']),
                        quantity=order['result']['size'],
                        side=side12,
                        unique=order['result']['id'],
                        date=order['result']['created_at'],
                        status=order['result']['state'],
                        orderid=position.order_id,
                        stratergy=position.stratergy,
                        remark="Order Placed Successfully.",
                        stratergy_name=position.stratergy_name,
                        margin=margin_used,
                        broker_id=position.broker_id
                    )
                    db.add(trade_detail)
                    db.delete(position)
                    db.commit()
                    return {"message": "Position closed successfully."}
                else:
                    raise HTTPException(status_code=400, detail="No open position found.")
            else:
                raise HTTPException(status_code=400, detail="Unable to fetch position from broker")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error closing position: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin-close", status_code=status.HTTP_200_OK)
def admin_close_position(
    request: AdminClosePositionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Close position (admin function)"""
    try:
        broker = db.query(BrokerModels).filter(BrokerModels.id == request.broker_id).first()
        if not broker:
            raise HTTPException(status_code=404, detail="Broker not found")
        
        apikey, apisecret = get_broker_credentials(broker)
        if not apikey or not apisecret:
            raise HTTPException(status_code=400, detail="Broker credentials not available")
        
        quantity = abs(int(request.quantity))
        side = request.side
        
        if broker.broker == "Coindcx":
            client = coindcxclient(api_key=apikey, api_secret=apisecret)
            symbol_coindcx = convert_symbol(request.symbol)
            order = client.place_order_coindcx(side=side, symbol=symbol_coindcx, qty=quantity, leverage=50)
            if order.get('success') != True:
                raise HTTPException(status_code=400, detail="Error closing position")
        else:
            client = DeltaExchangeClient(api_key=apikey, api_secret=apisecret)
            order = client.place_order(product_symbol=request.symbol, side=side, size=quantity)
            if order.get('success') != True:
                raise HTTPException(status_code=400, detail="Error closing position")
        
        return {"message": "Position Closed Successfully."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in admin close position: {e}")
        raise HTTPException(status_code=400, detail=str(e))
