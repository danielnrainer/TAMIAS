"""Theme management helpers for the TAMIAS GUI."""

from __future__ import annotations

from typing import Mapping, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QPalette
from PyQt6.QtWidgets import QApplication


class ThemeManager:
    """Encapsulates theme mode and palette application behavior."""

    VALID_MODES = {"auto", "light", "dark"}

    def __init__(self, initial_mode: str = "auto"):
        self.mode = initial_mode if initial_mode in self.VALID_MODES else "auto"

    def sync_action_checks(self, theme_actions: Optional[Mapping[str, QAction]] = None):
        if not theme_actions:
            return
        for mode, action in theme_actions.items():
            action.setChecked(mode == self.mode)

    @staticmethod
    def is_system_dark_mode() -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        try:
            return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except Exception:
            window_color = app.palette().color(QPalette.ColorRole.Window)
            return window_color.lightness() < 128

    @staticmethod
    def create_dark_palette() -> QPalette:
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        pal.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        pal.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        pal.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        pal.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        pal.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        pal.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        pal.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        pal.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        pal.setColor(QPalette.ColorRole.Link, QColor(122, 183, 255))
        pal.setColor(QPalette.ColorRole.LinkVisited, QColor(189, 156, 255))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        pal.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
        return pal

    def apply_theme_mode(self, mode: str, theme_actions: Optional[Mapping[str, QAction]] = None):
        app = QApplication.instance()
        if app is None:
            return

        normalized_mode = mode if mode in self.VALID_MODES else "auto"
        resolved_mode = normalized_mode
        if normalized_mode == "auto":
            resolved_mode = "dark" if self.is_system_dark_mode() else "light"

        if resolved_mode == "dark":
            app.setPalette(self.create_dark_palette())
        else:
            app.setPalette(app.style().standardPalette())

        self.mode = normalized_mode
        self.sync_action_checks(theme_actions)

    def on_system_color_scheme_changed(self, _scheme, theme_actions: Optional[Mapping[str, QAction]] = None):
        if self.mode == "auto":
            self.apply_theme_mode("auto", theme_actions)
