from fastapi import APIRouter
from app.store.redis_client import redis_client

router = APIRouter()


@router.get("/signals/{strategy_id}")
def get_signal(strategy_id: int):
    """
    Get signal for a specific strategy from Redis.
    
    Returns:
        dict: JSON with strategy_id and signal (value or null)
    """
    signal_key = f"SIGNAL:{strategy_id}"
    
    try:
        signal = redis_client.get(signal_key)
        return {
            "strategy_id": strategy_id,
            "signal": signal if signal is not None else None
        }
    except Exception:
        # Return null signal if Redis read fails
        return {
            "strategy_id": strategy_id,
            "signal": None
        }

