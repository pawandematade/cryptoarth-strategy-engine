"""
API Request/Response Audit Logging
Logs all API requests and responses with metadata
"""
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from common.redis import get_redis

logger = logging.getLogger(__name__)

def log_api_request(
    request_id: str,
    method: str,
    path: str,
    user_id: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None
):
    """
    Log API request
    Stores in Redis if available, logs to file otherwise
    """
    log_data = {
        "type": "api_request",
        "request_id": request_id,
        "method": method,
        "path": path,
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat(),
        "headers": headers,
        "body": body
    }
    
    logger.info(f"API Request: {method} {path} [request_id={request_id}]")
    
    redis = get_redis()
    if redis:
        try:
            key = f"audit:api:{request_id}"
            redis.setex(key, 86400, json.dumps(log_data))  # 24 hours
        except Exception as e:
            logger.warning(f"Failed to store API request log (non-fatal): {e}")

def log_api_response(
    request_id: str,
    status_code: int,
    response_body: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[float] = None
):
    """
    Log API response
    """
    log_data = {
        "type": "api_response",
        "request_id": request_id,
        "status_code": status_code,
        "response_body": response_body,
        "duration_ms": duration_ms,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.info(f"API Response: {status_code} [request_id={request_id}, duration={duration_ms}ms]")
    
    redis = get_redis()
    if redis:
        try:
            key = f"audit:api:{request_id}:response"
            redis.setex(key, 86400, json.dumps(log_data))
        except Exception as e:
            logger.warning(f"Failed to store API response log (non-fatal): {e}")

