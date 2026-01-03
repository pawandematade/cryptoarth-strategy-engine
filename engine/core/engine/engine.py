import time
import logging
from common.redis import redis_client
from engine.strategies.loader import load_strategies

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

PRICE_KEY = "PRICE:BTCUSD"


def run_engine():
    """
    Strategy engine loop that evaluates strategies against current price.
    """
    # Load strategies once at startup
    strategies = load_strategies()
    logger.info(f"Loaded {len(strategies)} strategy(ies)")
    
    if not strategies:
        logger.warning("No strategies loaded. Engine will continue but won't process any strategies.")
    
    while True:
        # Read latest BTCUSD price from Redis
        try:
            price_str = redis_client.get(PRICE_KEY)
            if price_str is None:
                # Price not available, skip this iteration
                logger.debug("Price not available in Redis, waiting...")
                time.sleep(1)
                continue
            
            price = float(price_str)
        except (ValueError, TypeError) as e:
            # Invalid price value, skip this iteration
            logger.warning(f"Invalid price value in Redis: {price_str}, error: {e}")
            time.sleep(1)
            continue
        
        # Evaluate each strategy
        for strategy in strategies:
            # Only process BTCUSD strategies
            if strategy.get("symbol") != "BTCUSD":
                continue
            
            condition = strategy.get("condition", {})
            condition_type = condition.get("type")
            condition_value = condition.get("value")
            strategy_id = strategy.get("id")
            
            # Check price_above condition
            if condition_type == "price_above" and condition_value is not None:
                if price > condition_value:
                    # Store signal in Redis
                    signal_key = f"SIGNAL:{strategy_id}"
                    try:
                        redis_client.set(signal_key, "MATCHED")
                        logger.info(f"Strategy {strategy_id} MATCHED: Price {price} > {condition_value}")
                    except Exception as e:
                        logger.error(f"Failed to write signal to Redis for strategy {strategy_id}: {e}")
            else:
                logger.debug(f"Strategy {strategy_id}: Price {price}, Condition: {condition_type}={condition_value} (not matched)")
        
        # Sleep 1 second before next iteration
        time.sleep(1)


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Strategy Engine Starting")
    logger.info(f"Monitoring price key: {PRICE_KEY}")
    logger.info("=" * 50)
    run_engine()

