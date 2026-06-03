"""App settings persistence for TAMIAS."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from utils.storage_paths import ensure_app_storage_dir, get_project_resource_path


def _load_shipped_default_settings() -> dict[str, Any]:
    """Load shipped app defaults from repository/bundle resource JSON."""
    defaults_file = get_project_resource_path("settings_defaults.json")
    try:
        with open(defaults_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError("Expected JSON object at root")
        return loaded
    except Exception as e:
        print(f"Error loading shipped app defaults from {defaults_file}: {e}")
        return {}


SHIPPED_DEFAULT_SETTINGS = _load_shipped_default_settings()


class AppSettingsStorage:
    """Load/save non-preset app settings."""

    @staticmethod
    def get_default_settings() -> dict[str, Any]:
        """Return a deep-copied view of shipped default app settings."""
        return copy.deepcopy(SHIPPED_DEFAULT_SETTINGS)

    @staticmethod
    def get_settings_file() -> Path:
        return ensure_app_storage_dir() / "settings.json"

    @staticmethod
    def _deep_merge(defaults: Any, loaded: Any) -> Any:
        if isinstance(defaults, dict) and isinstance(loaded, dict):
            merged = {k: copy.deepcopy(v) for k, v in defaults.items()}
            for key, value in loaded.items():
                if key in merged:
                    merged[key] = AppSettingsStorage._deep_merge(merged[key], value)
                else:
                    merged[key] = value
            return merged
        return loaded if loaded is not None else copy.deepcopy(defaults)

    @staticmethod
    def load_settings() -> dict[str, Any]:
        settings = AppSettingsStorage.get_default_settings()
        settings_file = AppSettingsStorage.get_settings_file()
        if not settings_file.exists():
            return settings

        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            settings = AppSettingsStorage._deep_merge(settings, loaded)
        except Exception as e:
            print(f"Error loading app settings: {e}")
        return settings

    @staticmethod
    def save_settings(settings: dict[str, Any]) -> None:
        settings_file = AppSettingsStorage.get_settings_file()
        try:
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Error saving app settings: {e}")

    @staticmethod
    def reset_to_defaults() -> dict[str, Any]:
        """Reset persisted app settings to shipped defaults and return them."""
        settings = AppSettingsStorage.get_default_settings()
        AppSettingsStorage.save_settings(settings)
        return settings
