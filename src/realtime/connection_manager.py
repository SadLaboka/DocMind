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

        logger.info(
            "Try registering ws-connection",
            user_id=user_id,
            websocket_id=id(websocket),
        )

        user_connections = self.connections.setdefault(user_id, {})

        for user in self.connections:
            if self.connections[user].get(websocket, None) is not None and user != user_id:
                logger.warning(
                    "Ws-connection already registered for another user",
                    current_user_id=user_id,
                    registered_for_user_id=user,
                    websocket_id=id(websocket),
                )
                return

        if user_connections.get(websocket) is None:
            user_connections[websocket] = ConnectionState()

            logger.info(
                "Ws-connection registered",
                user_id=user_id,
                websocket_id=id(websocket),
            )
        else:
            logger.warning(
                "Ws-connection already registered",
                user_id=user_id,
                websocket_id=id(websocket),
            )

    async def unregister(self, user_id: int, websocket: WebSocket):
        """Unregister a ws-connection"""
        try:

            logger.info(
                "Try unregistering ws-connection",
                user_id=user_id,
                websocket_id=id(websocket),
            )

            self.connections[user_id].pop(websocket)
        except KeyError:

            logger.warning(
                "Ws-connection already unregistered",
                user_id=user_id,
                websocket_id=id(websocket),
            )

            return

        logger.info(
            "Ws-connection unregistered",
            user_id=user_id,
            websocket_id=id(websocket),
        )

        if len(self.connections[user_id]) == 0:
            self.connections.pop(user_id)
