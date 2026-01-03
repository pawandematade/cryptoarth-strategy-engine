"""
Error Audit Logging
Logs all errors with correlation_id for tracing
"""
import logging
import json
import traceback
from typing import Dict, Any, Optional
from datetime import datetime
from common.redis import get_redis

logger = logging.getLogger(__name__)

def log_error(
    error_message: str,
    error_type: str,
    correlation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    exception: Optional[Exception] = None
):
    """
    Log error with full context
    Includes stack trace if exception provided
    """
    error_data = {
        "type": "error",
        "error_message": error_message,
        "error_type": error_type,
        "correlation_id": correlation_id,
        "user_id": user_id,
        "request_id": request_id,
        "context": context,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if exception:
        error_data["stack_trace"] = traceback.format_exc()
    
    logger.error(f"Error: {error_message} [correlation_id={correlation_id}, type={error_type}]")
    
    redis = get_redis()
    if redis:
        try:
            key = f"audit:error:{correlation_id or request_id or datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            redis.setex(key, 604800, json.dumps(error_data))  # 7 days
        except Exception as e:
            logger.warning(f"Failed to store error log (non-fatal): {e}")

