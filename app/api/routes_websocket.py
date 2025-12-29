"""
WebSocket endpoint for frontend to receive live price updates
Connects to Delta Exchange WebSocket and forwards data to connected clients
CLEAN IMPLEMENTATION: Start background task ONLY after first client connects
"""

import json
import asyncio
import logging
import threading
from typing import Set, Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from sqlalchemy import text
import websocket
from threading import Thread

from app.store.redis_client import redis_client
from app.config import DELTA_BASE_URL, IS_PRODUCTION, FRONTEND_URL
from app.database import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter()

# ===============================
# GLOBAL STATE
# ===============================

DELTA_WS_URL = (
    DELTA_BASE_URL.replace("https://api", "wss://socket")
    if DELTA_BASE_URL
    else "wss://socket.india.delta.exchange"
)

delta_ws = None
delta_ws_thread = None

subscribed_symbols: Set[str] = set()
price_broadcast_task_started = False
price_broadcast_lock = threading.Lock()

product_to_symbol: Dict[int, str] = {}
symbol_to_product: Dict[str, int] = {}
symbol_mapping_lock = threading.Lock()

GLOBAL_HEADER_PRODUCTS = {
    27: "BTCUSD",
    3136: "ETHUSD",
    14823: "SOLUSD",
}

delta_orderbook_required = False

# ===============================
# CONNECTION MANAGER
# ===============================

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.connection_subscriptions: Dict[WebSocket, Dict] = {}
        self.connection_loops: Dict[WebSocket, asyncio.AbstractEventLoop] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        self.connection_subscriptions[websocket] = {
            "product_ids": set(),
            "orderbook": False
        }
        self.connection_loops[websocket] = asyncio.get_event_loop()
        logger.info(f"✅ WS connected | total={len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        self.connection_subscriptions.pop(websocket, None)
        self.connection_loops.pop(websocket, None)
        logger.info(f"❌ WS disconnected | total={len(self.active_connections)}")

    def broadcast_ticker(self, message):
        self._broadcast(message)

    def broadcast_orderbook(self, message):
        self._broadcast(message, orderbook_only=True)

    def _broadcast(self, message, orderbook_only=False):
        if not self.active_connections:
            return

        msg = json.dumps(message)
        dead = []

        for ws in list(self.active_connections):
            try:
                subs = self.connection_subscriptions.get(ws)
                if not subs:
                    continue

                pid = message.get("product_id")
                if pid is None:
                    continue

                if str(pid) not in subs["product_ids"]:
                    continue

                if message.get("type") == "l1_orderbook" and not subs["orderbook"]:
                    continue

                if ws.client_state == WebSocketState.CONNECTED:
                    loop = self.connection_loops.get(ws)
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(ws.send_text(msg), loop)
                else:
                    dead.append(ws)

            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)


connection_manager = ConnectionManager()

# ===============================
# DELTA HANDLERS
# ===============================

def on_delta_message(ws, message):
    try:
        data = json.loads(message)
        if data.get("type") in ("ping", "pong", "heartbeat"):
            return

        symbol = data.get("symbol")
        if not symbol:
            return

        with symbol_mapping_lock:
            product_id = symbol_to_product.get(symbol)

        if product_id is None:
            return

        if data.get("type") == "v2/ticker":
            ltp = data.get("spot_price") or data.get("mark_price") or data.get("close")
            # ✅ FIX: Broadcast ticker even if ltp is 0 (use 'is not None' instead of truthy check)
            if ltp is not None:
                try:
                    redis_client.set(f"PRICE:{symbol}", str(ltp))
                except Exception as e:
                    logger.warning(f"Redis write failed: {e}")

                # ✅ FIX: Include ALL ticker fields (OHLC, Change %)
                connection_manager.broadcast_ticker({
                    "type": "ticker",
                    "symbol": symbol,
                    "product_id": product_id,
                    "ltp": float(ltp) if ltp is not None else None,
                    "open": float(data.get("open")) if data.get("open") is not None else None,
                    "high": float(data.get("high")) if data.get("high") is not None else None,
                    "low": float(data.get("low")) if data.get("low") is not None else None,
                    "close": float(data.get("close")) if data.get("close") is not None else None,
                    "mark_change_24h": float(data.get("mark_change_24h")) if data.get("mark_change_24h") is not None else None,
                })

        elif data.get("type") == "l1_orderbook":
            connection_manager.broadcast_orderbook({
                "type": "l1_orderbook",
                "symbol": symbol,
                "product_id": product_id,
                "best_bid": data.get("best_bid"),
                "best_ask": data.get("best_ask"),
            })

    except Exception as e:
        logger.warning(f"Delta parse error: {e}")


def subscribe_to_delta(ws, symbols: List[str], orderbook: bool):
    if not symbols:
        return

    channels = [{"name": "v2/ticker", "symbols": symbols}]

    if orderbook:
        channels.append({"name": "l1_orderbook", "symbols": symbols})

    payload = {
        "type": "subscribe",
        "payload": {
            "channels": channels
        },
    }

    ws.send(json.dumps(payload))

    # IMPORTANT: Update after sending (Delta allows duplicate subscribe safely)
    subscribed_symbols.update(symbols)

    logger.info(f"🚀 Delta subscribed symbols: {symbols}")


def connect_to_delta():
    global delta_ws, delta_ws_thread

    if delta_ws_thread and delta_ws_thread.is_alive():
        return

    def on_open(ws):
        logger.info("✅ Delta WS connected")

        # 🔥 AUTO subscribe to already requested symbols
        if subscribed_symbols:
            logger.info(f"🚀 Auto-subscribing on Delta connect: {list(subscribed_symbols)}")
            subscribe_to_delta(ws, list(subscribed_symbols), delta_orderbook_required)

    delta_ws = websocket.WebSocketApp(
        DELTA_WS_URL,
        on_open=on_open,
        on_message=on_delta_message,
    )

    def run():
        delta_ws.run_forever()

    delta_ws_thread = Thread(target=run, daemon=True)
    delta_ws_thread.start()
    logger.info("✅ Delta WS thread started")


def start_price_broadcast_if_needed():
    global price_broadcast_task_started
    with price_broadcast_lock:
        if not price_broadcast_task_started:
            price_broadcast_task_started = True
            connect_to_delta()

# ===============================
# DB SYMBOL MAPPING
# ===============================

def get_symbol_mapping(product_ids: List[int]) -> Dict[int, str]:
    if not product_ids:
        return {}

    db = SessionLocal()
    mapping = {}

    try:
        ids = ",".join(map(str, product_ids))
        res = db.execute(
            text(f"SELECT symbolid, symbol FROM authenticate_symbolmaster WHERE symbolid IN ({ids})")
        )
        for r in res:
            mapping[int(r[0])] = r[1]

    finally:
        db.close()

    return mapping

# ===============================
# WEBSOCKET ENDPOINT
# ===============================

@router.websocket("/ws/live-prices")
async def websocket_endpoint(websocket: WebSocket):

    await connection_manager.connect(websocket)
    start_price_broadcast_if_needed()

    try:
        await websocket.send_json({"type": "connected"})

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1)
                message = json.loads(data)

                # ===============================
                # SUBSCRIBE (FINAL & ONLY)
                # ===============================
                if message.get("type") == "subscribe":

                    if "channels" in message:
                        logger.warning("❌ Legacy subscribe ignored")
                        continue

                    # ✅ FIX: Handle product_ids from frontend subscribe message
                    product_ids = message.get("product_ids", [])
                    if not product_ids:
                        # Fallback to symbols for backward compatibility
                        symbols = message.get("symbols", [])
                        if isinstance(symbols, (int, str)):
                            symbols = [symbols]
                        product_ids = [
                            int(s) for s in symbols
                            if isinstance(s, int) or (isinstance(s, str) and s.isdigit())
                        ]

                    if not product_ids:
                        logger.warning(f"❌ Subscribe message missing product_ids: {message}")
                        continue

                    logger.info(f"📥 Subscribe received: product_ids={product_ids}")

                    # Global Header FIX: use hardcoded symbols (no DB call)
                    delta_symbols = []
                    mapping = {}

                    for pid in product_ids:
                        if pid in GLOBAL_HEADER_PRODUCTS:
                            symbol = GLOBAL_HEADER_PRODUCTS[pid]
                            mapping[pid] = symbol
                            delta_symbols.append(symbol)

                    # Fallback to DB for non-header products (copy trade, etc.)
                    missing_pids = [pid for pid in product_ids if pid not in mapping]

                    if missing_pids:
                        db_mapping = get_symbol_mapping(missing_pids)
                        mapping.update(db_mapping)
                        delta_symbols.extend(db_mapping.values())

                    if not delta_symbols:
                        logger.warning(f"❌ No symbols found for product_ids: {product_ids}")
                        continue

                    # Update symbol maps
                    with symbol_mapping_lock:
                        product_to_symbol.update(mapping)
                        symbol_to_product.update({v: k for k, v in mapping.items()})

                    # Store subscriptions for this connection
                    connection_manager.connection_subscriptions[websocket]["product_ids"].update(
                        [str(pid) for pid in product_ids]
                    )
                    
                    # Enable orderbook ONLY if explicitly requested
                    global delta_orderbook_required
                    if message.get("orderbook") is True:
                        connection_manager.connection_subscriptions[websocket]["orderbook"] = True
                        delta_orderbook_required = True

                    # Send confirmation to frontend
                    await websocket.send_json({
                        "type": "subscribed",
                        "product_ids": product_ids,
                        "symbols": delta_symbols,
                    })

                    # Subscribe to Delta for new symbols
                    need_orderbook = message.get("orderbook") is True

                    start_price_broadcast_if_needed()
                    await asyncio.sleep(0.5)

                    if delta_ws:
                        subscribe_to_delta(delta_ws, delta_symbols, need_orderbook)
                    else:
                        logger.warning("❌ Delta WebSocket not available, retrying connection...")
                        connect_to_delta()
                        await asyncio.sleep(1)
                        if delta_ws:
                            subscribe_to_delta(delta_ws, delta_symbols, need_orderbook)

            except asyncio.TimeoutError:
                continue

    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect(websocket)
