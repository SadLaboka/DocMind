from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.antivirus.client import ClamAVClient
from src.antivirus.exceptions import AntivirusUnavailableError
from src.antivirus.scanner import AntivirusScanner


@pytest.fixture
def file_path() -> Path:
    return Path("/tmp/test.txt")


@pytest.fixture
def mock_clamav_client() -> MagicMock:
    client = MagicMock(spec=ClamAVClient)
    client.host = "clamav"
    client.port = 3310
    return client


@pytest.fixture
def scanner(mock_clamav_client: MagicMock) -> AntivirusScanner:
    return AntivirusScanner(client=mock_clamav_client)


def test_scan_file_returns_clean_result(
    scanner: AntivirusScanner,
    mock_clamav_client: MagicMock,
    file_path: Path,
) -> None:
    mock_clamav_client.scan_file.return_value = "stream: OK"

    with patch(
        "src.antivirus.scanner.time.perf_counter",
        side_effect=[10.0, 10.123456],
    ):
        result = scanner.scan_file(file_path)

    assert result.is_infected is False
    assert result.signature is None
    assert result.duration_ms == 123.46

    mock_clamav_client.scan_file.assert_called_once_with(file_path)


def test_scan_file_returns_infected_result(
    scanner: AntivirusScanner,
    mock_clamav_client: MagicMock,
    file_path: Path,
) -> None:
    mock_clamav_client.scan_file.return_value = (
        "stream: Eicar-Test-Signature FOUND"
    )

    with patch(
        "src.antivirus.scanner.time.perf_counter",
        side_effect=[5.0, 5.01],
    ):
        result = scanner.scan_file(file_path)

    assert result.is_infected is True
    assert result.signature == "Eicar-Test-Signature"
    assert result.duration_ms == 10.0

    mock_clamav_client.scan_file.assert_called_once_with(file_path)


@pytest.mark.parametrize(
    "connection_error",
    [
        TimeoutError("Scan timeout"),
        OSError("Connection refused"),
    ],
    ids=["timeout", "os-error"],
)
def test_scan_file_wraps_connection_error(
    scanner: AntivirusScanner,
    mock_clamav_client: MagicMock,
    file_path: Path,
    connection_error: Exception,
) -> None:
    mock_clamav_client.scan_file.side_effect = connection_error

    with pytest.raises(AntivirusUnavailableError) as exc_info:
        scanner.scan_file(file_path)

    error = exc_info.value

    assert error.error_code == "antivirus_connection_error"
    assert error.message == "ClamAV connection failed"
    assert error.host == "clamav"
    assert error.port == 3310
    assert error.original_error is connection_error
    assert error.__cause__ is connection_error


def test_scan_file_rejects_clamav_error_response(
    scanner: AntivirusScanner,
    mock_clamav_client: MagicMock,
    file_path: Path,
) -> None:
    raw_response = "stream: Size limit exceeded ERROR"
    mock_clamav_client.scan_file.return_value = raw_response

    with (
        patch(
            "src.antivirus.scanner.time.perf_counter",
            side_effect=[1.0, 1.001],
        ),
        pytest.raises(AntivirusUnavailableError) as exc_info,
    ):
        scanner.scan_file(file_path)

    error = exc_info.value

    assert error.error_code == "antivirus_scan_error"
    assert error.message == f"ClamAV returned error: {raw_response}"
    assert error.host == "clamav"
    assert error.port == 3310


def test_scan_file_rejects_unknown_response(
    scanner: AntivirusScanner,
    mock_clamav_client: MagicMock,
    file_path: Path,
) -> None:
    raw_response = "unexpected response"
    mock_clamav_client.scan_file.return_value = raw_response

    with (
        patch(
            "src.antivirus.scanner.time.perf_counter",
            side_effect=[1.0, 1.001],
        ),
        pytest.raises(AntivirusUnavailableError) as exc_info,
    ):
        scanner.scan_file(file_path)

    error = exc_info.value

    assert error.error_code == "antivirus_invalid_response"
    assert error.message == f"Unexpected ClamAV response: {raw_response}"
    assert error.host == "clamav"
    assert error.port == 3310
