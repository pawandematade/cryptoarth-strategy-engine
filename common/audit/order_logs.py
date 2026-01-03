"""
Order Audit Logging
Logs all order events: placed, success, failure
"""
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from common.redis import get_redis

logger = logging.getLogger(__name__)

def log_order_placed(
    order_id: str,
    user_id: str,
    strategy_id: Optional[str],
    broker: str,
    symbol: str,
    side: str,
    quantity: float,
    order_type: str,
    request_id: Optional[str] = None
):
    """Log order placement"""
    log_data = {
        "type": "order_placed",
        "order_id": order_id,
        "user_id": user_id,
        "strategy_id": strategy_id,
        "broker": broker,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.info(f"Order Placed: {order_id} [{broker}] {side} {quantity} {symbol}")
    
    redis = get_redis()
    if redis:
        try:
            key = f"audit:order:{order_id}"
            redis.setex(key, 604800, json.dumps(log_data))  # 7 days
        except Exception as e:
            logger.warning(f"Failed to store order log (non-fatal): {e}")

def log_order_success(
    order_id: str,
    broker_order_id: Optional[str],
    filled_quantity: float,
    avg_price: Optional[float],
    request_id: Optional[str] = None
):
    """Log successful order execution"""
    log_data = {
        "type": "order_success",
        "order_id": order_id,
        "broker_order_id": broker_order_id,
        "filled_quantity": filled_quantity,
        "avg_price": avg_price,
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.info(f"Order Success: {order_id} [filled={filled_quantity}, price={avg_price}]")
    
    redis = get_redis()
    if redis:
        try:
            key = f"audit:order:{order_id}:success"
            redis.setex(key, 604800, json.dumps(log_data))
        except Exception as e:
            logger.warning(f"Failed to store order success log (non-fatal): {e}")

def log_order_failure(
    order_id: str,
    error_message: str,
    error_code: Optional[str],
    request_id: Optional[str] = None
):
    """Log order failure"""
    log_data = {
        "type": "order_failure",
        "order_id": order_id,
        "error_message": error_message,
        "error_code": error_code,
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.error(f"Order Failure: {order_id} [error={error_message}]")
    
    redis = get_redis()
    if redis:
        try:
            key = f"audit:order:{order_id}:failure"
            redis.setex(key, 604800, json.dumps(log_data))
        except Exception as e:
            logger.warning(f"Failed to store order failure log (non-fatal): {e}")

