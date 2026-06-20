from faststream import BaseMiddleware
from faststream.rabbit import RabbitMessage
import structlog

logger = structlog.get_logger(__name__)


class RetryLoggingMiddleware(BaseMiddleware):
    """Middleware for logging retry count"""

    async def consume_scope(self, call_next, message: RabbitMessage):
        retry_count = self._get_retry_count(message)

        structlog.contextvars.bind_contextvars(retry_count=retry_count)

        try:
            result = await call_next(message)
            return result
        finally:
            structlog.contextvars.clear_contextvars()

    def _get_retry_count(self, message: RabbitMessage) -> int:
        """Extracts retry count from message"""
        if 'x-death' in message.headers:
            x_death = message.headers['x-death']
            if isinstance(x_death, list) and len(x_death) > 0:
                return x_death[0].get('count', 0)

        return 0
