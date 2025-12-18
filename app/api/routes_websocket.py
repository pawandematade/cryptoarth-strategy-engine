"""
WebSocket endpoint for frontend to receive live price updates
Connects to Delta Exchange WebSocket and forwards data to connected clients
"""
import json
import asyncio
import logging
from typing import Set, Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.store.redis_client import redis_client
from app.config import DELTA_BASE_URL
import websocket
from threading import Thread

logger = logging.getLogger(__name__)

router = APIRouter()

# Derive WebSocket URL from base URL
DELTA_WS_URL = DELTA_BASE_URL.replace('https://api', 'wss://socket') if DELTA_BASE_URL else 'wss://socket.india.delta.exchange'

# Store active WebSocket connections
active_connections: Set[WebSocket] = set()

# Store subscribed symbols per connection
connection_subscriptions: Dict[WebSocket, Set[str]] = {}

# Store event loops for each connection (for thread-safe broadcasting)
connection_loops: Dict[WebSocket, asyncio.AbstractEventLoop] = {}

# Global Delta Exchange WebSocket connection
delta_ws = None
delta_ws_thread = None
subscribed_symbols: Set[str] = set()


def broadcast_to_clients(message: dict):
    """Broadcast message to all connected clients (thread-safe)"""
    if not active_connections:
        return
    
    message_str = json.dumps(message)
    disconnected = set()
    
    for connection in active_connections:
        try:
            # Check if connection is subscribed to this symbol
            conn_subs = connection_subscriptions.get(connection, set())
            symbol = message.get('symbol') or message.get('product_id')
            
            # Send to all if no subscriptions, or if subscribed to this symbol
            if not conn_subs or symbol in conn_subs:
                # Get event loop for this connection
                loop = connection_loops.get(connection)
                if loop and loop.is_running():
                    # Schedule coroutine in the connection's event loop
                    asyncio.run_coroutine_threadsafe(
                        connection.send_text(message_str),
                        loop
                    )
        except Exception as e:
            logger.error(f"Error sending message to client: {e}")
            disconnected.add(connection)
    
    # Remove disconnected connections
    for conn in disconnected:
        active_connections.discard(conn)
        connection_subscriptions.pop(conn, None)
        connection_loops.pop(conn, None)


def on_delta_message(ws, message):
    """Handle messages from Delta Exchange WebSocket"""
    try:
        data = json.loads(message)
        
        # Handle pong response (heartbeat)
        if data.get('type') in ('pong', 'ping', 'heartbeat'):
            return
        
        # Handle ticker updates
        if data.get('type') == 'v2/ticker':
            symbol = data.get('symbol')
            if symbol:
                # Extract price data
                price_data = {
                    'type': 'ticker',
                    'symbol': symbol,
                    'product_id': data.get('product_id'),
                    'spot_price': data.get('spot_price'),
                    'mark_price': data.get('mark_price'),
                    'close': data.get('close'),
                    'open': data.get('open'),
                    'high': data.get('high'),
                    'low': data.get('low'),
                    'volume': data.get('volume'),
                    'timestamp': data.get('timestamp')
                }
                
                # Store in Redis
                try:
                    price = data.get('spot_price') or data.get('mark_price') or data.get('close')
                    if price:
                        redis_client.set(f'PRICE:{symbol}', str(price))
                except Exception as e:
                    logger.error(f"Failed to write to Redis: {e}")
                
                # Broadcast to all connected clients
                broadcast_to_clients(price_data)
        
        # Handle other message types (L2 orderbook, trades, etc.)
        elif data.get('type'):
            # Forward other message types as well
            broadcast_to_clients(data)
            
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.warning(f"Error parsing Delta message: {e}")


def on_delta_error(ws, error):
    """Handle Delta WebSocket errors"""
    logger.error(f"Delta WebSocket error: {error}")


def on_delta_close(ws, close_status_code, close_msg):
    """Handle Delta WebSocket close and reconnect"""
    logger.warning(f"Delta WebSocket closed. Status: {close_status_code}, Message: {close_msg}")
    logger.info("Reconnecting to Delta Exchange in 2 seconds...")
    import time
    time.sleep(2)
    connect_to_delta()


def on_delta_open(ws):
    """Handle Delta WebSocket open - subscribe to symbols"""
    logger.info("Delta WebSocket connection opened successfully")
    
    # Subscribe to all currently subscribed symbols
    if subscribed_symbols:
        subscribe_to_symbols(ws, list(subscribed_symbols))


def subscribe_to_delta(ws, symbols: List[str]):
    """Subscribe to symbols on Delta Exchange WebSocket"""
    if not symbols:
        return
    
    subscribe_msg = {
        'type': 'subscribe',
        'payload': {
            'channels': [
                {
                    'name': 'v2/ticker',
                    'symbols': symbols
                }
            ]
        }
    }
    
    try:
        ws.send(json.dumps(subscribe_msg))
        logger.info(f"Subscribed to Delta Exchange symbols: {symbols}")
        subscribed_symbols.update(symbols)
    except Exception as e:
        logger.error(f"Error subscribing to Delta Exchange: {e}")


def subscribe_to_symbols(ws, symbols: List[str]):
    """Helper to subscribe to symbols"""
    subscribe_to_delta(ws, symbols)


def connect_to_delta():
    """Connect to Delta Exchange WebSocket"""
    global delta_ws
    
    logger.info(f"Connecting to Delta Exchange WebSocket: {DELTA_WS_URL}")
    
    try:
        delta_ws = websocket.WebSocketApp(
            DELTA_WS_URL,
            on_open=on_delta_open,
            on_message=on_delta_message,
            on_error=on_delta_error,
            on_close=on_delta_close
        )
        
        # Run in a separate thread
        def run_ws():
            delta_ws.run_forever()
        
        global delta_ws_thread
        if delta_ws_thread and delta_ws_thread.is_alive():
            return
        
        delta_ws_thread = Thread(target=run_ws, daemon=True)
        delta_ws_thread.start()
        logger.info("Delta WebSocket thread started")
        
    except Exception as e:
        logger.error(f"Error connecting to Delta Exchange: {e}")


# Start Delta Exchange connection on module load
connect_to_delta()


@router.websocket("/ws/live-prices")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for frontend to receive live price updates
    Frontend can subscribe to specific symbols
    """
    await websocket.accept()
    active_connections.add(websocket)
    connection_subscriptions[websocket] = set()
    connection_loops[websocket] = asyncio.get_event_loop()
    
    logger.info(f"Client connected. Total connections: {len(active_connections)}")
    
    try:
        # Send welcome message
        await websocket.send_json({
            'type': 'connected',
            'message': 'Connected to live price feed',
            'delta_ws_url': DELTA_WS_URL
        })
        
        while True:
            # Receive messages from client (subscriptions, etc.)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                try:
                    message = json.loads(data)
                    
                    # Handle subscription requests
                    if message.get('type') == 'subscribe':
                        symbols = message.get('symbols', [])
                        if isinstance(symbols, str):
                            symbols = [symbols]
                        
                        # Add to connection subscriptions
                        connection_subscriptions[websocket].update(symbols)
                        
                        # Subscribe to Delta Exchange if not already subscribed
                        new_symbols = [s for s in symbols if s not in subscribed_symbols]
                        if new_symbols and delta_ws and delta_ws.sock and delta_ws.sock.connected:
                            subscribe_to_delta(delta_ws, new_symbols)
                        
                        await websocket.send_json({
                            'type': 'subscribed',
                            'symbols': list(connection_subscriptions[websocket])
                        })
                    
                    # Handle unsubscribe requests
                    elif message.get('type') == 'unsubscribe':
                        symbols = message.get('symbols', [])
                        if isinstance(symbols, str):
                            symbols = [symbols]
                        
                        connection_subscriptions[websocket].difference_update(symbols)
                        await websocket.send_json({
                            'type': 'unsubscribed',
                            'symbols': list(connection_subscriptions[websocket])
                        })
                    
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from client: {data}")
            
            except asyncio.TimeoutError:
                # Timeout is expected - continue loop
                continue
            
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Cleanup
        active_connections.discard(websocket)
        connection_subscriptions.pop(websocket, None)
        connection_loops.pop(websocket, None)
        logger.info(f"Client removed. Total connections: {len(active_connections)}")

