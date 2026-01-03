"""
Copy Trading Routes
Migrated from cryptoarth_backend/authenticate/views.py
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging
from datetime import datetime
import pytz

from common.db import get_db
from common.auth import get_current_user
from engine.models import User
from engine.models_legacy_trading import copysignal, highLowstratergy
from order.orders.service import get_live_price

logger = logging.getLogger(__name__)

router = APIRouter()


class SetSignalRequest(BaseModel):
    symbol: str
    symbolid: int
    side: str
    target: float
    stoploss: float
    entry: Optional[float] = None
    typeq: str  # "market" or "limit"
    strategy_id: int
    strategy_code: str
    leverage: int
    capital: float
    trailingpoints: Optional[float] = 0


class CloseSignalRequest(BaseModel):
    id: int


@router.post("/setSignal", status_code=status.HTTP_200_OK)
def set_signal(
    request: SetSignalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create copy trading signal (market or limit order)"""
    try:
        # Hardcoded internal URL for security
        internal_signal_url = "https://trade-api.cryptoarth.in/auth/signal/"
        
        if request.typeq == "market":
            tz = pytz.timezone('Asia/Kolkata')
            now = datetime.now(tz)
            formatted_datetime = now.strftime("%m/%d/%Y %I:%M:%S %p")
            price1 = get_live_price(request.symbol)
            
            trailing_pts = float(request.trailingpoints or 0)
            is_trailing = trailing_pts > 0
            
            if request.side == "buy":
                tpprice = float(price1) + trailing_pts
            else:
                tpprice = float(price1) - trailing_pts
            
            copy = copysignal(
                owner_id=user.id,
                is_trailing=is_trailing,
                symbol=request.symbol,
                side=request.side,
                target=request.target,
                stoploss=request.stoploss,
                entry=float(price1),
                typeq=request.typeq,
                strategy_id=request.strategy_id,
                url=internal_signal_url,
                trailingpoints=trailing_pts,
                status="Active",
                trailingprice=tpprice,
                symbolid=request.symbolid,
                leverage=request.leverage,
                capital=request.capital
            )
            db.add(copy)
            db.commit()
            
            return {"message": "Signal saved successfully."}
        else:
            # Limit order
            trailing_pts = float(request.trailingpoints or 0)
            is_trailing = trailing_pts > 0
            
            if request.side == "buy":
                tpprice = float(request.entry) + trailing_pts
            else:
                tpprice = float(request.entry) - trailing_pts
            
            copy = copysignal(
                owner_id=user.id,
                is_trailing=is_trailing,
                symbol=request.symbol,
                side=request.side,
                target=request.target,
                stoploss=request.stoploss,
                entry=float(request.entry),
                typeq=request.typeq,
                strategy_id=request.strategy_id,
                url=internal_signal_url,
                trailingpoints=trailing_pts,
                status="Pending",
                trailingprice=tpprice,
                symbolid=request.symbolid,
                leverage=request.leverage,
                capital=request.capital
            )
            db.add(copy)
            db.commit()
            
            return {"message": "Signal saved successfully."}
    except Exception as e:
        db.rollback()
        logger.error(f"Error setting signal: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/closeSignal", status_code=status.HTTP_200_OK)
def close_signal(
    request: CloseSignalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Close copy trading signal"""
    try:
        signal = db.query(copysignal).filter(copysignal.id == request.id).first()
        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        # Check if user is staff (admin) - for now allowing all authenticated users
        # TODO: Add proper admin check if needed
        
        tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(tz)
        formatted_datetime = now.strftime("%m/%d/%Y %I:%M:%S %p")
        headers = {"Content-Type": "text/plain"}
        
        if signal.side == "buy":
            side = "sell"
        else:
            side = "buy"
        
        strategy = db.query(highLowstratergy).filter(highLowstratergy.id == signal.strategy_id).first()
        strategy_code = strategy.stratergy_code if strategy else "NA"
        
        parts2 = [
            signal.symbol,
            str(signal.symbolid), "0", "0", "0",
            str(signal.strategy_id),
            str(strategy_code),
            "DELTA",
            side,
            formatted_datetime,
            str(signal.leverage),
            str(signal.capital),
            "Exit"
        ]
        final_string2 = "|".join(parts2) + "|"
        
        import requests
        response = requests.post(signal.url, data=final_string2.encode("utf-8"), headers=headers)
        
        signal.status = "Completed"
        db.commit()
        
        return {"message": "Order Signal close Successfully."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error closing signal: {e}")
        raise HTTPException(status_code=400, detail=str(e))
