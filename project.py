"""Shared project paths, credentials, and storyboard lookup."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
STORYBOARD = ROOT / "storyboard.json"


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


def require_env(name, hint):
    """Return an environment variable or exit with instructions for setting it."""
    load_env()
    value = os.environ.get(name, "")
    if not value:
        sys.exit("Missing {}. Add it to .env:\n  {}=...\n{}".format(name, name, hint))
    return value


def load_storyboard():
    if not STORYBOARD.exists():
        sys.exit("No storyboard.json next to {}".format(__file__))
    return json.loads(STORYBOARD.read_text())


def find_shot(shot_id):
    """Return (shot, storyboard) for a shot id, or exit listing the valid ones."""
    board = load_storyboard()
    for shot in board["shots"]:
        if shot["id"] == shot_id:
            return shot, board
    sys.exit("No shot '{}' in storyboard.json. Known shots: {}".format(
        shot_id, ", ".join(s["id"] for s in board["shots"])
    ))
