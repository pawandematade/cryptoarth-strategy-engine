"""
Set Signal Route (Place Order API)
Migrated from cryptoarth_backend/authenticate/views.py setSignal

Endpoint: POST /auth/setSignal/
Creates a copysignal record (order/signal) in the database.

Request/Response format matches cryptoarth_backend exactly.
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from pydantic import BaseModel, Field
import logging
from datetime import datetime
import pytz

from common.db import get_db
from api.user_dependencies import get_current_user_strict
from models import User
from common.redis import redis_client

logger = logging.getLogger(__name__)

router = APIRouter()

# Django table name constant (do not hardcode inline)
COPYSIGNAL_TABLE_NAME = "authenticate_copysignal"


class SetSignalRequest(BaseModel):
    """Request model for setSignal endpoint"""
    symbol: str
    symbolid: int
    side: str  # "buy" or "sell"
    target: float
    stoploss: float
    entry: Optional[float] = None  # Required for limit orders
    typeq: str  # "market" or "limit"
    strategy_id: int
    strategy_code: str
    leverage: int
    capital: float
    trailingpoints: Optional[float] = Field(default=0)


def get_live_price(symbol: str) -> float:
    """
    Get live price for a symbol from Redis cache only.
    Returns 503 error if price is not available in Redis.
    
    CRITICAL: No external HTTP calls - Redis-only for place-order request path.
    """
    price_key = f"DELTA-{symbol}"
    cached_price = redis_client.get(price_key)
    
    if cached_price:
        try:
            return float(cached_price)
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing cached price for {symbol}: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Live price data unavailable"
            )
    
    # Price not available in Redis - return 503
    logger.warning(f"Live price not available in Redis for symbol: {symbol}")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Live price not available. Please try again later."
    )


@router.post("/setSignal/", status_code=status.HTTP_200_OK)
def set_signal(
    request_data: SetSignalRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    Create a signal/order (copysignal record).
    
    Matches: cryptoarth_backend/authenticate/views.py setSignal
    
    Request body (JSON):
    {
        "symbol": str,
        "symbolid": int,
        "side": "buy" | "sell",
        "target": float,
        "stoploss": float,
        "entry": float (for limit orders),
        "typeq": "market" | "limit",
        "strategy_id": int,
        "strategy_code": str,
        "leverage": int,
        "capital": float,
        "trailingpoints": float (optional, default 0)
    }
    
    Response:
    {
        "message": "Signal saved successfully."
    }
    """
    try:
        # Convert Pydantic model to dict
        data = request_data.dict()
        
        # Validate entry price for limit orders
        if data['typeq'] != "market" and not data.get('entry'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="entry is required for limit orders"
            )
        
        # Get user's external_user_id (matches Django user.id)
        user_id = user.external_user_id
        
        # Handle trailingpoints - default to 0 if missing
        # Note: Django model stores as IntegerField, but accepts float from request
        trailing_pts = int(float(data.get('trailingpoints', 0) or 0))
        is_trailing = trailing_pts > 0
        
        # CRITICAL: Use hardcoded internal URL, ignore frontend-provided URL for security
        internal_signal_url = "https://trade-api.cryptoarth.in/auth/signal/"
        
        if data['typeq'] == "market":
            # Market order - get live price
            tz = pytz.timezone('Asia/Kolkata')
            now = datetime.now(tz)
            formatted_datetime = now.strftime("%m/%d/%Y %I:%M:%S %p")
            price1 = get_live_price(data['symbol'])
            
            # Calculate trailing price
            if data['side'] == "buy":
                tpprice = float(price1) + trailing_pts
            else:
                tpprice = float(price1) - trailing_pts
            
            # Insert into copysignal table using raw SQL within transaction
            # Note: Using raw SQL because copysignal is a Django model table
            # We're using Strategy Engine DB session but inserting into Django table
            # CRITICAL: Wrap in transaction to ensure atomicity and prevent partial writes
            try:
                insert_sql = text(f"""
                    INSERT INTO {COPYSIGNAL_TABLE_NAME} 
                    (owner_id, symbol, symbolid, side, target, stoploss, entry, typeq, 
                     leverage, capital, strategy_id, url, status, trailingpoints, trailingprice, is_trailing, created_at)
                    VALUES 
                    (:owner_id, :symbol, :symbolid, :side, :target, :stoploss, :entry, :typeq,
                     :leverage, :capital, :strategy_id, :url, :status, :trailingpoints, :trailingprice, :is_trailing, NOW())
                """)
                
                db.execute(insert_sql, {
                    'owner_id': user_id,
                    'symbol': data['symbol'],
                    'symbolid': int(data['symbolid']),
                    'side': data['side'],
                    'target': float(data['target']),
                    'stoploss': float(data['stoploss']),
                    'entry': float(price1),
                    'typeq': data['typeq'],
                    'leverage': int(data['leverage']),
                    'capital': float(data['capital']),
                    'strategy_id': int(data['strategy_id']),
                    'url': internal_signal_url,
                    'status': 'Active',
                    'trailingpoints': trailing_pts,
                    'trailingprice': tpprice,
                    'is_trailing': is_trailing
                })
                db.commit()
            except Exception as db_error:
                db.rollback()
                logger.error(f"Database error in setSignal (market order): {db_error}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error saving signal to database"
                )
            
            logger.info(f"[setSignal] ✅ DB saved: copysignal for user_id={user_id}, symbol={data['symbol']}")
            
            return {'message': 'Signal saved successfully.'}
        
        else:
            # Limit order - use provided entry price
            trailing_pts = int(float(data.get('trailingpoints', 0) or 0))
            is_trailing = trailing_pts > 0
            
            # Calculate trailing price
            if data['side'] == "buy":
                tpprice = float(data['entry']) + trailing_pts
            else:
                tpprice = float(data['entry']) - trailing_pts
            
            # Insert into copysignal table within transaction
            # CRITICAL: Wrap in transaction to ensure atomicity and prevent partial writes
            try:
                insert_sql = text(f"""
                    INSERT INTO {COPYSIGNAL_TABLE_NAME} 
                    (owner_id, symbol, symbolid, side, target, stoploss, entry, typeq, 
                     leverage, capital, strategy_id, url, status, trailingpoints, trailingprice, is_trailing, created_at)
                    VALUES 
                    (:owner_id, :symbol, :symbolid, :side, :target, :stoploss, :entry, :typeq,
                     :leverage, :capital, :strategy_id, :url, :status, :trailingpoints, :trailingprice, :is_trailing, NOW())
                """)
                
                db.execute(insert_sql, {
                    'owner_id': user_id,
                    'symbol': data['symbol'],
                    'symbolid': int(data['symbolid']),
                    'side': data['side'],
                    'target': float(data['target']),
                    'stoploss': float(data['stoploss']),
                    'entry': float(data['entry']),
                    'typeq': data['typeq'],
                    'leverage': int(data['leverage']),
                    'capital': float(data['capital']),
                    'strategy_id': int(data['strategy_id']),
                    'url': internal_signal_url,
                    'status': 'Pending',
                    'trailingpoints': trailing_pts,
                    'trailingprice': tpprice,
                    'is_trailing': is_trailing
                })
                db.commit()
            except Exception as db_error:
                db.rollback()
                logger.error(f"Database error in setSignal (limit order): {db_error}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error saving signal to database"
                )
            
            logger.info(f"[setSignal] ✅ DB saved: copysignal for user_id={user_id}, symbol={data['symbol']}")
            
            return {'message': 'Signal saved successfully.'}
        
    except HTTPException:
        # Re-raise HTTP exceptions (including 503 for missing Redis price)
        raise
    except Exception as e:
        # Rollback any pending transaction
        db.rollback()
        logger.error(f"Error in setSignal: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving signal: {str(e)}"
        )

