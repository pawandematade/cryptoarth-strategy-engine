import json
import time
import websocket
from threading import Thread
from app.store.redis_client import redis_client
from app.config import DELTA_BASE_URL
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Derive WebSocket URL from base URL (replace https://api with wss://socket)
DELTA_WS_URL = DELTA_BASE_URL.replace('https://api', 'wss://socket') if DELTA_BASE_URL else 'wss://socket.india.delta.exchange'

SYMBOL = 'BTCUSD'
PRICE_KEY = 'PRICE:BTCUSD'
HEARTBEAT_INTERVAL = 30  # seconds
RECONNECT_DELAY = 2  # seconds


def extract_price(ticker_data):
    """
    Extract latest traded price from ticker data.
    Priority: spot_price > mark_price > close
    """
    if ticker_data.get('spot_price'):
        return float(ticker_data['spot_price'])
    elif ticker_data.get('mark_price'):
        return float(ticker_data['mark_price'])
    elif ticker_data.get('close'):
        return float(ticker_data['close'])
    return None


def subscribe_to_ticker(ws):
    """Subscribe to BTCUSD ticker channel"""
    subscribe_msg = {
        'type': 'subscribe',
        'payload': {
            'channels': [
                {
                    'name': 'v2/ticker',
                    'symbols': [SYMBOL]
                }
            ]
        }
    }
    logger.info(f"Subscribing to {SYMBOL} ticker...")
    ws.send(json.dumps(subscribe_msg))


def on_message(ws, message):
    """Handle incoming WebSocket messages"""
    try:
        data = json.loads(message)
        
        # Handle pong response (heartbeat)
        if data.get('type') in ('pong', 'ping', 'heartbeat'):
            logger.debug(f"Heartbeat received: {data.get('type')}")
            return
        
        # Handle ticker updates
        if data.get('type') == 'v2/ticker' and data.get('symbol') == SYMBOL:
            price = extract_price(data)
            if price is not None:
                try:
                    redis_client.set(PRICE_KEY, str(price))
                    logger.info(f"Price update: {SYMBOL} = {price}")
                except Exception as e:
                    logger.error(f"Failed to write to Redis: {e}")
        else:
            logger.debug(f"Received message: {data.get('type', 'unknown')}")
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.warning(f"Error parsing message: {e}")


def on_error(ws, error):
    """Handle WebSocket errors"""
    logger.error(f"WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    """Handle WebSocket close and reconnect"""
    logger.warning(f"WebSocket closed. Status: {close_status_code}, Message: {close_msg}")
    logger.info(f"Reconnecting in {RECONNECT_DELAY} seconds...")
    time.sleep(RECONNECT_DELAY)
    connect_websocket()


def on_open(ws):
    """Handle WebSocket open - subscribe to ticker"""
    logger.info("WebSocket connection opened successfully")
    subscribe_to_ticker(ws)
    
    # Start heartbeat thread
    def heartbeat():
        while ws.sock and ws.sock.connected:
            try:
                ws.send(json.dumps({'type': 'ping'}))
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break
            time.sleep(HEARTBEAT_INTERVAL)
    
    Thread(target=heartbeat, daemon=True).start()


def connect_websocket():
    """Connect to Delta Exchange WebSocket"""
    logger.info(f"Connecting to WebSocket: {DELTA_WS_URL}")
    ws = websocket.WebSocketApp(
        DELTA_WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()


def run_price_feed():
    """Main function to run the Delta Exchange price feed"""
    logger.info("Starting Delta Exchange price feed...")
    while True:
        try:
            connect_websocket()
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            logger.info(f"Reconnecting in {RECONNECT_DELAY} seconds...")
            time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    # To start this live feed manually for testing:
    # python -m app.feed.delta_ws_live
    logger.info("=" * 50)
    logger.info("Delta Exchange WebSocket Price Feed")
    logger.info(f"Symbol: {SYMBOL}")
    logger.info(f"WebSocket URL: {DELTA_WS_URL}")
    logger.info("=" * 50)
    run_price_feed()

