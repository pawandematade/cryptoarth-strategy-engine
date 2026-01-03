"""
Webhook Signal Service
Placeholder for webhook signal sending.

⚠️ DO NOT hardcode webhook URL
⚠️ Only create function & payload format
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def send_strategy_signal(payload: dict) -> Dict[str, Any]:
    """
    Placeholder webhook sender.
    Webhook URL & auth will be injected later.
    
    Payload FORMAT (LOCKED STRING KEYS):
    {
      "event": "STRATEGY_SIGNAL",
      "strategy_code": "STRG-XXXX",
      "strategy_name": "EMA 9/21",
      "symbol": "BTCUSD",
      "signal": "BUY",
      "timeframe": "5m",
      "price": 100000,
      "timestamp": "ISO",
      "execution_id": 123
    }
    
    Args:
        payload: Signal payload dictionary
    
    Returns:
        dict: Result with status and message
    """
    try:
        # Validate payload structure
        required_keys = ["event", "strategy_code", "strategy_name", "symbol", "signal", "timeframe", "price", "timestamp", "execution_id"]
        missing_keys = [key for key in required_keys if key not in payload]
        if missing_keys:
            logger.error(f"Missing required keys in webhook payload: {missing_keys}")
            return {
                "status": "error",
                "message": f"Missing required keys: {missing_keys}"
            }
        
        # TODO: Implement actual webhook HTTP request
        # This is a placeholder - webhook URL and auth will be injected later
        logger.info(f"Webhook signal (placeholder): {payload}")
        
        # Placeholder return
        return {
            "status": "success",
            "message": "Webhook signal queued (placeholder)",
            "payload": payload
        }
        
    except Exception as e:
        logger.error(f"Error sending webhook signal: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Webhook error: {str(e)}"
        }

