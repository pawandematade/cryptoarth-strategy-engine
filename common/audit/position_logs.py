"""
Position Audit Logging
Logs position open/close events
"""
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from common.redis import get_redis

logger = logging.getLogger(__name__)

def log_position_open(
    position_id: str,
    user_id: str,
    broker: str,
    symbol: str,
    quantity: float,
    entry_price: float,
    order_id: Optional[str] = None,
    request_id: Optional[str] = None
):
    """Log position opened"""
    log_data = {
        "type": "position_open",
        "position_id": position_id,
        "user_id": user_id,
        "broker": broker,
        "symbol": symbol,
        "quantity": quantity,
        "entry_price": entry_price,
        "order_id": order_id,
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.info(f"Position Open: {position_id} [{broker}] {symbol} {quantity} @ {entry_price}")
    
    redis = get_redis()
    if redis:
        try:
            key = f"audit:position:{position_id}"
            redis.setex(key, 604800, json.dumps(log_data))  # 7 days
        except Exception as e:
            logger.warning(f"Failed to store position log (non-fatal): {e}")

def log_position_close(
    position_id: str,
    exit_price: float,
    pnl: Optional[float],
    order_id: Optional[str] = None,
    request_id: Optional[str] = None
):
    """Log position closed"""
    log_data = {
        "type": "position_close",
        "position_id": position_id,
        "exit_price": exit_price,
        "pnl": pnl,
        "order_id": order_id,
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.info(f"Position Close: {position_id} [exit={exit_price}, pnl={pnl}]")
    
    redis = get_redis()
    if redis:
        try:
            key = f"audit:position:{position_id}:close"
            redis.setex(key, 604800, json.dumps(log_data))
        except Exception as e:
            logger.warning(f"Failed to store position close log (non-fatal): {e}")

