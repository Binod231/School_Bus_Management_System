# school_bus_management/app/utils/websocket.py
from typing import List, Dict
from fastapi import WebSocket
import json

class ConnectionManager:
    def __init__(self):
        # Maps user_id (as string) to a list of their active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        if client_id not in self.active_connections:
            self.active_connections[client_id] = []
        self.active_connections[client_id].append(websocket)

    def disconnect(self, websocket: WebSocket, client_id: str):
        if client_id in self.active_connections:
            self.active_connections[client_id].remove(websocket)
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]

    async def broadcast(self, message: dict, client_ids: List[str]):
        message_str = json.dumps(message)
        for client_id in client_ids:
            if client_id in self.active_connections:
                for connection in self.active_connections[client_id]:
                    await connection.send_text(message_str)

manager = ConnectionManager()