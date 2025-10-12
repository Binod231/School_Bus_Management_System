from fastapi import WebSocket
from typing import Dict, List
import json

class ConnectionManager:
    def __init__(self):
        # Maps trip_id (as a string) to a list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        """Accepts a new WebSocket connection and adds it to the specified room."""
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)
        print(f"Client connected and added to room {room_id}")

    def disconnect(self, websocket: WebSocket, room_id: str):
        """Removes a WebSocket connection from a room."""
        if room_id in self.active_connections and websocket in self.active_connections[room_id]:
            self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
        print(f"Client disconnected from room {room_id}")

    async def broadcast(self, message: dict, room_id: str):
        """Broadcasts a JSON message to all clients in a specific room."""
        if room_id in self.active_connections:
            message_str = json.dumps(message)
            for connection in self.active_connections[room_id]:
                await connection.send_text(message_str)

# Create a single, shared instance of the manager
manager = ConnectionManager()