from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QCursor, QPalette

class QCollapsibleBox(QWidget):
    """A custom collapsible box widget"""
    
    def __init__(self, title="", parent=None, expanded=True):
        super().__init__(parent)
        
        self.title = title
        # Set initial arrow based on expanded state
        arrow = "▼" if expanded else "▶"
        self.toggleButton = QPushButton(f"{arrow} {title}")
        self.toggleButton.setStyleSheet("text-align: left; padding: 5px;")
        self.toggleButton.setCheckable(True)
        self.toggleButton.setChecked(expanded)
        self.toggleButton.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        self.contentWidget = QWidget()
        self.contentWidget.setVisible(expanded)
        
        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggleButton)
        lay.addWidget(self.contentWidget)
        
        self.toggleButton.toggled.connect(self.toggle)

    def _build_toggle_stylesheet(self) -> str:
        """Build a palette-aware stylesheet for readable contrast in light/dark themes."""
        pal = self.palette()
        window_color = pal.color(QPalette.ColorRole.Window)
        text_color = pal.color(QPalette.ColorRole.WindowText)

        is_dark = window_color.lightness() < 128
        bg_color = window_color.lighter(120) if is_dark else window_color.darker(105)
        border_color = bg_color.lighter(135) if is_dark else bg_color.darker(125)
        hover_color = bg_color.lighter(112) if is_dark else bg_color.darker(108)
        pressed_color = bg_color.lighter(122) if is_dark else bg_color.darker(116)

        return f"""
            QPushButton {{
                text-align: left;
                padding: 6px 8px;
                margin: 0px;
                border: 1px solid {border_color.name(QColor.NameFormat.HexRgb)};
                background-color: {bg_color.name(QColor.NameFormat.HexRgb)};
                color: {text_color.name(QColor.NameFormat.HexRgb)};
                border-radius: 3px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {hover_color.name(QColor.NameFormat.HexRgb)};
                border: 1px solid {border_color.name(QColor.NameFormat.HexRgb)};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color.name(QColor.NameFormat.HexRgb)};
            }}
        """

    def _apply_toggle_button_style(self):
        self.toggleButton.setStyleSheet(self._build_toggle_stylesheet())

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (event.Type.PaletteChange, event.Type.ApplicationPaletteChange):
            self._apply_toggle_button_style()
    
    def toggle(self, checked):
        self.contentWidget.setVisible(checked)
        # Update the arrow icon based on expanded/collapsed state
        if checked:
            self.toggleButton.setText(f"▼ {self.title}")
        else:
            self.toggleButton.setText(f"▶ {self.title}")

    def setTitle(self, title: str):
        """Update the section title while preserving expanded/collapsed state."""
        self.title = title
        self.toggle(self.toggleButton.isChecked())
        
    def setContentLayout(self, layout):
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        self.contentWidget.setLayout(layout)

        self._apply_toggle_button_style()
