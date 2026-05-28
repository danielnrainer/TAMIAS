"""Dialog for cropping rows from the top and bottom of an image."""

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


class TopBottomCropDialog(QDialog):
    """Collect top/bottom row crop counts and confirm resulting size."""

    def __init__(self, image_width: int, image_height: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crop Top/Bottom Rows")
        self.setModal(True)

        self._image_width = int(image_width)
        self._image_height = int(image_height)

        max_rows = max(0, self._image_height - 1)

        self.top_rows_spin = QSpinBox()
        self.top_rows_spin.setRange(0, max_rows)
        self.top_rows_spin.setValue(min(10, max_rows))
        self.top_rows_spin.valueChanged.connect(self._update_preview)

        self.bottom_rows_spin = QSpinBox()
        self.bottom_rows_spin.setRange(0, max_rows)
        self.bottom_rows_spin.setValue(min(9, max_rows))
        self.bottom_rows_spin.valueChanged.connect(self._update_preview)

        self.original_size_label = QLabel(
            f"Original size: {self._image_width} x {self._image_height} px"
        )
        self.result_size_label = QLabel()
        self.warning_label = QLabel(
            "Note: Existing measurement annotations and custom scalebar offset will be reset."
        )
        self.warning_label.setWordWrap(True)

        form_layout = QFormLayout()
        form_layout.addRow("Top rows:", self.top_rows_spin)
        form_layout.addRow("Bottom rows:", self.bottom_rows_spin)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.original_size_label)
        layout.addLayout(form_layout)
        layout.addWidget(self.result_size_label)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

        self._update_preview()

    def get_crop_values(self) -> tuple[int, int]:
        """Return selected top and bottom row crop values."""
        return self.top_rows_spin.value(), self.bottom_rows_spin.value()

    def _update_preview(self):
        """Update result-size text and disable OK on invalid crop amounts."""
        top_rows, bottom_rows = self.get_crop_values()
        remaining_height = self._image_height - top_rows - bottom_rows
        self.result_size_label.setText(
            f"Result size: {self._image_width} x {remaining_height} px"
        )

        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(remaining_height > 0)
