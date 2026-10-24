"""Folder locations on the user's machine. Nothing here is ever inside the repository.

Set the environment variable VDQ_HOME to redirect every location, which the tests do.
"""

import os
import sys
from pathlib import Path

APP_NAME = "Voice Database Query"


def _override() -> "Path | None":
    value = os.environ.get("VDQ_HOME")
    return Path(value).expanduser() if value else None


def settings_dir() -> Path:
    """Roaming settings: settings.json, catalog.json, history.json."""
    override = _override()
    if override:
        return override / "settings"
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / APP_NAME


def local_dir() -> Path:
    """Machine-local data: logs and speech models."""
    override = _override()
    if override:
        return override / "local"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / APP_NAME


def logs_dir() -> Path:
    return local_dir() / "logs"


def models_dir() -> Path:
    return local_dir() / "models"


def ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
