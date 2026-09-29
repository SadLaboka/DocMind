from unittest.mock import AsyncMock, patch

import pytest
from beanie import BeanieObjectId
from pymongo.errors import DuplicateKeyError

from src.core.enums import AnalysisFailureKind, AnalysisStatus, LLMProvider
from src.core.exceptions import ConflictError, ResourceNotFoundError, ServiceUnavailableError
from src.events.publisher import publish_document_analysis_requested
from src.services.analysis import AnalysisService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("returned_count", "expected_count", "expected_has_next"),
    [
        (0, 0, False),
        (1, 1, False),
        (10, 10, False),
        (11, 10, True),
    ],
)
async def test_get_analyses_list_pagination_boundaries(
    mock_analysis_repo: AsyncMock,
    analysis_content_factory,
    returned_count: int,
    expected_count: int,
    expected_has_next: bool,
) -> None:
    mock_analysis_repo.get_analyses_by_document_id.return_value = [
        analysis_content_factory(
            document_id=42,
            request_id=f"request-{index}",
        )
        for index in range(returned_count)
    ]

    service = AnalysisService(mock_analysis_repo)

    result = await service.get_analyses_list(
        document_id=42,
        page=1,
        limit=10,
        user_id=7,
    )

    assert len(result.analyses) == expected_count
    assert result.page == 1
    assert result.limit == 10
    assert result.has_next is expected_has_next

    mock_analysis_repo.get_analyses_by_document_id.assert_awaited_once_with(
        42,
        limit=11,
        skip=0,
        statuses=None,
        providers=None,
    )


@pytest.mark.asyncio
async def test_get_analyses_list_passes_pagination_and_filters_to_repository(
    mock_analysis_repo: AsyncMock,
) -> None:
    mock_analysis_repo.get_analyses_by_document_id.return_value = []

    service = AnalysisService(mock_analysis_repo)

    statuses = [
        AnalysisStatus.success,
        AnalysisStatus.failed,
    ]
    providers = [
        LLMProvider.gemini,
        LLMProvider.deepseek,
    ]

    result = await service.get_analyses_list(
        document_id=42,
        page=3,
        limit=10,
        user_id=7,
        analyses_statuses=statuses,
        providers=providers,
    )

    assert result.analyses == []
    assert result.page == 3
    assert result.limit == 10
    assert result.has_next is False

    mock_analysis_repo.get_analyses_by_document_id.assert_awaited_once_with(
        42,
        limit=11,
        skip=20,
        statuses=statuses,
        providers=providers,
    )


ANALYSIS_ID = "507f1f77bcf86cd799439011"
RETRY_ANALYSIS_ID = "507f1f77bcf86cd799439012"


@pytest.mark.asyncio
async def test_get_analysis_success(
    mock_analysis_repo: AsyncMock,
    analysis_content_factory,
) -> None:
    analysis = analysis_content_factory(
        document_id=42,
        request_id="request-1",
    )
    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = analysis

    service = AnalysisService(mock_analysis_repo)

    result = await service.get_analysis(
        analysis_id=ANALYSIS_ID,
        document_id=42,
        user_id=7,
    )

    assert result.id == analysis.id
    assert result.status == analysis.status
    assert result.provider == analysis.provider

    mock_analysis_repo.get_analysis_by_id_and_document_id.assert_awaited_once_with(
        BeanieObjectId(ANALYSIS_ID),
        42,
    )


@pytest.mark.asyncio
async def test_get_analysis_malformed_id_returns_not_found(
    mock_analysis_repo: AsyncMock,
) -> None:
    service = AnalysisService(mock_analysis_repo)

    with pytest.raises(ResourceNotFoundError) as exc_info:
        await service.get_analysis(
            analysis_id="invalid-id",
            document_id=42,
            user_id=7,
        )

    assert exc_info.value.error_code == "analysis_not_found"

    mock_analysis_repo.get_analysis_by_id_and_document_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_analysis_not_found(
    mock_analysis_repo: AsyncMock,
) -> None:
    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = None

    service = AnalysisService(mock_analysis_repo)

    with pytest.raises(ResourceNotFoundError) as exc_info:
        await service.get_analysis(
            analysis_id=ANALYSIS_ID,
            document_id=42,
            user_id=7,
        )

    assert exc_info.value.error_code == "analysis_not_found"

    mock_analysis_repo.get_analysis_by_id_and_document_id.assert_awaited_once_with(
        BeanieObjectId(ANALYSIS_ID),
        42,
    )


@pytest.mark.asyncio
async def test_create_and_dispatch_analysis_success(
    mock_analysis_repo: AsyncMock,
    analysis_content_factory,
) -> None:
    analysis = analysis_content_factory(
        document_id=42,
        request_id="request-1",
    ).model_copy(
        update={"provider": LLMProvider.gemini},
    )
    mock_analysis_repo.create_analysis.return_value = analysis

    service = AnalysisService(mock_analysis_repo)

    with patch(
        "src.services.analysis.asyncio.to_thread",
        new_callable=AsyncMock,
    ) as mock_to_thread:
        result = await service.create_and_dispatch_analysis(
            user_id=7,
            document_id=42,
            request_id="request-1",
            provider=LLMProvider.gemini,
        )

    assert result.id == analysis.id
    assert result.status == AnalysisStatus.queued
    assert result.provider == LLMProvider.gemini

    mock_analysis_repo.create_analysis.assert_awaited_once_with(
        42,
        "request-1",
        LLMProvider.gemini,
    )

    mock_to_thread.assert_awaited_once_with(
        publish_document_analysis_requested,
        analysis_id=str(analysis.id),
        document_id=42,
        user_id=7,
        request_id="request-1",
    )

    mock_analysis_repo.update_analysis_fields.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_and_dispatch_analysis_creation_failure_does_not_dispatch_or_recover(
    mock_analysis_repo: AsyncMock,
) -> None:
    primary_error = RuntimeError("Mongo insert failed")
    mock_analysis_repo.create_analysis.side_effect = primary_error

    service = AnalysisService(mock_analysis_repo)
    mock_mark_dispatch_failed = AsyncMock()

    with (
        patch(
            "src.services.analysis.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread,
        patch.object(
            service,
            "mark_dispatch_failed",
            new=mock_mark_dispatch_failed,
        ),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await service.create_and_dispatch_analysis(
            user_id=7,
            document_id=42,
            request_id="request-1",
            provider=LLMProvider.gemini,
        )

    assert exc_info.value is primary_error

    mock_to_thread.assert_not_awaited()
    mock_mark_dispatch_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_and_dispatch_analysis_publish_failure_marks_analysis_failed(
    mock_analysis_repo: AsyncMock,
    analysis_content_factory,
) -> None:
    analysis = analysis_content_factory(
        document_id=42,
        request_id="request-1",
    ).model_copy(
        update={"provider": LLMProvider.gemini},
    )
    mock_analysis_repo.create_analysis.return_value = analysis
    mock_analysis_repo.get_analysis_by_document_and_request.return_value = analysis

    primary_error = RuntimeError("RabbitMQ unavailable")

    service = AnalysisService(mock_analysis_repo)

    with (
        patch(
            "src.services.analysis.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=primary_error,
        ) as mock_to_thread,
        pytest.raises(ServiceUnavailableError) as exc_info,
    ):
        await service.create_and_dispatch_analysis(
            user_id=7,
            document_id=42,
            request_id="request-1",
            provider=LLMProvider.gemini,
        )

    assert exc_info.value.error_code == "analysis_dispatch_failed"
    assert exc_info.value.__cause__ is primary_error

    mock_to_thread.assert_awaited_once_with(
        publish_document_analysis_requested,
        analysis_id=str(analysis.id),
        document_id=42,
        user_id=7,
        request_id="request-1",
    )

    mock_analysis_repo.get_analysis_by_document_and_request.assert_awaited_once_with(
        42,
        "request-1",
    )
    mock_analysis_repo.update_analysis_fields.assert_awaited_once_with(
        document_id=42,
        request_id="request-1",
        status=AnalysisStatus.failed,
        failure_kind=AnalysisFailureKind.transient,
        error_code="analysis_dispatch_failed",
        error_detail=str(primary_error),
    )


@pytest.mark.asyncio
async def test_create_and_dispatch_analysis_recovery_failure_does_not_mask_publish_error(
    mock_analysis_repo: AsyncMock,
    analysis_content_factory,
) -> None:
    analysis = analysis_content_factory(
        document_id=42,
        request_id="request-1",
    ).model_copy(
        update={"provider": LLMProvider.gemini},
    )
    mock_analysis_repo.create_analysis.return_value = analysis

    primary_error = RuntimeError("RabbitMQ unavailable")
    recovery_error = RuntimeError("Mongo unavailable during recovery")

    service = AnalysisService(mock_analysis_repo)
    mock_mark_dispatch_failed = AsyncMock(side_effect=recovery_error)

    with (
        patch(
            "src.services.analysis.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=primary_error,
        ),
        patch.object(
            service,
            "mark_dispatch_failed",
            new=mock_mark_dispatch_failed,
        ),
        pytest.raises(ServiceUnavailableError) as exc_info,
    ):
        await service.create_and_dispatch_analysis(
            user_id=7,
            document_id=42,
            request_id="request-1",
            provider=LLMProvider.gemini,
        )

    assert exc_info.value.error_code == "analysis_dispatch_failed"
    assert exc_info.value.__cause__ is primary_error

    mock_mark_dispatch_failed.assert_awaited_once_with(
        document_id=42,
        request_id="request-1",
        error_detail=primary_error,
    )


@pytest.mark.asyncio
async def test_retry_analysis_success(
    mock_analysis_repo: AsyncMock,
    analysis_content_factory,
) -> None:
    source_id = BeanieObjectId(ANALYSIS_ID)
    retry_id = BeanieObjectId(RETRY_ANALYSIS_ID)

    source_analysis = analysis_content_factory(
        document_id=42,
        request_id="source-request",
    ).model_copy(
        update={
            "id": source_id,
            "status": AnalysisStatus.failed,
            "failure_kind": AnalysisFailureKind.transient,
            "provider": LLMProvider.gemini,
        }
    )

    retried_analysis = analysis_content_factory(
        document_id=42,
        request_id="retry-request",
    ).model_copy(
        update={
            "id": retry_id,
            "provider": LLMProvider.gemini,
            "retry_of_analysis_id": source_id,
        }
    )

    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = source_analysis
    mock_analysis_repo.get_analysis_by_retry_of_analysis_id.return_value = None
    mock_analysis_repo.create_analysis.return_value = retried_analysis

    service = AnalysisService(mock_analysis_repo)

    with patch(
        "src.services.analysis.asyncio.to_thread",
        new_callable=AsyncMock,
    ) as mock_to_thread:
        result = await service.retry_analysis(
            analysis_id=ANALYSIS_ID,
            document_id=42,
            request_id="retry-request",
            user_id=7,
        )

    assert result.id == str(retry_id)
    assert result.status == AnalysisStatus.queued
    assert result.provider == LLMProvider.gemini
    assert result.retry_of_analysis_id == str(source_id)

    mock_analysis_repo.get_analysis_by_id_and_document_id.assert_awaited_once_with(
        source_id,
        42,
    )
    mock_analysis_repo.get_analysis_by_retry_of_analysis_id.assert_awaited_once_with(
        source_id,
    )
    mock_analysis_repo.create_analysis.assert_awaited_once_with(
        document_id=42,
        request_id="retry-request",
        provider=LLMProvider.gemini,
        retry_of_analysis_id=source_id,
    )

    mock_to_thread.assert_awaited_once_with(
        publish_document_analysis_requested,
        analysis_id=str(retry_id),
        document_id=42,
        user_id=7,
        request_id="retry-request",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("analysis_status", "failure_kind"),
    [
        (AnalysisStatus.queued, None),
        (AnalysisStatus.analyzing, None),
        (AnalysisStatus.success, None),
        (AnalysisStatus.failed, AnalysisFailureKind.permanent),
    ],
)
async def test_retry_analysis_rejects_non_retryable_analysis(
    mock_analysis_repo: AsyncMock,
    analysis_content_factory,
    analysis_status: AnalysisStatus,
    failure_kind: AnalysisFailureKind | None,
) -> None:
    source_id = BeanieObjectId(ANALYSIS_ID)

    source_analysis = analysis_content_factory(
        document_id=42,
        request_id="source-request",
    ).model_copy(
        update={
            "id": source_id,
            "status": analysis_status,
            "failure_kind": failure_kind,
        }
    )

    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = source_analysis

    service = AnalysisService(mock_analysis_repo)

    with (
        patch(
            "src.services.analysis.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread,
        pytest.raises(ConflictError) as exc_info,
    ):
        await service.retry_analysis(
            analysis_id=ANALYSIS_ID,
            document_id=42,
            request_id="retry-request",
            user_id=7,
        )

    assert exc_info.value.error_code == "analysis_not_retryable"

    mock_analysis_repo.get_analysis_by_retry_of_analysis_id.assert_not_awaited()
    mock_analysis_repo.create_analysis.assert_not_awaited()
    mock_to_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_analysis_rejects_when_child_already_exists(
    mock_analysis_repo: AsyncMock,
    analysis_content_factory,
) -> None:
    source_id = BeanieObjectId(ANALYSIS_ID)
    child_id = BeanieObjectId(RETRY_ANALYSIS_ID)

    source_analysis = analysis_content_factory(
        document_id=42,
        request_id="source-request",
    ).model_copy(
        update={
            "id": source_id,
            "status": AnalysisStatus.failed,
            "failure_kind": AnalysisFailureKind.transient,
        }
    )
    child_analysis = analysis_content_factory(
        document_id=42,
        request_id="existing-retry",
    ).model_copy(
        update={
            "id": child_id,
            "retry_of_analysis_id": source_id,
        }
    )

    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = source_analysis
    mock_analysis_repo.get_analysis_by_retry_of_analysis_id.return_value = child_analysis

    service = AnalysisService(mock_analysis_repo)

    with (
        patch(
            "src.services.analysis.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread,
        pytest.raises(ConflictError) as exc_info,
    ):
        await service.retry_analysis(
            analysis_id=ANALYSIS_ID,
            document_id=42,
            request_id="retry-request",
            user_id=7,
        )

    assert exc_info.value.error_code == "analysis_already_retried"

    mock_analysis_repo.create_analysis.assert_not_awaited()
    mock_to_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_analysis_duplicate_race_returns_already_retried(
    mock_analysis_repo: AsyncMock,
    analysis_content_factory,
) -> None:
    source_id = BeanieObjectId(ANALYSIS_ID)
    child_id = BeanieObjectId(RETRY_ANALYSIS_ID)

    source_analysis = analysis_content_factory(
        document_id=42,
        request_id="source-request",
    ).model_copy(
        update={
            "id": source_id,
            "status": AnalysisStatus.failed,
            "failure_kind": AnalysisFailureKind.transient,
        }
    )
    child_analysis = analysis_content_factory(
        document_id=42,
        request_id="concurrent-retry",
    ).model_copy(
        update={
            "id": child_id,
            "retry_of_analysis_id": source_id,
        }
    )

    duplicate_error = DuplicateKeyError("duplicate retry")

    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = source_analysis
    mock_analysis_repo.get_analysis_by_retry_of_analysis_id.side_effect = [
        None,
        child_analysis,
    ]
    mock_analysis_repo.create_analysis.side_effect = duplicate_error

    service = AnalysisService(mock_analysis_repo)

    with (
        patch(
            "src.services.analysis.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread,
        pytest.raises(ConflictError) as exc_info,
    ):
        await service.retry_analysis(
            analysis_id=ANALYSIS_ID,
            document_id=42,
            request_id="retry-request",
            user_id=7,
        )

    assert exc_info.value.error_code == "analysis_already_retried"
    assert exc_info.value.__cause__ is duplicate_error

    assert mock_analysis_repo.get_analysis_by_retry_of_analysis_id.await_count == 2
    mock_to_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_analysis_unrelated_duplicate_error_propagates(
    mock_analysis_repo: AsyncMock,
    analysis_content_factory,
) -> None:
    source_id = BeanieObjectId(ANALYSIS_ID)

    source_analysis = analysis_content_factory(
        document_id=42,
        request_id="source-request",
    ).model_copy(
        update={
            "id": source_id,
            "status": AnalysisStatus.failed,
            "failure_kind": AnalysisFailureKind.transient,
        }
    )

    duplicate_error = DuplicateKeyError("unrelated duplicate")

    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = source_analysis
    mock_analysis_repo.get_analysis_by_retry_of_analysis_id.side_effect = [
        None,
        None,
    ]
    mock_analysis_repo.create_analysis.side_effect = duplicate_error

    service = AnalysisService(mock_analysis_repo)

    with (
        patch(
            "src.services.analysis.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread,
        pytest.raises(DuplicateKeyError) as exc_info,
    ):
        await service.retry_analysis(
            analysis_id=ANALYSIS_ID,
            document_id=42,
            request_id="retry-request",
            user_id=7,
        )

    assert exc_info.value is duplicate_error
    assert mock_analysis_repo.get_analysis_by_retry_of_analysis_id.await_count == 2
    mock_to_thread.assert_not_awaited()
