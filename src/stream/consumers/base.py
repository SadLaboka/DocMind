from abc import ABC, abstractmethod
from typing import TypeVar

import structlog
from pydantic import BaseModel, ValidationError

logger = structlog.get_logger(__name__)

MAX_RETRIES = 3

T = TypeVar("T", bound=BaseModel)


class BaseConsumer[T: BaseModel](ABC):
    """Base class for FastStream consumers"""

    @staticmethod
    def _get_retry_count() -> int:
        """Extracts number of retry count from contextvars"""
        return structlog.contextvars.get_contextvars().get("retry_count", 0)

    async def __call__(self, raw_message: dict) -> None:
        """Entrypoint for FastStream"""
        event_model = self._get_event_model()
        queue_name = self._get_queue_name()
        retry_count = self._get_retry_count()

        try:
            event = event_model(**raw_message)
        except ValidationError as e:
            logger.error(
                "consumer_validation_error",
                error_code="invalid_event_schema",
                error_detail=str(e),
                queue_name=queue_name,
                retry_count=retry_count,
                raw_data=raw_message,
            )

            return

        log_context = self._extract_log_context(event)

        logger.info(
            "consumer_processing_started",
            event_type=event_model.__name__,
            queue_name=queue_name,
            retry_count=retry_count,
            **log_context,
        )

        try:
            await self.handle(event)

            logger.info(
                "consumer_processing_completed",
                event_type=event_model.__name__,
                queue_name=queue_name,
                retry_count=retry_count,
                **log_context,
            )

        except Exception as e:

            retryable = getattr(e, "retryable", True)

            if not retryable:
                logger.error(
                    "consumer_deterministic_error",
                    error_code=getattr(e, "error_code", "deterministic_error"),
                    error_detail=getattr(e, "message", str(e)),
                    error_type=type(e).__name__,
                    queue_name=queue_name,
                    retry_count=retry_count,
                    **log_context,
                )

                return

            if retry_count > MAX_RETRIES:
                logger.error(
                    "consumer_max_retries_exceeded",
                    error_code=getattr(e, "error_code", "max_retries_exceeded"),
                    error_detail=getattr(e, "message", str(e)),
                    error_type=type(e).__name__,
                    queue_name=queue_name,
                    retry_count=retry_count,
                    max_retries=MAX_RETRIES,
                    **log_context,
                )

                return

            logger.warning(
                "consumer_processing_error",
                error_code=getattr(e, "error_code", "processing_error"),
                error_detail=getattr(e, "message", str(e)),
                error_type=type(e).__name__,
                queue_name=queue_name,
                retry_count=retry_count,
                **log_context,
            )

            raise

    @abstractmethod
    async def handle(self, event: BaseModel) -> None:
        """Main consumer-logic"""

    @abstractmethod
    def _get_event_model(self) -> type[BaseModel]:
        """Returns pydantic model for validate"""

    @abstractmethod
    def _get_queue_name(self) -> str:
        """Returns queue name for logging"""

    def _extract_log_context(self, event: BaseModel) -> dict:
        """Extracts log context for logging"""
        data = event.model_dump()
        return {k: v for k, v in data.items() if k in ["document_id", "request_id", "user_id"]}
