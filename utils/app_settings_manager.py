"""App settings persistence for TAMIAS."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from utils.storage_paths import ensure_app_storage_dir


DEFAULT_SETTINGS: dict[str, Any] = {
    "theme_mode": "auto",
    "window": {
        "x": 100,
        "y": 100,
        "width": 1100,
        "height": 700,
    },
    "splitter_sizes": [900, 350],
    "single_io_directory": "",
    "batch_input_directory": "",
    "batch_output_directory": "",
    "overlay": {
        "scalebar_enabled": True,
        "scalebar_length_value": 100.0,
        "scalebar_unit": "nm",
        "scalebar_thickness": 15,
        "scalebar_position": "bottom-right",
        "bar_color": "#FFFFFF",
        "text_color": "#FFFFFF",
        "scalebar_bg_enabled": True,
        "scalebar_bg_color": "#000000",
        "scalebar_bg_opacity": 255,
        "aperture_enabled": False,
        "aperture_nominal_size": 100,
        "aperture_color": "#FFFF00",
        "measurement_enabled": False,
        "measurement_unit": "nm",
        "measurement_line_color": "#00FF00",
        "measurement_text_color": "#00FF00",
        "measurement_show_label": True,
        "measurement_line_width": 4,
    },
}


class AppSettingsStorage:
    """Load/save non-preset app settings."""

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
        settings = copy.deepcopy(DEFAULT_SETTINGS)
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
