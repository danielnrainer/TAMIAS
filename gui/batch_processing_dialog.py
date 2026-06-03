"""Batch processing dialog for applying overlays and exports across multiple images."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QColorDialog,
)

from core.image_processor import ImageProcessor
from core.overlay_renderer import OverlayRenderer
from gui.collapsible_box import QCollapsibleBox
from gui.custom_widgets import SmartDoubleSpinBox, set_color_button_indicator
from utils.imaging_mode_defaults import get_mode_overlay_defaults


class BatchProcessingDialog(QDialog):
    """Dialog for batch processing of multiple images."""

    def __init__(
        self,
        presets: dict,
        renderer: OverlayRenderer,
        parent=None,
        initial_input_directory: str = "",
        initial_output_directory: str = "",
        default_crop_top_rows: int = 10,
        default_crop_bottom_rows: int = 9,
    ):
        super().__init__(parent)
        self.setWindowTitle("Batch Processing")
        self.setModal(True)
        self.resize(450, 700)

        self.presets = presets
        self.renderer = renderer
        self.files = []
        self.last_input_directory = str(initial_input_directory or "")
        self.last_output_directory = str(initial_output_directory or "")
        self.default_crop_top_rows = max(0, int(default_crop_top_rows))
        self.default_crop_bottom_rows = max(0, int(default_crop_bottom_rows))

        self._setup_ui()

    def _setup_ui(self):
        """Setup the batch dialog UI."""
        root_layout = QVBoxLayout()

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        layout = QVBoxLayout()
        scroll_content.setLayout(layout)

        file_group = QGroupBox("Select Files")
        file_layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        add_files_btn = QPushButton("Add Files...")
        add_files_btn.clicked.connect(self._add_files)
        btn_layout.addWidget(add_files_btn)

        remove_files_btn = QPushButton("Remove Selected")
        remove_files_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(remove_files_btn)

        clear_files_btn = QPushButton("Clear All")
        clear_files_btn.clicked.connect(self._clear_files)
        btn_layout.addWidget(clear_files_btn)

        file_layout.addLayout(btn_layout)

        self.file_list = QListWidget()
        file_layout.addWidget(self.file_list)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        params_group = QGroupBox("Annotation Parameters")
        params_layout = QVBoxLayout()

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(sorted(self.presets.keys()))
        self.preset_combo.setCurrentText("Standard")
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_layout.addWidget(self.preset_combo)
        params_layout.addLayout(preset_layout)

        pixel_layout = QHBoxLayout()
        pixel_layout.addWidget(QLabel("Pixel size:"))
        self.pixel_size_spinbox = QDoubleSpinBox()
        self.pixel_size_spinbox.setRange(0.00001, 100000.0)
        self.pixel_size_spinbox.setDecimals(3)
        self.pixel_size_spinbox.setValue(35.6)
        pixel_layout.addWidget(self.pixel_size_spinbox)

        self.pixel_unit_combo = QComboBox()
        self.pixel_unit_combo.addItems(["nm", "µm"])
        pixel_layout.addWidget(self.pixel_unit_combo)
        params_layout.addLayout(pixel_layout)

        crop_box = QCollapsibleBox("Image Cropping", expanded=False)
        self.batch_crop_box = crop_box
        crop_layout = QVBoxLayout()

        self.batch_auto_crop_checkbox = QCheckBox("Enable top/bottom row crop")
        self.batch_auto_crop_checkbox.setChecked(True)
        self.batch_auto_crop_checkbox.stateChanged.connect(self._update_batch_section_titles)
        crop_layout.addWidget(self.batch_auto_crop_checkbox)

        crop_rows_layout = QHBoxLayout()
        crop_rows_layout.addWidget(QLabel("Top rows:"))
        self.batch_crop_top_spinbox = QSpinBox()
        self.batch_crop_top_spinbox.setRange(0, 100000)
        self.batch_crop_top_spinbox.setValue(self.default_crop_top_rows)
        crop_rows_layout.addWidget(self.batch_crop_top_spinbox)

        crop_rows_layout.addWidget(QLabel("Bottom rows:"))
        self.batch_crop_bottom_spinbox = QSpinBox()
        self.batch_crop_bottom_spinbox.setRange(0, 100000)
        self.batch_crop_bottom_spinbox.setValue(self.default_crop_bottom_rows)
        crop_rows_layout.addWidget(self.batch_crop_bottom_spinbox)
        crop_layout.addLayout(crop_rows_layout)

        crop_hint = QLabel("Applied immediately after image load and before adjustments/overlays.")
        crop_hint.setWordWrap(True)
        crop_hint.setStyleSheet("font-style: italic")
        crop_layout.addWidget(crop_hint)

        crop_box.setContentLayout(crop_layout)
        params_layout.addWidget(crop_box)

        self.auto_bc_checkbox = QCheckBox("Auto-adjust brightness/contrast")
        self.auto_bc_checkbox.setChecked(True)
        params_layout.addWidget(self.auto_bc_checkbox)

        scalebar_group = QCollapsibleBox("Scalebar", expanded=False)
        self.batch_scalebar_box = scalebar_group
        scalebar_layout = QVBoxLayout()

        self.scalebar_checkbox = QCheckBox("Add scalebar")
        self.scalebar_checkbox.setChecked(True)
        self.scalebar_checkbox.stateChanged.connect(self._update_batch_section_titles)
        scalebar_layout.addWidget(self.scalebar_checkbox)

        length_layout = QHBoxLayout()
        length_layout.addWidget(QLabel("Length:"))
        self.scalebar_length_spinbox = SmartDoubleSpinBox()
        self.scalebar_length_spinbox.setDecimals(2)
        self.scalebar_length_spinbox.setSingleStep(0.1)
        self.scalebar_length_spinbox.setRange(0.01, 10000.0)
        self.scalebar_length_spinbox.setValue(5.0)
        try:
            self.scalebar_length_spinbox.lineEdit().textEdited.connect(self._on_batch_scalebar_length_text_edited)
        except Exception:
            pass
        length_layout.addWidget(self.scalebar_length_spinbox)

        self.scalebar_unit_combo = QComboBox()
        self.scalebar_unit_combo.addItems(["nm", "µm"])
        self.scalebar_unit_combo.setCurrentText("µm")
        length_layout.addWidget(self.scalebar_unit_combo)
        scalebar_layout.addLayout(length_layout)

        thickness_layout = QHBoxLayout()
        thickness_layout.addWidget(QLabel("Thickness (px):"))
        self.scalebar_thickness_spinbox = QSpinBox()
        self.scalebar_thickness_spinbox.setRange(5, 100)
        self.scalebar_thickness_spinbox.setValue(self.renderer.scalebar_thickness)
        thickness_layout.addWidget(self.scalebar_thickness_spinbox)
        scalebar_layout.addLayout(thickness_layout)

        position_layout = QHBoxLayout()
        position_layout.addWidget(QLabel("Position:"))
        self.position_combo = QComboBox()
        self.position_combo.addItems(["bottom-right", "bottom-left", "top-right", "top-left"])
        self.position_combo.setCurrentText(self.renderer.scalebar_position)
        position_layout.addWidget(self.position_combo)
        scalebar_layout.addLayout(position_layout)

        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Bar color:"))
        self.bar_color_btn = QPushButton("Choose...")
        self.bar_color = QColor(self.renderer.bar_color)
        self.bar_color_btn.clicked.connect(self._choose_bar_color)
        set_color_button_indicator(self.bar_color_btn, self.bar_color)
        color_layout.addWidget(self.bar_color_btn)

        color_layout.addWidget(QLabel("Text color:"))
        self.text_color_btn = QPushButton("Choose...")
        self.text_color = QColor(self.renderer.text_color)
        self.text_color_btn.clicked.connect(self._choose_text_color)
        set_color_button_indicator(self.text_color_btn, self.text_color)
        color_layout.addWidget(self.text_color_btn)
        scalebar_layout.addLayout(color_layout)

        self.bg_checkbox = QCheckBox("Background box")
        self.bg_checkbox.setChecked(self.renderer.scalebar_bg_enabled)
        scalebar_layout.addWidget(self.bg_checkbox)

        bg_layout = QHBoxLayout()
        bg_layout.addWidget(QLabel("BG color:"))
        self.bg_color_btn = QPushButton("Choose...")
        self.bg_color = QColor(self.renderer.scalebar_bg_color)
        self.bg_color_btn.clicked.connect(self._choose_bg_color)
        set_color_button_indicator(self.bg_color_btn, self.bg_color)
        bg_layout.addWidget(self.bg_color_btn)

        bg_layout.addWidget(QLabel("Opacity:"))
        self.bg_opacity_spinbox = QSpinBox()
        self.bg_opacity_spinbox.setRange(0, 255)
        self.bg_opacity_spinbox.setValue(self.renderer.scalebar_bg_opacity)
        bg_layout.addWidget(self.bg_opacity_spinbox)
        scalebar_layout.addLayout(bg_layout)

        scalebar_group.setContentLayout(scalebar_layout)
        params_layout.addWidget(scalebar_group)

        aperture_group = QCollapsibleBox("Aperture Overlay", expanded=False)
        self.batch_aperture_box = aperture_group
        aperture_layout = QVBoxLayout()

        self.aperture_checkbox = QCheckBox("Add aperture overlay")
        self.aperture_checkbox.setChecked(False)
        self.aperture_checkbox.stateChanged.connect(self._update_batch_section_titles)
        aperture_layout.addWidget(self.aperture_checkbox)

        ap_layout = QHBoxLayout()
        ap_layout.addWidget(QLabel("Nominal diameter (µm):"))
        self.aperture_size_combo = QComboBox()
        self.aperture_size_combo.addItems(["300", "200", "100", "50"])
        self.aperture_size_combo.setCurrentText("100")
        ap_layout.addWidget(self.aperture_size_combo)
        aperture_layout.addLayout(ap_layout)

        ap_color_layout = QHBoxLayout()
        ap_color_layout.addWidget(QLabel("Circle color:"))
        self.aperture_color_btn = QPushButton("Choose...")
        self.aperture_color = QColor(self.renderer.aperture_color)
        self.aperture_color_btn.clicked.connect(self._choose_aperture_color)
        set_color_button_indicator(self.aperture_color_btn, self.aperture_color)
        ap_color_layout.addWidget(self.aperture_color_btn)
        aperture_layout.addLayout(ap_color_layout)

        aperture_group.setContentLayout(aperture_layout)
        params_layout.addWidget(aperture_group)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()

        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Output folder:"))
        self.output_folder_edit = QLabel("(same as input)")
        self.output_folder_edit.setStyleSheet("QLabel { border: 1px solid palette(mid); padding: 3px; }")
        folder_layout.addWidget(self.output_folder_edit, stretch=1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._choose_output_folder)
        folder_layout.addWidget(browse_btn)
        output_layout.addLayout(folder_layout)

        suffix_layout = QHBoxLayout()
        suffix_layout.addWidget(QLabel("Filename suffix:"))
        self.suffix_edit = QComboBox()
        self.suffix_edit.setEditable(True)
        self.suffix_edit.addItems(["_processed", "_annotated", "_scaled", ""])
        self.suffix_edit.setCurrentText("_processed")
        suffix_layout.addWidget(self.suffix_edit)
        output_layout.addLayout(suffix_layout)

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Output format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "TIFF", "JPEG"])
        self.format_combo.setCurrentText("PNG")
        format_layout.addWidget(self.format_combo)
        output_layout.addLayout(format_layout)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        process_btn = QPushButton("Process All")
        process_btn.setMinimumHeight(40)
        process_btn.clicked.connect(self._process_all)
        button_layout.addWidget(process_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addStretch()
        scroll_area.setWidget(scroll_content)
        root_layout.addWidget(scroll_area)
        root_layout.addLayout(button_layout)

        self.setLayout(root_layout)

        if self.last_output_directory:
            self.output_folder_edit.setText(self.last_output_directory)

        self._update_batch_section_titles()
        self._on_preset_changed("Standard")

    @staticmethod
    def _format_batch_section_title(base_title: str, applied: bool) -> str:
        marker = "☑ Applied" if applied else "☐ Not Applied"
        return f"{base_title} {marker}"

    def _update_batch_section_titles(self):
        if hasattr(self, "batch_crop_box") and hasattr(self, "batch_auto_crop_checkbox"):
            self.batch_crop_box.setTitle(
                self._format_batch_section_title("Image Cropping", self.batch_auto_crop_checkbox.isChecked())
            )
        if hasattr(self, "batch_scalebar_box") and hasattr(self, "scalebar_checkbox"):
            self.batch_scalebar_box.setTitle(
                self._format_batch_section_title("Scalebar", self.scalebar_checkbox.isChecked())
            )
        if hasattr(self, "batch_aperture_box") and hasattr(self, "aperture_checkbox"):
            self.batch_aperture_box.setTitle(
                self._format_batch_section_title("Aperture Overlay", self.aperture_checkbox.isChecked())
            )

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            self.last_input_directory,
            "Image Files (*.rodhypix *.tif *.tiff *.png *.jpg *.jpeg *.bmp);;RODHyPix Files (*.rodhypix);;TIFF Files (*.tif *.tiff);;All Files (*.*)",
        )
        if files:
            try:
                self.last_input_directory = str(Path(files[0]).parent)
            except Exception:
                pass
            for file in files:
                if file not in self.files:
                    self.files.append(file)
                    self.file_list.addItem(Path(file).name)

    def _remove_selected(self):
        selected = self.file_list.selectedItems()
        if not selected:
            return
        for item in selected:
            row = self.file_list.row(item)
            self.file_list.takeItem(row)
            self.files.pop(row)

    def _clear_files(self):
        self.files.clear()
        self.file_list.clear()

    def _on_preset_changed(self, preset_name: str):
        if preset_name in self.presets:
            try:
                npp = float(self.presets[preset_name])
                if npp <= 0:
                    npp = 1.0
            except Exception:
                npp = 1.0

            self.pixel_size_spinbox.setValue(npp)
            self.pixel_unit_combo.setCurrentText("nm")

            defaults = get_mode_overlay_defaults(preset_name)
            if defaults is not None:
                self.scalebar_unit_combo.setCurrentText(defaults["unit"])
                self.scalebar_length_spinbox.setValue(defaults["scalebar_length_value"])
                self._batch_scalebar_length_text_raw = defaults["scalebar_length_text"]

    def _choose_bar_color(self):
        color = QColorDialog.getColor(self.bar_color, self, "Choose Scalebar Bar Color")
        if color.isValid():
            self.bar_color = color
            set_color_button_indicator(self.bar_color_btn, self.bar_color)

    def _choose_text_color(self):
        color = QColorDialog.getColor(self.text_color, self, "Choose Scalebar Text Color")
        if color.isValid():
            self.text_color = color
            set_color_button_indicator(self.text_color_btn, self.text_color)

    def _choose_bg_color(self):
        color = QColorDialog.getColor(self.bg_color, self, "Choose Background Color")
        if color.isValid():
            self.bg_color = color
            set_color_button_indicator(self.bg_color_btn, self.bg_color)

    def _choose_aperture_color(self):
        color = QColorDialog.getColor(self.aperture_color, self, "Choose Aperture Color")
        if color.isValid():
            self.aperture_color = color
            set_color_button_indicator(self.aperture_color_btn, self.aperture_color)

    def _choose_output_folder(self):
        start_dir = self.last_output_directory or self.last_input_directory
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", start_dir)
        if folder:
            self.last_output_directory = str(folder)
            self.output_folder_edit.setText(folder)

    def get_last_directories(self) -> tuple[str, str]:
        """Return latest batch input/output directory preferences."""
        return self.last_input_directory, self.last_output_directory

    def get_crop_defaults(self) -> tuple[int, int]:
        """Return current batch crop defaults (top_rows, bottom_rows)."""
        return int(self.batch_crop_top_spinbox.value()), int(self.batch_crop_bottom_spinbox.value())

    def _on_batch_scalebar_length_text_edited(self, text: str):
        self._batch_scalebar_length_text_raw = text

    def _process_all(self):
        if not self.files:
            QMessageBox.warning(self, "No Files", "Please add files to process.")
            return

        output_folder_text = self.output_folder_edit.text()
        if output_folder_text == "(same as input)":
            output_folder = None
        else:
            output_folder = Path(output_folder_text)
            if not output_folder.exists():
                QMessageBox.warning(self, "Invalid Folder", "Output folder does not exist.")
                return

        pixel_size = self.pixel_size_spinbox.value()
        pixel_unit = self.pixel_unit_combo.currentText()
        nm_per_pixel = pixel_size * 1000.0 if pixel_unit == "µm" else pixel_size
        if nm_per_pixel <= 0:
            nm_per_pixel = 1.0

        auto_bc = self.auto_bc_checkbox.isChecked()

        scalebar_enabled = self.scalebar_checkbox.isChecked()
        scalebar_length = self.scalebar_length_spinbox.value()
        scalebar_unit = self.scalebar_unit_combo.currentText()
        scalebar_thickness = self.scalebar_thickness_spinbox.value()
        scalebar_position = self.position_combo.currentText()

        aperture_enabled = self.aperture_checkbox.isChecked()
        aperture_size = int(self.aperture_size_combo.currentText())

        batch_auto_crop_enabled = self.batch_auto_crop_checkbox.isChecked()
        batch_crop_top_rows = self.batch_crop_top_spinbox.value()
        batch_crop_bottom_rows = self.batch_crop_bottom_spinbox.value()

        suffix = self.suffix_edit.currentText()
        output_format = self.format_combo.currentText().lower()

        progress = QProgressDialog("Processing images...", "Cancel", 0, len(self.files), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        processor = ImageProcessor()
        renderer = OverlayRenderer()

        renderer.scalebar_enabled = scalebar_enabled
        renderer.scalebar_length_value = float(scalebar_length)
        renderer.scalebar_unit = scalebar_unit
        renderer.scalebar_thickness = scalebar_thickness
        renderer.scalebar_position = scalebar_position
        renderer.bar_color = QColor(self.bar_color)
        renderer.text_color = QColor(self.text_color)
        renderer.scalebar_bg_enabled = self.bg_checkbox.isChecked()
        renderer.scalebar_bg_color = QColor(self.bg_color)
        renderer.scalebar_bg_opacity = self.bg_opacity_spinbox.value()
        renderer.aperture_enabled = aperture_enabled
        renderer.aperture_nominal_size = aperture_size
        renderer.aperture_color = QColor(self.aperture_color)

        override = getattr(self, "_batch_scalebar_length_text_raw", None)
        if isinstance(override, str) and override.strip() != "":
            try:
                float(override)
                renderer.scalebar_label_override = override.strip()
            except ValueError:
                renderer.scalebar_label_override = None

        successful = 0
        failed = []

        for i, file_path in enumerate(self.files):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            progress.setLabelText(f"Processing {Path(file_path).name}...")
            QApplication.processEvents()

            try:
                success, error, _, pixel_metadata = processor.load_image(file_path)
                if not success:
                    failed.append((file_path, error))
                    continue

                if batch_auto_crop_enabled:
                    crop_success, crop_error, _ = processor.crop_rows(
                        top_rows=batch_crop_top_rows,
                        bottom_rows=batch_crop_bottom_rows,
                    )
                    if not crop_success:
                        failed.append(
                            (
                                file_path,
                                crop_error
                                or (
                                    "Image crop failed "
                                    f"(top={batch_crop_top_rows}, bottom={batch_crop_bottom_rows})."
                                ),
                            )
                        )
                        continue

                file_nm_per_pixel = nm_per_pixel
                if pixel_metadata and "pixel_size_nm" in pixel_metadata:
                    if pixel_unit == "µm":
                        file_nm_per_pixel = pixel_metadata["pixel_size_um"]
                    else:
                        file_nm_per_pixel = pixel_metadata["pixel_size_nm"]
                    print(f"Using pixel size from {Path(file_path).name}: {file_nm_per_pixel:.3f} {pixel_unit}")

                if auto_bc:
                    processor.auto_adjust_contrast()

                q_image = renderer.render_image_with_overlays(processor.get_current_image(), file_nm_per_pixel)
                if q_image is None:
                    failed.append((file_path, "Failed to render image"))
                    continue

                input_path = Path(file_path)
                output_dir = output_folder if output_folder else input_path.parent
                output_name = input_path.stem + suffix + "." + output_format
                output_path = output_dir / output_name

                q_rgba = q_image.convertToFormat(QImage.Format.Format_RGBA8888)
                width = q_rgba.width()
                height = q_rgba.height()
                ptr = q_rgba.bits()
                ptr.setsize(height * width * 4)
                arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))
                export_rgba = arr.copy()

                input_dpi = processor.get_dpi()
                if input_dpi and all(v > 0 for v in input_dpi):
                    xdpi = min(input_dpi[0], 300.0)
                    ydpi = min(input_dpi[1], 300.0)
                else:
                    xdpi = ydpi = 300.0

                if output_format in ["jpg", "jpeg", "bmp"]:
                    export_rgb = export_rgba[:, :, :3]
                    pil_image = Image.fromarray(export_rgb, mode="RGB")
                    pil_image.save(str(output_path), dpi=(xdpi, ydpi))
                else:
                    pil_image = Image.fromarray(export_rgba, mode="RGBA")
                    pil_image.save(str(output_path), dpi=(xdpi, ydpi))

                successful += 1

            except Exception as e:
                failed.append((file_path, str(e)))

        progress.setValue(len(self.files))

        if failed:
            failed_list = "\n".join([f"{Path(f).name}: {e}" for f, e in failed[:10]])
            if len(failed) > 10:
                failed_list += f"\n... and {len(failed) - 10} more"
            QMessageBox.warning(
                self,
                "Batch Processing Complete",
                f"Successfully processed: {successful}/{len(self.files)}\n\n"
                f"Failed files:\n{failed_list}",
            )
        else:
            QMessageBox.information(
                self,
                "Batch Processing Complete",
                f"Successfully processed all {successful} images!",
            )

        self.accept()
