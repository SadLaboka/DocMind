import subprocess
import sys
from pathlib import Path


def main():
    env_file = Path(".env")
    if not env_file.exists():
        print("Error: .env file not found")
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

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
