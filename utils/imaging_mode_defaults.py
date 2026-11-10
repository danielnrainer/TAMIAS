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


# Pseudo-preset: take the pixel size from the image file header when available
# (.rodhypix), otherwise fall back to a real preset.
AUTO_PRESET_LABEL = "Auto (from file)"
AUTO_FALLBACK_PRESET = "Standard"


def _floor_to_nice_number(value: float) -> float:
    """Floor a positive value to the 1-2-5 series (e.g. 7.3 -> 5, 16 -> 10)."""
    import math

    exponent = math.floor(math.log10(value))
    base = 10.0 ** exponent
    for mult in (5.0, 2.0, 1.0):
        if value >= mult * base:
            return mult * base
    return base


def derive_overlay_defaults(nm_per_pixel: float, image_width_px: int | None) -> ModeOverlayDefaults:
    """Derive unit/scalebar defaults for a file-calibrated pixel size (~10% of image width)."""
    unit = "nm" if nm_per_pixel < 10.0 else "µm"
    width_px = image_width_px if image_width_px and image_width_px > 0 else 1024
    target_nm = 0.1 * width_px * nm_per_pixel
    target = target_nm if unit == "nm" else target_nm / 1000.0
    length = _floor_to_nice_number(target) if target > 0 else 1.0
    text = f"{length:g}"
    return {"unit": unit, "scalebar_length_value": length, "scalebar_length_text": text}
