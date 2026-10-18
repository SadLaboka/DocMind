import asyncio
from dataclasses import dataclass, field

from fastapi import WebSocket
from structlog import get_logger

from src.schemas.ws_messages import Ready, SyncRequired, DocumentStatusChanged, AnalysisStatusChanged

logger = get_logger(__name__)


@dataclass
class ConnectionState:
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    closing: bool = False


class WSConnectionManager:
    def __init__(self):
        self.connections: dict[int, dict[WebSocket, ConnectionState]] = {}

    async def register(self, user_id: int, websocket: WebSocket) -> None:
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

    async def send_to_user(
            self,
            user_id: int,
            event: Ready | SyncRequired | DocumentStatusChanged | AnalysisStatusChanged
    ) -> None:
        """Send event to user in his ws-connections"""

        if not self.connections.get(user_id):
            return

        json_event = event.model_dump(mode="json")

        for ws, state in self.connections[user_id].items():
            if not state.closing:
                async with state.send_lock:
                    await ws.send_json(json_event)

    async def unregister(self, user_id: int, websocket: WebSocket) -> None:
        """Unregister a ws-connection"""

        try:
            self.connections[user_id][websocket].closing = True
            self.connections[user_id].pop(websocket)
        except KeyError:
            return

        if len(self.connections[user_id]) == 0:
            self.connections.pop(user_id)
