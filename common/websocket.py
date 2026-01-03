"""
Single WebSocket Manager - ONE SOURCE OF TRUTH
All WebSocket connections managed here.
Engine publishes, Frontend subscribes.
"""
import logging
from typing import Dict, Set
from fastapi import WebSocket
from fastapi.websockets import WebSocketState

logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    Single WebSocket connection manager.
    Manages all active WebSocket connections.
    """
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, room: str = "default"):
        """Connect a WebSocket to a room"""
        await websocket.accept()
        if room not in self.active_connections:
            self.active_connections[room] = set()
        self.active_connections[room].add(websocket)
        logger.info(f"WebSocket connected to room: {room}")
    
    async def disconnect(self, websocket: WebSocket, room: str = "default"):
        """Disconnect a WebSocket from a room"""
        if room in self.active_connections:
            self.active_connections[room].discard(websocket)
            if not self.active_connections[room]:
                del self.active_connections[room]
        logger.info(f"WebSocket disconnected from room: {room}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send message to a single WebSocket"""
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send personal message: {e}")
    
    async def broadcast_to_room(self, message: str, room: str = "default"):
        """Broadcast message to all connections in a room"""
        if room not in self.active_connections:
            return
        
        disconnected = set()
        for websocket in self.active_connections[room]:
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.send_text(message)
                except Exception as e:
                    logger.warning(f"Failed to broadcast to room {room}: {e}")
                    disconnected.add(websocket)
            else:
                disconnected.add(websocket)
        
        # Clean up disconnected sockets
        for ws in disconnected:
            self.active_connections[room].discard(ws)
    
    async def broadcast(self, message: str):
        """Broadcast message to all connections in all rooms"""
        for room in list(self.active_connections.keys()):
            await self.broadcast_to_room(message, room)

# Single global instance - ONE WEBSOCKET MANAGER
websocket_manager = WebSocketManager()

