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
        
        # Handle pong response (heartbeat) from Delta Exchange
        if data.get('type') in ('pong', 'ping', 'heartbeat'):
            return
        
        # Handle ticker updates
        if data.get('type') == 'v2/ticker':
            symbol = data.get('symbol')
            if symbol:
                # Extract all available price data from Delta Exchange ticker
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
                    'timestamp': data.get('timestamp'),
                    'mark_change_24h': data.get('mark_change_24h'),
                    'ltp_change_24h': data.get('ltp_change_24h'),
                    'tick_size': data.get('tick_size'),
                    'contract_multiplier': data.get('contract_multiplier'),
                    # Extract best bid/ask from quotes if available
                    'best_bid': data.get('quotes', {}).get('best_bid') if isinstance(data.get('quotes'), dict) else data.get('best_bid'),
                    'bid_size': data.get('quotes', {}).get('bid_size') if isinstance(data.get('quotes'), dict) else data.get('bid_size'),
                    'best_ask': data.get('quotes', {}).get('best_ask') if isinstance(data.get('quotes'), dict) else data.get('best_ask'),
                    'ask_size': data.get('quotes', {}).get('ask_size') if isinstance(data.get('quotes'), dict) else data.get('ask_size'),
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
        
        # Handle L1 orderbook updates (for best bid/ask)
        elif data.get('type') == 'l1_orderbook':
            symbol = data.get('symbol')
            if symbol:
                orderbook_data = {
                    'type': 'l1_orderbook',
                    'symbol': symbol,
                    'best_bid': data.get('best_bid'),
                    'bid_qty': data.get('bid_qty'),
                    'best_ask': data.get('best_ask'),
                    'ask_qty': data.get('ask_qty'),
                    'timestamp': data.get('timestamp')
                }
                broadcast_to_clients(orderbook_data)
        
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
    logger.info("✅ Delta WebSocket connection opened successfully")
    
    # Re-subscribe to ALL previously subscribed symbols (including defaults and user-requested)
    # This ensures prices continue flowing after reconnection
    if subscribed_symbols:
        symbols_list = list(subscribed_symbols)
        logger.info(f"Re-subscribing to {len(symbols_list)} symbols on Delta WebSocket reconnect: {symbols_list}")
        subscribe_to_symbols(ws, symbols_list)
    else:
        # First time connection - subscribe to default symbols
        default_symbols = ['BTCUSD', 'ETHUSD']
        logger.info(f"Auto-subscribing to default symbols: {default_symbols}")
        subscribe_to_symbols(ws, default_symbols)
        subscribed_symbols.update(default_symbols)


def subscribe_to_delta(ws, symbols: List[str]):
    """Subscribe to symbols on Delta Exchange WebSocket - IMMEDIATE subscription"""
    if not symbols:
        return
    
    subscribe_msg = {
        'type': 'subscribe',
        'payload': {
            'channels': [
                {
                    'name': 'v2/ticker',
                    'symbols': symbols
                },
                {
                    'name': 'l1_orderbook',
                    'symbols': symbols
                }
            ]
        }
    }
    
    try:
        # Send subscription IMMEDIATELY - no delay
        ws.send(json.dumps(subscribe_msg))
        logger.info(f"✅ Immediately subscribed to Delta Exchange symbols: {symbols}")
        subscribed_symbols.update(symbols)
    except Exception as e:
        logger.error(f"❌ Error subscribing to Delta Exchange: {e}")
        # Retry once after a very short delay
        import time
        time.sleep(0.1)
        try:
            ws.send(json.dumps(subscribe_msg))
            logger.info(f"✅ Retry subscription successful for symbols: {symbols}")
            subscribed_symbols.update(symbols)
        except Exception as retry_error:
            logger.error(f"❌ Retry subscription failed: {retry_error}")


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


# Auto-subscribe to default symbols for live prices
DEFAULT_SYMBOLS = ['BTCUSD', 'ETHUSD']

# Start Delta Exchange connection on module load - IMMEDIATE connection
connect_to_delta()

# Auto-subscribe to default symbols IMMEDIATELY (connection handles subscription in on_open)
# No need for separate thread - subscription happens in on_delta_open callback


@router.websocket("/ws/live-prices")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for frontend to receive live price updates.
    
    CRITICAL: This endpoint is PUBLIC - no authentication required.
    Live market prices are public data and do not require user authentication.
    
    This endpoint explicitly bypasses all authentication checks.
    Frontend can subscribe to specific symbols to receive real-time price updates.
    """
    from app.config import IS_PRODUCTION, FRONTEND_URL
    
    # Get origin from headers
    origin = websocket.headers.get("origin") or websocket.headers.get("Origin")
    logger.info(f"🔌 WebSocket connection attempt from origin: {origin} (PUBLIC endpoint - NO AUTH REQUIRED)")
    
    # Allowed origins for WebSocket (same as CORS)
    if IS_PRODUCTION:
        allowed_origins = [
            FRONTEND_URL,
            "https://aistrategy.cryptoarth.in",
            "https://cryptoarth.in",
            "https://panel.cryptoarth.in",
            "https://trade-panel.cryptoarth.in",
            "https://www.trade-panel.cryptoarth.in",
        ]
        allowed_origins = list(set(filter(None, allowed_origins)))
    else:
        # Development: Allow ALL localhost origins (very permissive)
        allowed_origins = [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:8000",  # Backend origin
            "http://localhost:8000",  # Backend origin
            FRONTEND_URL,
        ]
        # In development, also allow any localhost/127.0.0.1 origin
        allowed_origins = list(set(filter(None, allowed_origins)))
    
    # Validate origin for WebSocket (CORS doesn't apply to WebSocket, need manual check)
    # In development, be more permissive - allow any localhost origin
    if origin:
        # Normalize origin (remove trailing slash)
        origin_clean = origin.rstrip('/')
        allowed_origins_clean = [o.rstrip('/') for o in allowed_origins]
        
        # Check if origin is allowed
        if origin_clean not in allowed_origins_clean:
            # Also check if origin matches any allowed origin (case-insensitive for scheme)
            origin_lower = origin_clean.lower()
            is_allowed = any(
                allowed.lower() == origin_lower or 
                origin_clean.startswith(allowed.rstrip('/')) or
                allowed.rstrip('/').startswith(origin_clean)
                for allowed in allowed_origins
            )
            
            # In development, also allow any localhost/127.0.0.1 origin
            if not IS_PRODUCTION:
                if 'localhost' in origin_lower or '127.0.0.1' in origin_lower:
                    is_allowed = True
                    logger.info(f"✅ Development mode: Allowing localhost origin: {origin}")
            
            if not is_allowed:
                logger.warning(f"❌ WebSocket connection rejected: origin '{origin}' not in allowed list")
                logger.warning(f"   Allowed origins: {allowed_origins}")
                await websocket.close(code=1008, reason="Origin not allowed")
                return
    else:
        # No origin header - in development, allow it
        if not IS_PRODUCTION:
            logger.info("⚠️  No origin header, but allowing in development mode")
        else:
            logger.warning("❌ WebSocket connection rejected: No origin header in production")
            await websocket.close(code=1008, reason="Origin required")
            return
    
    # CRITICAL: Accept WebSocket connection WITHOUT any authentication
    # This endpoint is PUBLIC - no token, no user check, no permission check
    try:
        await websocket.accept()
        active_connections.add(websocket)
        connection_subscriptions[websocket] = set()
        connection_loops[websocket] = asyncio.get_event_loop()
        
        logger.info(f"✅ WebSocket connection ACCEPTED (PUBLIC - NO AUTH). Origin: {origin}. Total connections: {len(active_connections)}")
    except Exception as e:
        logger.error(f"❌ Error accepting WebSocket connection: {e}")
        logger.error(f"   This should NOT happen - endpoint is PUBLIC")
        raise
    
    try:
        # Send welcome message
        await websocket.send_json({
            'type': 'connected',
            'message': 'Connected to live price feed',
            'delta_ws_url': DELTA_WS_URL
        })
        
        while True:
            # Receive messages from client (subscriptions, heartbeat, etc.)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                try:
                    message = json.loads(data)
                    
                    # Handle ping requests from frontend - respond with pong immediately
                    if message.get('type') == 'ping':
                        await websocket.send_json({'type': 'pong'})
                        logger.debug("Responded to ping with pong")
                        continue
                    
                    # Handle subscription requests
                    if message.get('type') == 'subscribe':
                        symbols = message.get('symbols', [])
                        if isinstance(symbols, str):
                            symbols = [symbols]
                        
                        # Add to connection subscriptions immediately
                        connection_subscriptions[websocket].update(symbols)
                        
                        # Subscribe to Delta Exchange if not already subscribed
                        new_symbols = [s for s in symbols if s not in subscribed_symbols]
                        if new_symbols:
                            # Add to subscribed symbols immediately
                            subscribed_symbols.update(new_symbols)
                            
                            # Subscribe to Delta Exchange if connected - IMMEDIATE subscription
                            if delta_ws:
                                try:
                                    # Check if WebSocket is connected (websocket-client uses sock property)
                                    if hasattr(delta_ws, 'sock') and delta_ws.sock:
                                        # Check if socket is actually connected
                                        import socket
                                        try:
                                            # Try to get socket state
                                            if delta_ws.sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0:
                                                # IMMEDIATELY subscribe - no delay
                                                subscribe_to_delta(delta_ws, new_symbols)
                                                logger.info(f"✅ Immediately subscribed to new symbols: {new_symbols}")
                                            else:
                                                # Socket exists but not connected, wait for reconnection
                                                logger.warning(f"Delta WebSocket not connected, will subscribe when reconnected: {new_symbols}")
                                        except:
                                            # Socket might be in transition, try subscribing anyway
                                            try:
                                                subscribe_to_delta(delta_ws, new_symbols)
                                                logger.info(f"✅ Subscribed to symbols (socket in transition): {new_symbols}")
                                            except Exception as sub_error:
                                                logger.warning(f"Delta WebSocket in transition, will subscribe when reconnected: {new_symbols}, error: {sub_error}")
                                    else:
                                        # WebSocket not initialized yet, will subscribe when connected
                                        logger.info(f"Delta WebSocket not initialized, will subscribe when connected: {new_symbols}")
                                except Exception as e:
                                    logger.error(f"Error checking Delta WebSocket connection: {e}")
                                    # Still add to subscribed symbols, will subscribe when connected
                        
                        # Send confirmation immediately
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

