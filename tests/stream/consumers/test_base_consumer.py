from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from src.stream.consumers.base import MAX_RETRIES, BaseConsumer


class DummyEvent(BaseModel):
    document_id: int
    user_id: int
    request_id: str


class DummyConsumer(BaseConsumer[DummyEvent]):
    def __init__(self) -> None:
        self.handle_mock = AsyncMock()
        self.final_failure_mock = AsyncMock()

    async def handle(self, event: DummyEvent) -> None:
        await self.handle_mock(event)

    async def _on_final_failure(self, event: DummyEvent, error: Exception) -> None:
        await self.final_failure_mock(event, error)

    def _get_event_model(self) -> type[DummyEvent]:
        return DummyEvent

    def _get_queue_name(self) -> str:
        return "test.queue"


@pytest.fixture
def consumer() -> DummyConsumer:
    return DummyConsumer()


@pytest.fixture
def raw_message() -> dict:
    return {
        "document_id": 1,
        "user_id": 10,
        "request_id": "request-1",
    }


async def test_retryable_error_before_max_retries_is_raised(
    consumer,
    raw_message,
    monkeypatch,
):
    error = RuntimeError("temporary failure")
    consumer.handle_mock.side_effect = error

    monkeypatch.setattr(
        consumer,
        "_get_retry_count",
        lambda: MAX_RETRIES - 1,
    )

    with pytest.raises(RuntimeError) as exc_info:
        await consumer(raw_message)

    assert exc_info.value is error
    consumer.final_failure_mock.assert_not_awaited()


async def test_retryable_error_at_max_retries_calls_final_failure(
    consumer,
    raw_message,
    monkeypatch,
):
    error = RuntimeError("temporary failure")
    consumer.handle_mock.side_effect = error

    monkeypatch.setattr(
        consumer,
        "_get_retry_count",
        lambda: MAX_RETRIES,
    )

    await consumer(raw_message)

    consumer.final_failure_mock.assert_awaited_once()

    event, final_error = consumer.final_failure_mock.await_args.args

    assert event == DummyEvent(**raw_message)
    assert final_error is error


async def test_final_failure_error_does_not_escape(
    consumer,
    raw_message,
    monkeypatch,
):
    original_error = RuntimeError("temporary failure")

    consumer.handle_mock.side_effect = original_error
    consumer.final_failure_mock.side_effect = RuntimeError("finalizer failed")

    monkeypatch.setattr(
        consumer,
        "_get_retry_count",
        lambda: MAX_RETRIES,
    )

    await consumer(raw_message)

    consumer.final_failure_mock.assert_awaited_once()
