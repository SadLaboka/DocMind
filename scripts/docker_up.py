import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import structlog

from src.core.logging_config import setup_logging

logger = structlog.get_logger(__name__)


def main():
    setup_logging()
    env_file = Path(".env")
    if not env_file.exists():
        logger.info("env_file_not_found")
        sys.exit(1)

    storage_backend = "local"  # default
    for line in env_file.read_text().splitlines():
        if line.startswith("STORAGE_BACKEND="):
            storage_backend = line.split("=", 1)[1].strip()
            break

    cmd = ["docker", "compose"]
    if storage_backend == "local":
        cmd.extend(["--profile", "local-storage"])
    cmd.extend(["up", "-d", "--build"])

    logger.info("docker_compose_starting", command=" ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
