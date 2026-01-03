"""
Broker Raw Response Audit Logging
Logs all broker API responses for debugging and analysis
"""
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from common.redis import get_redis

logger = logging.getLogger(__name__)

def log_broker_response(
    broker: str,
    endpoint: str,
    request_data: Optional[Dict[str, Any]],
    response_data: Dict[str, Any],
    status_code: int,
    duration_ms: Optional[float],
    order_id: Optional[str] = None,
    request_id: Optional[str] = None
):
    """
    Log broker API response
    Stores raw request/response for debugging
    """
    log_data = {
        "type": "broker_response",
        "broker": broker,
        "endpoint": endpoint,
        "request_data": request_data,
        "response_data": response_data,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "order_id": order_id,
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.debug(f"Broker Response: {broker} {endpoint} [status={status_code}, duration={duration_ms}ms]")
    
    redis = get_redis()
    if redis:
        try:
            key = f"audit:broker:{broker}:{datetime.utcnow().strftime('%Y%m%d')}:{order_id or request_id or 'unknown'}"
            redis.setex(key, 604800, json.dumps(log_data))  # 7 days
        except Exception as e:
            logger.warning(f"Failed to store broker log (non-fatal): {e}")

