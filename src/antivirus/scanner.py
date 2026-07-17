import socket
import time
from dataclasses import dataclass
from pathlib import Path

from src.antivirus.client import ClamAVClient
from src.antivirus.exceptions import AntivirusUnavailableError
from src.core.config import settings


@dataclass
class ScanResult:
    is_infected: bool
    signature: str | None
    duration_ms: float


class AntivirusScanner:
    def __init__(self, client: ClamAVClient | None = None) -> None:
        if client:
            self.client = client
        else:
            self.client = ClamAVClient(
                host=settings.antivirus.host,
                port=settings.antivirus.port,
                timeout=settings.antivirus.timeout,
                chunk_size=settings.antivirus.chunk_size,
            )

    def scan_file(self, file_path: Path) -> ScanResult:
        """Scan a file and return a ScanResult"""
        start_time = time.perf_counter()

        try:
            raw_response = self.client.scan_file(file_path)
        except (socket.error, OSError, socket.timeout) as e:
            raise AntivirusUnavailableError(
                message="ClamAV connection failed",
                error_code="antivirus_connection_error",
                host=self.client.host,
                port=self.client.port,
                original_error=e,
            ) from e

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if raw_response.endswith(" FOUND"):
            signature = self._extract_signature(raw_response)
            return ScanResult(
                is_infected=True,
                signature=signature,
                duration_ms=duration_ms,
            )

        if raw_response.endswith(" ERROR"):
            raise AntivirusUnavailableError(
                message=f"ClamAV returned error: {raw_response}",
                error_code="antivirus_scan_error",
                host=self.client.host,
                port=self.client.port,
            )

        if raw_response == "stream: OK":
            return ScanResult(
                is_infected=False,
                signature=None,
                duration_ms=duration_ms,
            )

        raise AntivirusUnavailableError(
            message=f"Unexpected ClamAV response: {raw_response}",
            error_code="antivirus_invalid_response",
            host=self.client.host,
            port=self.client.port,
        )

    @staticmethod
    def _extract_signature(result: str) -> str:
        """Extract signature name from ClamAV response"""
        return result.removeprefix("stream: ").removesuffix(" FOUND")
