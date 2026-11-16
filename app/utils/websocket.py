from fastapi import WebSocket
from typing import Dict, List, Optional
import json
import asyncio
from app.core.cache import redis_client

class ConnectionManager:
    def __init__(self):
        # Maps trip_id (as a string) to a list of active WebSocket connections in this process
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Background tasks listening to Redis pubsub channels per room
        self.listener_tasks: Dict[str, asyncio.Task] = {}

    async def _redis_listener(self, room_id: str):
        """Background task that subscribes to the Redis telemetry channel for room_id and forwards to local websockets."""
        channel_name = f"trip:{room_id}:telemetry"
        pubsub = None
        try:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(channel_name)
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    data = msg.get("data")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    
                    # Forward to all local websockets connected to this room
                    connections = list(self.active_connections.get(room_id, []))
                    for ws in connections:
                        try:
                            await ws.send_text(data)
                        except Exception:
                            pass
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in Redis listener for room {room_id}: {e}")
        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe(channel_name)
                    await pubsub.close()
                except Exception:
                    pass

    async def connect(self, websocket: WebSocket, room_id: str):
        """Accepts a new WebSocket connection and adds it to the specified room."""
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
            # Start Redis listener task for this room if not already running
            task = asyncio.create_task(self._redis_listener(room_id))
            self.listener_tasks[room_id] = task

        self.active_connections[room_id].append(websocket)
        print(f"Client connected and added to room {room_id} (Local total: {len(self.active_connections[room_id])})")

    def disconnect(self, websocket: WebSocket, room_id: str):
        """Removes a WebSocket connection from a room and cleans up listeners if empty."""
        if room_id in self.active_connections and websocket in self.active_connections[room_id]:
            self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
                # Cancel the Redis listener for this room to avoid leaking resources
                task = self.listener_tasks.pop(room_id, None)
                if task and not task.done():
                    task.cancel()
        print(f"Client disconnected from room {room_id}")

    async def broadcast(self, message: dict, room_id: str):
        """
        Broadcasts a message by publishing it to Redis Pub/Sub channel.
        Also delivers locally immediately for sub-millisecond response.
        """
        message_str = json.dumps(message)
        channel_name = f"trip:{room_id}:telemetry"

        # 1. Publish to Redis so all other backend worker processes / containers receive it
        try:
            await redis_client.publish(channel_name, message_str)
        except Exception as e:
            print(f"Warning: Failed to publish message to Redis pub/sub channel {channel_name}: {e}")

        # 2. Also send directly to local connections in case Redis is bypassed or delayed
        # (listener will dedup or listener sends to local if pubsub only; direct send ensures instant local delivery)
        if room_id in self.active_connections:
            for connection in list(self.active_connections[room_id]):
                try:
                    await connection.send_text(message_str)
                except Exception:
                    pass

# Create a single, shared instance of the manager
manager = ConnectionManager()
