"""Crop UI and interaction controller mixin for the main editor window."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QDialog,
)

from core.crop_geometry import (
    center_rect,
    constrain_endpoint,
    move_rect_within_bounds,
    normalize_rect,
    point_in_rect,
    rect_size,
)
from gui.collapsible_box import QCollapsibleBox
from gui.crop_dialog import TopBottomCropDialog


class CropControllerMixin:
    """Adds top/bottom and manual crop behavior to the main editor."""

    def _init_crop_state(self):
        self._manual_crop_mode_active = False
        self._manual_crop_move_mode_active = False
        self._manual_crop_start: Optional[tuple[int, int]] = None
        self._manual_crop_end: Optional[tuple[int, int]] = None
        self._manual_crop_drag_active = False
        self._manual_crop_drag_origin_img: Optional[tuple[int, int]] = None
        self._manual_crop_drag_start_start: Optional[tuple[int, int]] = None
        self._manual_crop_drag_start_end: Optional[tuple[int, int]] = None

    def _setup_crop_controls(self, parent_layout):
        """Setup top/bottom and manual image cropping controls."""
        crop_box = QCollapsibleBox("Image Cropping", expanded=False)
        crop_layout = QVBoxLayout()

        rows_layout = QHBoxLayout()
        rows_layout.addWidget(QLabel("Top rows:"))
        self.crop_top_spinbox = QSpinBox()
        self.crop_top_spinbox.setRange(0, 100000)
        self.crop_top_spinbox.setValue(10)
        rows_layout.addWidget(self.crop_top_spinbox)

        rows_layout.addWidget(QLabel("Bottom rows:"))
        self.crop_bottom_spinbox = QSpinBox()
        self.crop_bottom_spinbox.setRange(0, 100000)
        self.crop_bottom_spinbox.setValue(10)
        rows_layout.addWidget(self.crop_bottom_spinbox)
        crop_layout.addLayout(rows_layout)

        apply_crop_btn = QPushButton("Apply Top/Bottom Crop")
        apply_crop_btn.clicked.connect(self.apply_sidebar_crop)
        crop_layout.addWidget(apply_crop_btn)

        self.manual_crop_select_btn = QPushButton("Select Manual Crop Region")
        self.manual_crop_select_btn.setCheckable(True)
        self.manual_crop_select_btn.toggled.connect(self.on_manual_crop_mode_toggled)
        crop_layout.addWidget(self.manual_crop_select_btn)

        constraint_layout = QHBoxLayout()
        constraint_layout.addWidget(QLabel("Selection shape:"))
        self.manual_crop_constraint_combo = QComboBox()
        self.manual_crop_constraint_combo.addItems(["Free", "Square", "Keep Aspect Ratio"])
        self.manual_crop_constraint_combo.currentTextChanged.connect(self.on_manual_crop_constraint_changed)
        constraint_layout.addWidget(self.manual_crop_constraint_combo)
        crop_layout.addLayout(constraint_layout)

        ratio_layout = QHBoxLayout()
        ratio_layout.addWidget(QLabel("Aspect:"))
        self.manual_crop_aspect_w_spinbox = QSpinBox()
        self.manual_crop_aspect_w_spinbox.setRange(1, 1000)
        self.manual_crop_aspect_w_spinbox.setValue(2)
        ratio_layout.addWidget(self.manual_crop_aspect_w_spinbox)
        ratio_layout.addWidget(QLabel(":"))
        self.manual_crop_aspect_h_spinbox = QSpinBox()
        self.manual_crop_aspect_h_spinbox.setRange(1, 1000)
        self.manual_crop_aspect_h_spinbox.setValue(1)
        ratio_layout.addWidget(self.manual_crop_aspect_h_spinbox)
        crop_layout.addLayout(ratio_layout)

        self.manual_crop_center_checkbox = QCheckBox("Keep selection centered on image")
        self.manual_crop_center_checkbox.setChecked(False)
        self.manual_crop_center_checkbox.stateChanged.connect(self.on_manual_crop_center_toggled)
        crop_layout.addWidget(self.manual_crop_center_checkbox)

        self.manual_crop_move_btn = QPushButton("Move Manual Crop Region")
        self.manual_crop_move_btn.setCheckable(True)
        self.manual_crop_move_btn.toggled.connect(self.on_manual_crop_move_mode_toggled)
        crop_layout.addWidget(self.manual_crop_move_btn)

        self.clear_manual_crop_btn = QPushButton("Clear Manual Crop Region")
        self.clear_manual_crop_btn.clicked.connect(self.clear_manual_crop_selection)
        self.clear_manual_crop_btn.setEnabled(False)
        crop_layout.addWidget(self.clear_manual_crop_btn)

        self.apply_manual_crop_btn = QPushButton("Apply Manual Crop")
        self.apply_manual_crop_btn.clicked.connect(self.apply_manual_crop)
        crop_layout.addWidget(self.apply_manual_crop_btn)

        self.on_manual_crop_constraint_changed(self.manual_crop_constraint_combo.currentText())

        crop_box.setContentLayout(crop_layout)
        crop_box.toggleButton.toggled.connect(self._on_crop_section_toggled)
        parent_layout.addWidget(crop_box)

    def _on_crop_section_toggled(self, expanded: bool):
        """Turn off crop interaction modes when the crop section is collapsed."""
        if expanded:
            return
        if hasattr(self, "manual_crop_select_btn") and self.manual_crop_select_btn.isChecked():
            self.manual_crop_select_btn.setChecked(False)
        if hasattr(self, "manual_crop_move_btn") and self.manual_crop_move_btn.isChecked():
            self.manual_crop_move_btn.setChecked(False)

    def is_crop_draw_active(self) -> bool:
        return bool(self._manual_crop_mode_active)

    def is_crop_move_active(self) -> bool:
        return bool(self._manual_crop_move_mode_active)

    def has_manual_crop_selection(self) -> bool:
        if self._manual_crop_start is None or self._manual_crop_end is None:
            return False
        return self._is_manual_crop_selection_large_enough()

    def _is_manual_crop_selection_large_enough(self) -> bool:
        rect = normalize_rect(self._manual_crop_start, self._manual_crop_end)
        width, height = rect_size(rect)
        return (width * height) > 4

    def _update_manual_crop_clear_button_state(self):
        if hasattr(self, "clear_manual_crop_btn"):
            self.clear_manual_crop_btn.setEnabled(self.has_manual_crop_selection())

    def crop_overlay_rect(self) -> Optional[tuple[int, int, int, int]]:
        if not self.has_manual_crop_selection():
            return None
        return normalize_rect(self._manual_crop_start, self._manual_crop_end)

    def draw_manual_crop_overlay(self, q_image: QImage):
        rect = self.crop_overlay_rect()
        if rect is None:
            return
        x1, y1, x2, y2 = rect
        width, height = rect_size(rect)

        painter = QPainter(q_image)
        pen = QPen(QColor(255, 220, 0))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(x1, y1, max(1, width - 1), max(1, height - 1))
        painter.end()

    def reset_crop_state(self):
        self._manual_crop_start = None
        self._manual_crop_end = None
        self._manual_crop_mode_active = False
        self._manual_crop_move_mode_active = False
        self._manual_crop_drag_active = False
        self._manual_crop_drag_origin_img = None
        self._manual_crop_drag_start_start = None
        self._manual_crop_drag_start_end = None
        if hasattr(self, "manual_crop_select_btn") and self.manual_crop_select_btn.isChecked():
            self.manual_crop_select_btn.blockSignals(True)
            self.manual_crop_select_btn.setChecked(False)
            self.manual_crop_select_btn.blockSignals(False)
        if hasattr(self, "manual_crop_move_btn") and self.manual_crop_move_btn.isChecked():
            self.manual_crop_move_btn.blockSignals(True)
            self.manual_crop_move_btn.setChecked(False)
            self.manual_crop_move_btn.blockSignals(False)
        self._update_manual_crop_clear_button_state()

    def clear_manual_crop_selection(self):
        """Clear currently selected manual crop rectangle."""
        had_selection = self._manual_crop_start is not None and self._manual_crop_end is not None
        self._manual_crop_start = None
        self._manual_crop_end = None
        self._manual_crop_drag_active = False
        self._manual_crop_drag_origin_img = None
        self._manual_crop_drag_start_start = None
        self._manual_crop_drag_start_end = None
        self._update_manual_crop_clear_button_state()
        self.update_display()
        if had_selection:
            self.measurement_status_label.setText("Manual crop selection cleared.")
        else:
            self.measurement_status_label.setText("No manual crop selection to clear.")

    def crop_handle_mouse_press(self, x: int, y: int) -> bool:
        if self.is_crop_move_active():
            mapped = self._map_label_to_image_coords(x, y)
            if mapped is None:
                return True
            rect = self.crop_overlay_rect()
            if rect is None or not point_in_rect(mapped, rect):
                self.measurement_status_label.setText("Click inside the crop rectangle to move it.")
                return True
            self._manual_crop_drag_active = True
            self._manual_crop_drag_origin_img = mapped
            self._manual_crop_drag_start_start = self._manual_crop_start
            self._manual_crop_drag_start_end = self._manual_crop_end
            return True

        if self.is_crop_draw_active():
            mapped = self._map_label_to_image_coords(x, y)
            if mapped is None:
                return True
            self._manual_crop_start = mapped
            self._manual_crop_end = mapped
            self._update_manual_crop_clear_button_state()
            self.update_display()
            return True

        return False

    def crop_handle_mouse_move(self, x: int, y: int) -> bool:
        if self.is_crop_move_active():
            if not self._manual_crop_drag_active:
                return True
            mapped = self._map_label_to_image_coords(x, y)
            if mapped is None:
                return True
            self._move_manual_crop_rect(mapped)
            self.update_display()
            return True

        if self.is_crop_draw_active():
            if self._manual_crop_start is None:
                return True
            mapped = self._map_label_to_image_coords(x, y)
            if mapped is None:
                return True
            self._manual_crop_end = self._constrain_manual_crop_endpoint(self._manual_crop_start, mapped)
            if self.manual_crop_center_checkbox.isChecked():
                self._center_manual_crop_selection()
            self._update_manual_crop_clear_button_state()
            self.update_display()
            return True

        return False

    def crop_handle_mouse_release(self, x: int, y: int) -> bool:
        if self.is_crop_move_active():
            if self._manual_crop_drag_active:
                mapped = self._map_label_to_image_coords(x, y)
                if mapped is not None:
                    self._move_manual_crop_rect(mapped)
                self._manual_crop_drag_active = False
                self._manual_crop_drag_origin_img = None
                self._manual_crop_drag_start_start = None
                self._manual_crop_drag_start_end = None
                self.update_display()
            return True

        if self.is_crop_draw_active():
            if self._manual_crop_start is None:
                return True
            mapped = self._map_label_to_image_coords(x, y)
            if mapped is not None:
                self._manual_crop_end = self._constrain_manual_crop_endpoint(self._manual_crop_start, mapped)
                if self.manual_crop_center_checkbox.isChecked():
                    self._center_manual_crop_selection()
            if not self.has_manual_crop_selection():
                self.clear_manual_crop_selection()
                self.measurement_status_label.setText(
                    "Manual crop selection cleared. Selected area must be larger than 4 px."
                )
            else:
                self._update_manual_crop_clear_button_state()
            self.update_display()
            return True

        return False

    def crop_top_bottom_rows(self):
        """Crop rows from the top and bottom of the currently loaded image."""
        if not self.image_processor.has_image():
            QMessageBox.warning(self, "Warning", "Load an image before cropping.")
            return

        current_image = self.image_processor.get_current_image()
        if current_image is None:
            QMessageBox.warning(self, "Warning", "No image data available for cropping.")
            return

        image_height, image_width = current_image.shape
        dialog = TopBottomCropDialog(image_width=image_width, image_height=image_height, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        top_rows, bottom_rows = dialog.get_crop_values()
        self._apply_top_bottom_crop(top_rows=top_rows, bottom_rows=bottom_rows, source_label="dialog")

    def apply_sidebar_crop(self):
        """Apply crop values from the right-hand side panel."""
        top_rows = int(self.crop_top_spinbox.value())
        bottom_rows = int(self.crop_bottom_spinbox.value())
        self._apply_top_bottom_crop(top_rows=top_rows, bottom_rows=bottom_rows, source_label="side panel")

    def on_manual_crop_mode_toggled(self, checked: bool):
        """Toggle manual rectangle selection mode for cropping."""
        self._manual_crop_mode_active = checked
        if checked:
            if hasattr(self, "manual_crop_move_btn") and self.manual_crop_move_btn.isChecked():
                self.manual_crop_move_btn.blockSignals(True)
                self.manual_crop_move_btn.setChecked(False)
                self.manual_crop_move_btn.blockSignals(False)
                self._manual_crop_move_mode_active = False
            self.draw_measurement_btn.blockSignals(True)
            self.draw_measurement_btn.setChecked(False)
            self.draw_measurement_btn.blockSignals(False)
            self._draw_mode_active = False
            self.move_label_btn.blockSignals(True)
            self.move_label_btn.setChecked(False)
            self.move_label_btn.blockSignals(False)
            self._label_drag_active = False
            self.move_line_btn.blockSignals(True)
            self.move_line_btn.setChecked(False)
            self.move_line_btn.blockSignals(False)
            self._line_drag_active = False
            self.move_scalebar_btn.blockSignals(True)
            self.move_scalebar_btn.setChecked(False)
            self.move_scalebar_btn.blockSignals(False)
            self._scalebar_drag_active = False
            self.measurement_status_label.setText(
                "Manual crop mode ON — drag on the image to define crop region, then click 'Apply Manual Crop'."
            )
        else:
            self._manual_crop_drag_active = False
            self._manual_crop_drag_origin_img = None
            self.measurement_status_label.setText("Manual crop mode off.")
        self._refresh_image_interaction_mode()
        self.update_display()

    def on_manual_crop_move_mode_toggled(self, checked: bool):
        """Toggle moving an already-selected manual crop rectangle."""
        self._manual_crop_move_mode_active = checked
        if checked:
            if self.manual_crop_center_checkbox.isChecked():
                self._manual_crop_move_mode_active = False
                self.manual_crop_move_btn.blockSignals(True)
                self.manual_crop_move_btn.setChecked(False)
                self.manual_crop_move_btn.blockSignals(False)
                QMessageBox.information(self, "Manual Crop", "Disable centered selection before moving the crop region.")
                return
            if hasattr(self, "manual_crop_select_btn") and self.manual_crop_select_btn.isChecked():
                self.manual_crop_select_btn.blockSignals(True)
                self.manual_crop_select_btn.setChecked(False)
                self.manual_crop_select_btn.blockSignals(False)
                self._manual_crop_mode_active = False
            self.draw_measurement_btn.blockSignals(True)
            self.draw_measurement_btn.setChecked(False)
            self.draw_measurement_btn.blockSignals(False)
            self._draw_mode_active = False
            self.move_label_btn.blockSignals(True)
            self.move_label_btn.setChecked(False)
            self.move_label_btn.blockSignals(False)
            self._label_drag_active = False
            self.move_line_btn.blockSignals(True)
            self.move_line_btn.setChecked(False)
            self.move_line_btn.blockSignals(False)
            self._line_drag_active = False
            self.move_scalebar_btn.blockSignals(True)
            self.move_scalebar_btn.setChecked(False)
            self.move_scalebar_btn.blockSignals(False)
            self._scalebar_drag_active = False
            self.measurement_status_label.setText(
                "Move Manual Crop mode ON — drag inside the selected crop region to reposition it."
            )
        else:
            self._manual_crop_drag_active = False
            self._manual_crop_drag_origin_img = None
            self.measurement_status_label.setText("Move Manual Crop mode off.")
        self._refresh_image_interaction_mode()
        self.update_display()

    def on_manual_crop_constraint_changed(self, mode: str):
        """Enable aspect ratio inputs only for keep-aspect constraint mode."""
        enabled = mode == "Keep Aspect Ratio"
        self.manual_crop_aspect_w_spinbox.setEnabled(enabled)
        self.manual_crop_aspect_h_spinbox.setEnabled(enabled)

    def on_manual_crop_center_toggled(self, state: int):
        """Keep crop selection centered on image when enabled."""
        enabled = state == Qt.CheckState.Checked.value
        self.manual_crop_move_btn.setEnabled(not enabled)
        if enabled:
            if self.manual_crop_move_btn.isChecked():
                self.manual_crop_move_btn.blockSignals(True)
                self.manual_crop_move_btn.setChecked(False)
                self.manual_crop_move_btn.blockSignals(False)
                self._manual_crop_move_mode_active = False
            self._center_manual_crop_selection()
            self.measurement_status_label.setText("Centered crop enabled — selection remains centered on image.")
        else:
            self.measurement_status_label.setText("Centered crop disabled.")
        self._refresh_image_interaction_mode()
        self.update_display()

    def _get_manual_crop_constraint_mode(self) -> str:
        return self.manual_crop_constraint_combo.currentText() if hasattr(self, "manual_crop_constraint_combo") else "Free"

    def _get_manual_crop_aspect_ratio(self) -> float:
        w = max(1, int(self.manual_crop_aspect_w_spinbox.value()))
        h = max(1, int(self.manual_crop_aspect_h_spinbox.value()))
        return float(w) / float(h)

    def _constrain_manual_crop_endpoint(self, start: tuple[int, int], candidate: tuple[int, int]) -> tuple[int, int]:
        """Constrain selection endpoint based on current crop shape mode and image bounds."""
        current = self.image_processor.get_current_image()
        if current is None:
            return candidate
        img_h, img_w = current.shape
        return constrain_endpoint(
            start=start,
            candidate=candidate,
            mode=self._get_manual_crop_constraint_mode(),
            aspect_ratio=self._get_manual_crop_aspect_ratio(),
            img_w=img_w,
            img_h=img_h,
        )

    def _center_manual_crop_selection(self):
        """Recenter current selection on the image while preserving size."""
        rect = self.crop_overlay_rect()
        current = self.image_processor.get_current_image()
        if rect is None or current is None:
            return
        img_h, img_w = current.shape
        centered = center_rect(rect, img_w=img_w, img_h=img_h)
        self._manual_crop_start = (centered[0], centered[1])
        self._manual_crop_end = (centered[2], centered[3])

    def _move_manual_crop_rect(self, current_point: tuple[int, int]):
        """Move existing manual crop rectangle by dragging while keeping it in image bounds."""
        if (
            not self._manual_crop_drag_active
            or self._manual_crop_drag_origin_img is None
            or self._manual_crop_drag_start_start is None
            or self._manual_crop_drag_start_end is None
        ):
            return
        current = self.image_processor.get_current_image()
        if current is None:
            return
        if self.manual_crop_center_checkbox.isChecked():
            return

        img_h, img_w = current.shape
        start_rect = normalize_rect(self._manual_crop_drag_start_start, self._manual_crop_drag_start_end)
        dx = int(current_point[0]) - int(self._manual_crop_drag_origin_img[0])
        dy = int(current_point[1]) - int(self._manual_crop_drag_origin_img[1])
        moved = move_rect_within_bounds(start_rect, dx=dx, dy=dy, img_w=img_w, img_h=img_h)
        self._manual_crop_start = (moved[0], moved[1])
        self._manual_crop_end = (moved[2], moved[3])

    def apply_manual_crop(self):
        """Apply crop from the currently selected manual rectangle."""
        if not self.image_processor.has_image():
            QMessageBox.warning(self, "Warning", "Load an image before cropping.")
            return
        rect = self.crop_overlay_rect()
        if rect is None:
            QMessageBox.information(self, "Manual Crop", "Select a crop region first.")
            return

        x1, y1, x2, y2 = rect
        crop_width, crop_height = rect_size(rect)
        if (crop_width * crop_height) <= 4:
            QMessageBox.warning(self, "Manual Crop", "Selected region is too small to crop.")
            return

        if not self._confirm_crop_operation(
            title="Apply Manual Crop?",
            message=(
                "Apply manual crop to selected region?\n\n"
                f"X: {x1} to {x2} ({crop_width} px)\n"
                f"Y: {y1} to {y2} ({crop_height} px)"
            ),
        ):
            return

        success, error, dimensions = self.image_processor.crop_rectangle(
            left=x1,
            top=y1,
            right=x2 + 1,
            bottom=y2 + 1,
        )
        if not success:
            QMessageBox.warning(self, "Crop Failed", error or "Unable to crop the image.")
            return

        if dimensions is not None:
            width, height = dimensions
        else:
            fallback = self.image_processor.get_current_image()
            if fallback is None:
                width, height = (0, 0)
            else:
                height, width = fallback.shape

        self._manual_crop_start = None
        self._manual_crop_end = None
        self._update_manual_crop_clear_button_state()
        self._reset_image_specific_overlays(disable_scalebar=False)
        self._last_rendered_image_size = None
        self._refresh_scale_information()

        filename = Path(self.current_file).name if self.current_file else "(unsaved image)"
        self.file_info_label.setText(
            f"File: {filename} | Size: {width}x{height}px | Manual crop applied"
        )
        self.measurement_status_label.setText("Manual crop applied.")

    def _confirm_crop_operation(self, title: str, message: str) -> bool:
        """Show a confirmation prompt before mutating image geometry."""
        answer = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _apply_top_bottom_crop(self, top_rows: int, bottom_rows: int, source_label: str):
        """Apply top/bottom crop and refresh image/UI state."""
        if not self.image_processor.has_image():
            QMessageBox.warning(self, "Warning", "Load an image before cropping.")
            return

        if top_rows == 0 and bottom_rows == 0:
            QMessageBox.information(self, "Image Cropping", "Top and bottom crop are both 0. Nothing to apply.")
            return

        current = self.image_processor.get_current_image()
        if current is not None:
            current_height, current_width = current.shape
        else:
            current_width, current_height = (0, 0)
        result_height = current_height - top_rows - bottom_rows

        if not self._confirm_crop_operation(
            title="Apply Top/Bottom Crop?",
            message=(
                "Apply top/bottom crop now?\n\n"
                f"Top: {top_rows} px\n"
                f"Bottom: {bottom_rows} px\n"
                f"Current size: {current_width} x {current_height} px\n"
                f"Result height: {result_height} px"
            ),
        ):
            return

        success, error, dimensions = self.image_processor.crop_rows(top_rows=top_rows, bottom_rows=bottom_rows)
        if not success:
            QMessageBox.warning(self, "Crop Failed", error or "Unable to crop the image.")
            return

        if dimensions is not None:
            width, height = dimensions
        else:
            fallback = self.image_processor.get_current_image()
            if fallback is None:
                width, height = (0, 0)
            else:
                height, width = fallback.shape
        self._reset_image_specific_overlays(disable_scalebar=False)
        self._last_rendered_image_size = None
        self._refresh_scale_information()

        filename = Path(self.current_file).name if self.current_file else "(unsaved image)"
        self.file_info_label.setText(
            f"File: {filename} | Size: {width}x{height}px | Cropped top {top_rows}px, bottom {bottom_rows}px"
        )
        self.measurement_status_label.setText(
            f"Image cropped from {source_label}: top {top_rows}px, bottom {bottom_rows}px."
        )
