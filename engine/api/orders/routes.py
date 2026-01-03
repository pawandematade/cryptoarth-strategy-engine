"""
Order Placement Routes
Migrated from cryptoarth_backend/authenticate/views.py
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging

from common.db import get_db
from common.auth import get_current_user
from engine.models import User
from order.orders.service import process_entry_order, process_exit_order

logger = logging.getLogger(__name__)

router = APIRouter()


class PlaceOrderRequest(BaseModel):
    symbol: int
    side: str
    leverage: int
    capital: float
    strategy_id: int
    strategy_name: str


class ExitOrderRequest(BaseModel):
    strategy_id: int
    symbol: int
    side: str
    strategy_name: str


@router.post("/place", status_code=status.HTTP_200_OK)
def place_order(
    request: PlaceOrderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Place entry order for strategy execution"""
    try:
        processor = process_entry_order(
            symbol=request.symbol,
            side=request.side,
            leverage=request.leverage,
            capital=request.capital,
            strategy_id=request.strategy_id,
            strategy_name=request.strategy_name,
            db=db
        )
        processor.process()
        return {"message": "Order placed successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error placing order: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/exit", status_code=status.HTTP_200_OK)
def exit_order(
    request: ExitOrderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Place exit order to close position"""
    try:
        processor = process_exit_order(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            side=request.side,
            strategy_name=request.strategy_name,
            db=db
        )
        processor.process()
        return {"message": "Order exited successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error exiting order: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/squareoff", status_code=status.HTTP_200_OK)
def squareoff_order(
    request: ExitOrderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Square off all positions for a strategy (same as exit)"""
    try:
        processor = process_exit_order(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            side=request.side,
            strategy_name=request.strategy_name,
            db=db
        )
        processor.process()
        return {"message": "Position squared off successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error squaring off order: {e}")
        raise HTTPException(status_code=400, detail=str(e))
