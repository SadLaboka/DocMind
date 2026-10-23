import asyncio
from dataclasses import dataclass, field

from fastapi import WebSocket
from structlog import get_logger

from src.schemas.ws_messages import SyncRequired, DocumentStatusChanged, AnalysisStatusChanged

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
            event: SyncRequired | DocumentStatusChanged | AnalysisStatusChanged
    ) -> None:
        """Send event to user in his ws-connections"""

        user_connections = self.connections.get(user_id)

        if not user_connections:
            return

        json_event = event.model_dump_json()

        await asyncio.gather(
            *(self._send_one(json_event, event.type, user_id, ws, state) for ws, state in user_connections.items()))

    async def _send_one(
            self,
            event: str,
            event_type: str,
            user_id: int,
            ws: WebSocket,
            state: ConnectionState,
    ) -> None:
        """Send event-message to one ws-connection"""
        unregister_necessary = False

        async with state.send_lock:

            if not state.closing:
                try:
                    await asyncio.wait_for(ws.send_text(event), 5)
                except asyncio.TimeoutError:
                    logger.warning(
                        "Ws-connection timed out",
                        user_id=user_id,
                        websocket_id=id(ws),
                        event_type=event_type,
                    )
                    unregister_necessary = True
                    state.closing = True
                except Exception as e:
                    logger.warning(
                        "Ws-connection failed",
                        user_id=user_id,
                        websocket_id=id(ws),
                        error_msg=str(e),
                        error_type=type(e).__name__,
                        event_type=event_type,
                    )
                    unregister_necessary = True
                    state.closing = True
                except asyncio.CancelledError:
                    logger.info(
                        "Calling code cancelled. Ws-connection will close",
                        user_id=user_id,
                        websocket_id=id(ws),
                        event_type=event_type,
                    )
                    state.closing = True
                    await self._close_ws(ws, user_id)
                    raise

            if unregister_necessary:
               await self._close_ws(ws, user_id)

    async def close_user(self, user_id: int) -> None:
        """Close all user ws-connections"""

        logger.info(
            "Closing all user ws-connections",
            user_id=user_id,
        )

        user_connections = self.connections.get(user_id)
        if not user_connections:
            return

        for connection, state in list(user_connections.items()):
            if not state.closing:
                state.closing = True
                async with state.send_lock:
                    await self._close_ws(connection, user_id)

    async def _close_ws(self, ws: WebSocket, user_id: int, code: int | None = None) -> None:
        """Close the ws-connection"""
        try:
            if code:
                await asyncio.wait_for(ws.close(code), 5)
            else:
                await asyncio.wait_for(ws.close(), 5)
        except Exception as e:
            logger.warning(
                "Ws-connection was not closed",
                user_id=user_id,
                websocket_id=id(ws),
                error_type=type(e).__name__,
            )
        finally:
            await self.unregister(user_id, ws)

    async def unregister(self, user_id: int, websocket: WebSocket) -> None:
        """Unregister a ws-connection"""

        try:
            self.connections[user_id][websocket].closing = True
            self.connections[user_id].pop(websocket)
        except KeyError:
            return

        if len(self.connections[user_id]) == 0:
            self.connections.pop(user_id)
