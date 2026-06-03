"""Reusable custom widgets and GUI helper utilities."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QModelIndex, QSize, QItemSelectionModel, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import QDoubleSpinBox, QLabel, QPushButton, QTableWidget


class SmartDoubleSpinBox(QDoubleSpinBox):
    """A QDoubleSpinBox that hides trailing decimals for integer-like values."""

    def textFromValue(self, value: float) -> str:  # type: ignore[override]
        try:
            if abs(value - round(value)) < 1e-9:
                return str(int(round(value)))
            return (f"{value:.2f}").rstrip("0").rstrip(".")
        except Exception:
            return super().textFromValue(value)


class ImageDisplayLabel(QLabel):
    """Image label that supports draw mode and drag mode mouse signals."""

    clicked = pyqtSignal(int, int)
    mouse_pressed = pyqtSignal(int, int)
    mouse_moved = pyqtSignal(int, int)
    mouse_released = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._draw_mode = False
        self._label_drag_mode = False

    def set_draw_mode(self, active: bool):
        self._draw_mode = active
        self._label_drag_mode = False
        self.setCursor(Qt.CursorShape.CrossCursor if active else Qt.CursorShape.ArrowCursor)

    def set_label_drag_mode(self, active: bool):
        self._label_drag_mode = active
        self._draw_mode = False
        self.setCursor(Qt.CursorShape.OpenHandCursor if active else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            x, y = int(event.position().x()), int(event.position().y())
            if self._draw_mode or self._label_drag_mode:
                self.mouse_pressed.emit(x, y)
                if self._label_drag_mode:
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
            else:
                self.clicked.emit(x, y)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._draw_mode or self._label_drag_mode) and (event.buttons() & Qt.MouseButton.LeftButton):
            self.mouse_moved.emit(int(event.position().x()), int(event.position().y()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and (self._draw_mode or self._label_drag_mode):
            self.mouse_released.emit(int(event.position().x()), int(event.position().y()))
            if self._label_drag_mode:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


class ClickClearTableWidget(QTableWidget):
    """A QTableWidget that clears selection when clicking empty table space."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._toggle_deselect_excluded_columns: set[int] = set()

    def set_toggle_deselect_excluded_columns(self, columns: list[int] | set[int] | tuple[int, ...]):
        """Columns where clicking a selected row should not toggle deselection."""
        self._toggle_deselect_excluded_columns = {int(col) for col in columns}

    def mousePressEvent(self, event):  # type: ignore[override]
        idx = self.indexAt(event.pos())
        if (
            event.button() == Qt.MouseButton.LeftButton
            and idx.isValid()
            and idx.column() not in self._toggle_deselect_excluded_columns
            and self.selectionModel() is not None
            and self.selectionModel().isRowSelected(idx.row(), QModelIndex())
            and not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        ):
            # Toggle off a selected row on plain click.
            self.selectionModel().select(
                idx,
                QItemSelectionModel.SelectionFlag.Deselect | QItemSelectionModel.SelectionFlag.Rows,
            )
            remaining_rows = self.selected_rows()
            if remaining_rows:
                self.setCurrentCell(remaining_rows[0], 0)
            else:
                self.setCurrentIndex(QModelIndex())
            event.accept()
            return
        if not idx.isValid():
            self.clearSelection()
            self.setCurrentIndex(QModelIndex())
        super().mousePressEvent(event)

    def selected_rows(self) -> list[int]:
        """Return selected row indices in ascending order."""
        rows = {idx.row() for idx in self.selectionModel().selectedRows()}
        return sorted(rows)


def set_color_button_indicator(button: QPushButton, color: QColor):
    """Show a small color swatch icon on color-picker buttons."""
    swatch_size = 14
    pixmap = QPixmap(swatch_size, swatch_size)
    pixmap.fill(QColor(color))
    button.setIcon(QIcon(pixmap))
    button.setIconSize(QSize(swatch_size, swatch_size))
