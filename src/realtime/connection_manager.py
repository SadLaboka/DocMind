from dataclasses import dataclass

from fastapi import WebSocket
from structlog import get_logger

logger = get_logger(__name__)


@dataclass
class ConnectionState:
    pass


class WSConnectionManager:
    def __init__(self):
        self.connections: dict[int, dict[WebSocket, ConnectionState]] = {}

    async def register(self, user_id: int, websocket: WebSocket):
        """Register a ws-connection"""

        for user in self.connections:
            if self.connections[user].get(websocket, None) is not None and user != user_id:
                logger.warning(
                    "Ws-connection already registered for another user",
                    current_user_id=user_id,
                    registered_for_user_id=user,
                    websocket_id=id(websocket),
                )
                raise ValueError(
                    "Ws-connection already registered for another user",
                )

        user_connections = self.connections.setdefault(user_id, {})

        if user_connections.get(websocket) is None:
            user_connections[websocket] = ConnectionState()

    async def unregister(self, user_id: int, websocket: WebSocket):
        """Unregister a ws-connection"""
        try:

            self.connections[user_id].pop(websocket)
        except KeyError:
            return

        if len(self.connections[user_id]) == 0:
            self.connections.pop(user_id)
