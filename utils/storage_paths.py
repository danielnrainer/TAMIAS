"""Filesystem path helpers for user-specific TAMIAS data."""

from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "TAMIAS"


def get_app_storage_dir(app_name: str = APP_NAME) -> Path:
    """Return a per-user writable config directory for the app."""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / app_name
        return Path.home() / "AppData" / "Roaming" / app_name

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / app_name
    return Path.home() / ".config" / app_name


def ensure_app_storage_dir(app_name: str = APP_NAME) -> Path:
    """Create and return the app storage directory."""
    path = get_app_storage_dir(app_name)
    path.mkdir(parents=True, exist_ok=True)
    return path
