from unittest.mock import AsyncMock

import pytest
from beanie import BeanieObjectId

from src.core.enums import AnalysisStatus, LLMProvider
from src.core.exceptions import ResourceNotFoundError
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
