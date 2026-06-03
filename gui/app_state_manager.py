"""UI state orchestration helpers for TAMIAS main window."""

from __future__ import annotations

from typing import Any

from PyQt6.QtGui import QColor

from gui.custom_widgets import set_color_button_indicator
from utils.app_settings_manager import AppSettingsStorage
from utils.preset_manager import PresetStorage


class AppStateManager:
    """Extracted app/UI state behaviors used by the main editor window."""

    @staticmethod
    def apply_overlay_settings(editor: Any, settings: dict):
        """Apply persisted overlay defaults to the renderer before UI setup."""
        if not isinstance(settings, dict):
            return

        def _as_bool(key: str, current: bool) -> bool:
            return bool(settings.get(key, current))

        def _as_int(key: str, current: int, min_value: int, max_value: int) -> int:
            try:
                value = int(settings.get(key, current))
            except Exception:
                value = current
            return max(min_value, min(max_value, value))

        def _as_float(key: str, current: float, min_value: float, max_value: float) -> float:
            try:
                value = float(settings.get(key, current))
            except Exception:
                value = current
            return max(min_value, min(max_value, value))

        def _as_color(key: str, current: QColor) -> QColor:
            raw = settings.get(key)
            color = QColor(raw) if raw is not None else QColor(current)
            return color if color.isValid() else QColor(current)

        renderer = editor.overlay_renderer

        renderer.scalebar_enabled = _as_bool("scalebar_enabled", renderer.scalebar_enabled)
        renderer.scalebar_length_value = _as_float("scalebar_length_value", renderer.scalebar_length_value, 0.01, 10000.0)
        unit = str(settings.get("scalebar_unit", renderer.scalebar_unit))
        renderer.scalebar_unit = unit if unit in {"nm", "µm"} else "nm"
        renderer.scalebar_thickness = _as_int("scalebar_thickness", renderer.scalebar_thickness, 5, 100)
        position = str(settings.get("scalebar_position", renderer.scalebar_position))
        renderer.scalebar_position = position if position in {"bottom-right", "bottom-left", "top-right", "top-left", "custom"} else "bottom-right"
        renderer.bar_color = _as_color("bar_color", renderer.bar_color)
        renderer.text_color = _as_color("text_color", renderer.text_color)
        renderer.scalebar_bg_enabled = _as_bool("scalebar_bg_enabled", renderer.scalebar_bg_enabled)
        renderer.scalebar_bg_color = _as_color("scalebar_bg_color", renderer.scalebar_bg_color)
        renderer.scalebar_bg_opacity = _as_int("scalebar_bg_opacity", renderer.scalebar_bg_opacity, 0, 255)

        renderer.aperture_enabled = _as_bool("aperture_enabled", renderer.aperture_enabled)
        renderer.aperture_nominal_size = _as_int("aperture_nominal_size", renderer.aperture_nominal_size, 1, 10000)
        renderer.aperture_color = _as_color("aperture_color", renderer.aperture_color)

        renderer.measurement_enabled = _as_bool("measurement_enabled", renderer.measurement_enabled)
        m_unit = str(settings.get("measurement_unit", renderer.measurement_unit))
        renderer.measurement_unit = m_unit if m_unit in {"nm", "µm"} else "nm"
        renderer.measurement_line_color = _as_color("measurement_line_color", renderer.measurement_line_color)
        renderer.measurement_text_color = _as_color("measurement_text_color", renderer.measurement_text_color)
        renderer.measurement_show_label = _as_bool("measurement_show_label", renderer.measurement_show_label)
        renderer.measurement_line_width = _as_int("measurement_line_width", renderer.measurement_line_width, 1, 20)
        start_cap = str(settings.get("measurement_start_cap", renderer.measurement_start_cap)).strip().lower()
        end_cap = str(settings.get("measurement_end_cap", renderer.measurement_end_cap)).strip().lower()
        renderer.measurement_start_cap = start_cap if start_cap in {"head", "tick", "dot", "none"} else "head"
        renderer.measurement_end_cap = end_cap if end_cap in {"head", "tick", "dot", "none"} else "head"

    @staticmethod
    def apply_overlay_settings_to_controls(editor: Any):
        """Sync UI controls from renderer values loaded from persisted settings."""
        renderer = editor.overlay_renderer

        editor.scalebar_checkbox.setChecked(renderer.scalebar_enabled)
        editor.scalebar_length_spinbox.setValue(float(renderer.scalebar_length_value))
        editor.unit_combo.setCurrentText(renderer.scalebar_unit)
        editor.scalebar_thickness_spinbox.setValue(int(renderer.scalebar_thickness))
        editor.position_combo.setCurrentText(renderer.scalebar_position)
        editor.bg_checkbox.setChecked(renderer.scalebar_bg_enabled)
        editor.bg_opacity_slider.setValue(int(renderer.scalebar_bg_opacity))
        set_color_button_indicator(editor.bar_color_btn, renderer.bar_color)
        set_color_button_indicator(editor.text_color_btn, renderer.text_color)
        set_color_button_indicator(editor.bg_color_btn, renderer.scalebar_bg_color)

        editor.aperture_checkbox.setChecked(renderer.aperture_enabled)
        editor.aperture_size_combo.setCurrentText(str(renderer.aperture_nominal_size))
        set_color_button_indicator(editor.aperture_color_btn, renderer.aperture_color)

        editor.measurement_checkbox.setChecked(renderer.measurement_enabled)
        editor.measurement_unit_combo.setCurrentText(renderer.measurement_unit)
        editor.measurement_thickness_spinbox.setValue(int(renderer.measurement_line_width))
        editor.measurement_label_checkbox.setChecked(bool(renderer.measurement_show_label))
        editor.measurement_start_end_combo.setCurrentText(renderer.measurement_start_cap)
        editor.measurement_end_end_combo.setCurrentText(renderer.measurement_end_cap)
        set_color_button_indicator(editor.measurement_line_color_btn, renderer.measurement_line_color)
        set_color_button_indicator(editor.measurement_text_color_btn, renderer.measurement_text_color)

    @staticmethod
    def restore_window_state_from_settings(editor: Any):
        """Restore window geometry and splitter layout from persisted settings."""
        window = editor._app_settings.get("window", {})
        try:
            width = max(800, int(window.get("width", 1100)))
            height = max(600, int(window.get("height", 700)))
            editor.resize(width, height)
            editor.move(int(window.get("x", 100)), int(window.get("y", 100)))
        except Exception:
            pass

        splitter_sizes = editor._app_settings.get("splitter_sizes", [900, 350])
        if isinstance(splitter_sizes, list) and len(splitter_sizes) >= 2:
            try:
                editor.main_splitter.setSizes([max(100, int(splitter_sizes[0])), max(100, int(splitter_sizes[1]))])
            except Exception:
                pass

    @staticmethod
    def collect_app_settings(editor: Any) -> dict:
        """Collect current UI/application state for persistence."""
        renderer = editor.overlay_renderer

        settings = {
            "theme_mode": editor._theme_mode,
            "window": {
                "x": int(editor.x()),
                "y": int(editor.y()),
                "width": int(editor.width()),
                "height": int(editor.height()),
            },
            "splitter_sizes": [int(v) for v in editor.main_splitter.sizes()],
            "single_io_directory": str(editor.single_io_directory or ""),
            "batch_input_directory": str(editor.batch_input_directory or ""),
            "batch_output_directory": str(editor.batch_output_directory or ""),
            "overlay": {
                "scalebar_enabled": bool(renderer.scalebar_enabled),
                "scalebar_length_value": float(renderer.scalebar_length_value),
                "scalebar_unit": str(renderer.scalebar_unit),
                "scalebar_thickness": int(renderer.scalebar_thickness),
                "scalebar_position": str(renderer.scalebar_position),
                "bar_color": renderer.bar_color.name(),
                "text_color": renderer.text_color.name(),
                "scalebar_bg_enabled": bool(renderer.scalebar_bg_enabled),
                "scalebar_bg_color": renderer.scalebar_bg_color.name(),
                "scalebar_bg_opacity": int(renderer.scalebar_bg_opacity),
                "aperture_enabled": bool(renderer.aperture_enabled),
                "aperture_nominal_size": int(renderer.aperture_nominal_size),
                "aperture_color": renderer.aperture_color.name(),
                "measurement_enabled": bool(renderer.measurement_enabled),
                "measurement_unit": str(renderer.measurement_unit),
                "measurement_line_color": renderer.measurement_line_color.name(),
                "measurement_text_color": renderer.measurement_text_color.name(),
                "measurement_show_label": bool(renderer.measurement_show_label),
                "measurement_line_width": int(renderer.measurement_line_width),
                "measurement_start_cap": str(editor.measurement_start_end_combo.currentText()),
                "measurement_end_cap": str(editor.measurement_end_end_combo.currentText()),
            },
        }
        return settings

    @staticmethod
    def persist_user_state(editor: Any, persist_presets: bool = True):
        """Persist app settings, and optionally preset payload, to disk."""
        AppSettingsStorage.save_settings(AppStateManager.collect_app_settings(editor))
        if not persist_presets:
            return
        PresetStorage.save_presets(editor.presets)
        if hasattr(editor, "crop_top_spinbox") and hasattr(editor, "crop_bottom_spinbox"):
            PresetStorage.save_crop_defaults(
                int(editor.crop_top_spinbox.value()),
                int(editor.crop_bottom_spinbox.value()),
            )
