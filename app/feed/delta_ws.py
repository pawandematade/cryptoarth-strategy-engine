import time
import random
from app.store.redis_client import redis_client

# Initial price for BTC/USD
INITIAL_PRICE = 90000.0
PRICE_KEY = "PRICE:BTCUSD"


def run_price_feed():
    """
    Dummy price feed that simulates BTC/USD price using random walk.
    Updates price every second and writes to Redis.
    """
    price = INITIAL_PRICE
    
    while True:
        # Random walk: small random change (between -0.5% and +0.5%)
        change_percent = random.uniform(-0.005, 0.005)
        price = price * (1 + change_percent)
        
        # Write to Redis
        try:
            redis_client.set(PRICE_KEY, str(price))
        except Exception:
            # Silently continue if Redis write fails
            pass
        
        # Wait 1 second before next update
        time.sleep(1)


if __name__ == "__main__":
    # To start this dummy feed manually for testing:
    # python -m app.feed.delta_ws
    run_price_feed()

