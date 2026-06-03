"""Shared imaging-mode defaults for overlay units and scalebar length."""

from __future__ import annotations

from typing import TypedDict


class ModeOverlayDefaults(TypedDict):
    """Overlay defaults associated with a named imaging mode preset."""

    unit: str
    scalebar_length_value: float
    scalebar_length_text: str


_MODE_OVERLAY_DEFAULTS: dict[str, ModeOverlayDefaults] = {
    "Standard": {"unit": "µm", "scalebar_length_value": 5.0, "scalebar_length_text": "5"},
    "Local Map": {"unit": "µm", "scalebar_length_value": 10.0, "scalebar_length_text": "10"},
    "Reference": {"unit": "µm", "scalebar_length_value": 2.0, "scalebar_length_text": "2"},
    "In focus": {"unit": "µm", "scalebar_length_value": 5.0, "scalebar_length_text": "5"},
    "High Res": {"unit": "nm", "scalebar_length_value": 500.0, "scalebar_length_text": "500"},
}


def get_mode_overlay_defaults(preset_name: str) -> ModeOverlayDefaults | None:
    """Return a copy of defaults for a preset name, or None when not defined."""
    defaults = _MODE_OVERLAY_DEFAULTS.get(preset_name)
    if defaults is None:
        return None
    return dict(defaults)
