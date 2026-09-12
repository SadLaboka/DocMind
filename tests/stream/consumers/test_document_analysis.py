from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.core.enums import AnalysisFailureKind, AnalysisStatus, LLMProvider
from src.events.schemas import AnalysisRequestedEvent
from src.llm.base import BaseLLMService
from src.llm.exceptions import LLMException
from src.llm.factory import LLMServiceFactory
from src.schemas.analyses import AnalysisResult
from src.stream.consumers.document_analysis import (
    ConsumerError,
    DocumentAnalysisConsumer,
)

ANALYSIS_ID = "507f1f77bcf86cd799439011"


@pytest.fixture
def analysis_event() -> AnalysisRequestedEvent:
    return AnalysisRequestedEvent(
        analysis_id=ANALYSIS_ID,
        document_id=1,
        user_id=10,
        request_id="1",
    )


@pytest.fixture
def prompt():
    return SimpleNamespace(
        version="v1.0.0",
        content="Analyze this document: {text}",
    )


@pytest.fixture
def analysis_result() -> AnalysisResult:
    return AnalysisResult(
        summary="Test summary",
        keywords=["test", "document"],
        document_type="other",
        entities={},
        confidence=0.9,
        raw_response='{"result": "ok"}',
    )


@pytest.fixture
def llm_service(analysis_result: AnalysisResult) -> MagicMock:
    service = MagicMock(spec=BaseLLMService)
    service.analyze_text = AsyncMock(return_value=analysis_result)
    return service


@pytest.fixture
def llm_factory(llm_service: MagicMock) -> MagicMock:
    factory = MagicMock(spec=LLMServiceFactory)
    factory.create.return_value = llm_service
    return factory


@pytest.fixture
def analysis_consumer(
    mock_analysis_repo,
    mock_mongo_repo,
    mock_mongo_prompt_repository,
    llm_factory,
    prompt,
) -> DocumentAnalysisConsumer:
    mock_mongo_repo.get_content.return_value.raw_text = "document text"
    mock_mongo_prompt_repository.get_active_prompt.return_value = prompt

    return DocumentAnalysisConsumer(
        llm_service_factory=llm_factory,
        prompt_repo=mock_mongo_prompt_repository,
        document_repo=mock_mongo_repo,
        analysis_repo=mock_analysis_repo,
    )


async def test_handle_success(
    analysis_consumer,
    analysis_event,
    mock_analysis_repo,
    mock_mongo_repo,
    mock_mongo_prompt_repository,
    llm_factory,
    llm_service,
    analysis_result,
):
    analysis = mock_analysis_repo.get_analysis_by_id.return_value
    analysis.provider = LLMProvider.gpt

    await analysis_consumer.handle(analysis_event)

    mock_mongo_repo.get_content.assert_awaited_once_with(1)
    mock_mongo_prompt_repository.get_active_prompt.assert_awaited_once()

    llm_factory.create.assert_called_once_with(LLMProvider.gpt.value)
    llm_service.analyze_text.assert_awaited_once_with(
        text="document text",
        prompt="Analyze this document: {text}",
    )

    assert mock_analysis_repo.update_analysis_fields.await_count == 2
    mock_analysis_repo.update_analysis_fields.assert_has_awaits(
        [
            call(
                document_id=1,
                request_id="1",
                status=AnalysisStatus.analyzing,
            ),
            call(
                document_id=1,
                request_id="1",
                result=analysis_result,
                status=AnalysisStatus.success,
                prompt_version="v1.0.0",
                error_code=None,
                error_detail=None,
                failure_kind=None,
            ),
        ]
    )


@pytest.mark.parametrize(
    "terminal_status",
    [
        AnalysisStatus.success,
        AnalysisStatus.failed,
    ],
)
async def test_handle_terminal_analysis_does_nothing(
    terminal_status,
    analysis_consumer,
    analysis_event,
    mock_analysis_repo,
    mock_mongo_repo,
    mock_mongo_prompt_repository,
    llm_factory,
):
    analysis = mock_analysis_repo.get_analysis_by_id.return_value
    analysis.status = terminal_status

    await analysis_consumer.handle(analysis_event)

    mock_mongo_repo.get_content.assert_not_awaited()
    mock_mongo_prompt_repository.get_active_prompt.assert_not_awaited()
    mock_analysis_repo.update_analysis_fields.assert_not_awaited()
    llm_factory.create.assert_not_called()


async def test_handle_invalid_analysis_id(
    analysis_consumer,
    mock_analysis_repo,
):
    event = AnalysisRequestedEvent(
        analysis_id="invalid-id",
        document_id=1,
        user_id=10,
        request_id="1",
    )

    with pytest.raises(ConsumerError) as exc_info:
        await analysis_consumer.handle(event)

    assert exc_info.value.retryable is False
    assert exc_info.value.error_code == "invalid_analysis_id"

    mock_analysis_repo.get_analysis_by_id.assert_not_awaited()


async def test_handle_analysis_not_found(
    analysis_consumer,
    analysis_event,
    mock_analysis_repo,
):
    mock_analysis_repo.get_analysis_by_id.return_value = None

    with pytest.raises(ConsumerError) as exc_info:
        await analysis_consumer.handle(analysis_event)

    assert exc_info.value.retryable is False
    assert exc_info.value.error_code == "analysis_not_found"


async def test_handle_corrupted_event_marks_analysis_failed(
    analysis_consumer,
    mock_analysis_repo,
    mock_mongo_repo,
    llm_factory,
):
    event = AnalysisRequestedEvent(
        analysis_id=ANALYSIS_ID,
        document_id=999,
        user_id=10,
        request_id="1",
    )

    with pytest.raises(ConsumerError) as exc_info:
        await analysis_consumer.handle(event)

    assert exc_info.value.retryable is False
    assert exc_info.value.error_code == "event_corrupted"

    mock_analysis_repo.update_analysis_fields.assert_awaited_once_with(
        document_id=1,
        request_id="1",
        status=AnalysisStatus.failed,
        failure_kind=AnalysisFailureKind.permanent,
        error_code="event_corrupted",
    )

    mock_mongo_repo.get_content.assert_not_awaited()
    llm_factory.create.assert_not_called()


async def test_handle_missing_raw_text_marks_analysis_failed(
    analysis_consumer,
    analysis_event,
    mock_analysis_repo,
    mock_mongo_repo,
    mock_mongo_prompt_repository,
    llm_factory,
):
    mock_mongo_repo.get_content.return_value = None

    await analysis_consumer.handle(analysis_event)

    mock_analysis_repo.update_analysis_fields.assert_awaited_once_with(
        document_id=1,
        request_id="1",
        status=AnalysisStatus.failed,
        failure_kind=AnalysisFailureKind.permanent,
        error_code="document_text_not_found",
        error_detail="Raw text is missing in MongoDB",
    )

    mock_mongo_prompt_repository.get_active_prompt.assert_not_awaited()
    llm_factory.create.assert_not_called()


async def test_handle_retryable_llm_error_is_raised_for_retry(
    analysis_consumer,
    analysis_event,
    mock_analysis_repo,
    llm_service,
):
    error = LLMException(
        message="Provider temporarily unavailable",
        error_code="llm_provider_error",
        retryable=True,
    )
    llm_service.analyze_text.side_effect = error

    with pytest.raises(LLMException) as exc_info:
        await analysis_consumer.handle(analysis_event)

    assert exc_info.value is error

    mock_analysis_repo.update_analysis_fields.assert_awaited_once_with(
        document_id=1,
        request_id="1",
        status=AnalysisStatus.analyzing,
    )


async def test_handle_non_retryable_llm_error_marks_analysis_failed(
    analysis_consumer,
    analysis_event,
    mock_analysis_repo,
    llm_service,
):
    llm_service.analyze_text.side_effect = LLMException(
        message="Invalid provider configuration",
        error_code="llm_config_error",
        retryable=False,
    )

    await analysis_consumer.handle(analysis_event)

    assert mock_analysis_repo.update_analysis_fields.await_count == 2
    mock_analysis_repo.update_analysis_fields.assert_has_awaits(
        [
            call(
                document_id=1,
                request_id="1",
                status=AnalysisStatus.analyzing,
            ),
            call(
                document_id=1,
                request_id="1",
                status=AnalysisStatus.failed,
                failure_kind=AnalysisFailureKind.permanent,
                error_code="llm_config_error",
                error_detail="Invalid provider configuration",
            ),
        ]
    )


async def test_final_failure_marks_analysis_failed_transient(
    analysis_consumer,
    analysis_event,
    mock_analysis_repo,
):
    analysis = mock_analysis_repo.get_analysis_by_id.return_value
    analysis.status = AnalysisStatus.analyzing

    error = LLMException(
        message="Provider temporarily unavailable",
        error_code="llm_provider_error",
        retryable=True,
    )

    await analysis_consumer._on_final_failure(
        analysis_event,
        error,
    )

    mock_analysis_repo.get_analysis_by_id.assert_awaited_once()

    mock_analysis_repo.update_analysis_fields.assert_awaited_once_with(
        document_id=1,
        request_id="1",
        status=AnalysisStatus.failed,
        failure_kind=AnalysisFailureKind.transient,
        error_code="llm_provider_error",
        error_detail="Provider temporarily unavailable",
    )


@pytest.mark.parametrize(
    "terminal_status",
    [
        AnalysisStatus.success,
        AnalysisStatus.failed,
    ],
)
async def test_final_failure_does_not_overwrite_terminal_analysis(
    terminal_status,
    analysis_consumer,
    analysis_event,
    mock_analysis_repo,
):
    analysis = mock_analysis_repo.get_analysis_by_id.return_value
    analysis.status = terminal_status

    error = LLMException(
        message="Provider temporarily unavailable",
        error_code="llm_provider_error",
        retryable=True,
    )

    await analysis_consumer._on_final_failure(
        analysis_event,
        error,
    )

    mock_analysis_repo.update_analysis_fields.assert_not_awaited()


async def test_final_failure_does_not_update_analysis_for_corrupted_event(
    analysis_consumer,
    mock_analysis_repo,
):
    analysis = mock_analysis_repo.get_analysis_by_id.return_value
    analysis.status = AnalysisStatus.analyzing

    event = AnalysisRequestedEvent(
        analysis_id=ANALYSIS_ID,
        document_id=999,
        user_id=10,
        request_id="1",
    )

    error = LLMException(
        message="Provider temporarily unavailable",
        error_code="llm_provider_error",
        retryable=True,
    )

    await analysis_consumer._on_final_failure(
        event,
        error,
    )

    mock_analysis_repo.update_analysis_fields.assert_not_awaited()

