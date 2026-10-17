from dataclasses import dataclass

from fastapi import WebSocket


@dataclass
class ConnectionState:
    pass


class WSConnectionManager:
    def __init__(self):
        self.connections: dict[int, dict[WebSocket, ConnectionState]] = {}

    async def register(self, user_id: int, websocket: WebSocket):
        """Register a ws-connection"""
        self.connections.setdefault(user_id, {})[websocket] = ConnectionState()

    async def unregister(self, user_id: int, websocket: WebSocket):
        """Unregister a ws-connection"""
        try:
            self.connections[user_id].pop(websocket)
        except KeyError:
            return
