"""Read key=value pairs from the project .env into the environment."""

import os
from pathlib import Path

ROOT = Path(__file__).parent


def load_env():
    """Populate os.environ from .env without overriding real environment vars."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
