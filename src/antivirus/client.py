import socket
import struct
from pathlib import Path


class ClamAVClient:
    """TCP-client for clamd protocol"""
    def __init__(self, host: str, port: int, timeout: float, chunk_size: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.chunk_size = chunk_size

    def ping(self) -> bool:
        """Check if clamd is available"""
        try:
            with self._create_socket() as sock:
                sock.sendall(b"zPING\0")
                response = sock.recv(1024)
                return response.startswith(b"PONG")
        except (socket.error, OSError):
            return False

    def scan_file(self, file_path: Path) -> str:
        """Scan file with INSTREAM command"""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with self._create_socket() as sock:
            sock.sendall(b"zINSTREAM\0")

            with open(file_path, "rb") as f:
                while chunk := f.read(self.chunk_size):
                    sock.sendall(struct.pack("!I", len(chunk)))
                    sock.sendall(chunk)

            sock.sendall(struct.pack("!I", 0))

            response = b""
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                response += data
                if b"\0" in response:
                    break

            return response.rstrip(b"\0").decode("utf-8")

    def _create_socket(self) -> socket.socket:
        """Create and configure socket with timeout"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
            return sock
        except (socket.error, OSError) as e:
            sock.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
