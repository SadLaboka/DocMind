import socket
import struct
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.antivirus.client import ClamAVClient


@pytest.fixture
def clamav_client() -> ClamAVClient:
    return ClamAVClient(
        host="clamav",
        port=3310,
        timeout=5.0,
        chunk_size=4,
    )


@pytest.fixture
def mock_socket() -> MagicMock:
    socket_mock = MagicMock()
    socket_mock.__enter__.return_value = socket_mock
    socket_mock.__exit__.return_value = False
    return socket_mock


def test_scan_file_sends_instream_protocol_and_returns_response(
    clamav_client: ClamAVClient,
    mock_socket: MagicMock,
    temp_file: Path,
) -> None:
    mock_socket.recv.side_effect = [
        b"stream: ",
        b"OK\0",
    ]

    with patch.object(
        clamav_client,
        "_create_socket",
        return_value=mock_socket,
    ) as mock_create_socket:
        result = clamav_client.scan_file(temp_file)

    file_content = temp_file.read_bytes()
    chunks = [
        file_content[index : index + clamav_client.chunk_size]
        for index in range(0, len(file_content), clamav_client.chunk_size)
    ]

    expected_send_calls = [call(b"zINSTREAM\0")]
    for chunk in chunks:
        expected_send_calls.extend(
            [
                call(struct.pack("!I", len(chunk))),
                call(chunk),
            ]
        )
    expected_send_calls.append(call(struct.pack("!I", 0)))

    assert result == "stream: OK"

    mock_create_socket.assert_called_once_with()
    assert mock_socket.sendall.call_args_list == expected_send_calls
    assert mock_socket.recv.call_args_list == [
        call(4096),
        call(4096),
    ]
    mock_socket.__exit__.assert_called_once()


def test_scan_file_missing_file_does_not_create_socket(
    clamav_client: ClamAVClient,
    tmp_path: Path,
) -> None:
    missing_file = tmp_path / "missing.txt"

    with (
        patch.object(clamav_client, "_create_socket") as mock_create_socket,
        pytest.raises(FileNotFoundError, match="File not found"),
    ):
        clamav_client.scan_file(missing_file)

    mock_create_socket.assert_not_called()


def test_create_socket_configures_timeout_and_connects(
    clamav_client: ClamAVClient,
    mock_socket: MagicMock,
) -> None:
    with patch(
        "src.antivirus.client.socket.socket",
        return_value=mock_socket,
    ) as mock_socket_constructor:
        result = clamav_client._create_socket()

    assert result is mock_socket

    mock_socket_constructor.assert_called_once_with(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )
    mock_socket.settimeout.assert_called_once_with(5.0)
    mock_socket.connect.assert_called_once_with(("clamav", 3310))
    mock_socket.close.assert_not_called()


def test_create_socket_closes_socket_on_connection_error(
    clamav_client: ClamAVClient,
    mock_socket: MagicMock,
) -> None:
    connection_error = OSError("Connection refused")
    mock_socket.connect.side_effect = connection_error

    with (
        patch(
            "src.antivirus.client.socket.socket",
            return_value=mock_socket,
        ),
        pytest.raises(OSError, match="Connection refused") as exc_info,
    ):
        clamav_client._create_socket()

    assert exc_info.value is connection_error

    mock_socket.settimeout.assert_called_once_with(5.0)
    mock_socket.connect.assert_called_once_with(("clamav", 3310))
    mock_socket.close.assert_called_once_with()
