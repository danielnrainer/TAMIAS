"""Batch processing dialog for applying overlays and exports across multiple images."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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

from core.diffraction import (
    RECIPROCAL_ANGSTROM,
    RECIPROCAL_UNITS,
    DiffractionGeometry,
)
from core.image_processor import ImageProcessor
from core.overlay_renderer import OverlayRenderer, qimage_to_rgba_array
from gui.collapsible_box import QCollapsibleBox
from gui.custom_widgets import SmartDoubleSpinBox, set_color_button_indicator
from utils.imaging_mode_defaults import (
    AUTO_FALLBACK_PRESET,
    AUTO_PRESET_LABEL,
    get_mode_overlay_defaults,
)


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
        image_type: str = "real",
        diffraction_defaults: dict | None = None,
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
        self.initial_image_type = "diffraction" if str(image_type) == "diffraction" else "real"
        self.diffraction_defaults = dict(diffraction_defaults or {})

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

        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Image type:"))
        self.image_type_combo = QComboBox()
        self.image_type_combo.addItem("Real space image", "real")
        self.image_type_combo.addItem("Diffraction pattern", "diffraction")
        type_layout.addWidget(self.image_type_combo)
        params_layout.addLayout(type_layout)

        # Real-space calibration widgets (hidden for diffraction patterns)
        self.real_calibration_widget = QWidget()
        real_layout = QVBoxLayout(self.real_calibration_widget)
        real_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.addWidget(self.real_calibration_widget)

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Imaging mode:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem(AUTO_PRESET_LABEL)
        self.preset_combo.addItems(sorted(self.presets.keys()))
        self.preset_combo.setCurrentText(AUTO_PRESET_LABEL)
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_layout.addWidget(self.preset_combo)
        real_layout.addLayout(preset_layout)

        # Only relevant in Auto mode: preset used for files without a header pixel size
        fallback_layout = QHBoxLayout()
        self.fallback_label = QLabel("Fallback preset:")
        fallback_layout.addWidget(self.fallback_label)
        self.fallback_combo = QComboBox()
        self.fallback_combo.addItems(sorted(self.presets.keys()))
        if AUTO_FALLBACK_PRESET in self.presets:
            self.fallback_combo.setCurrentText(AUTO_FALLBACK_PRESET)
        self.fallback_combo.currentTextChanged.connect(self._on_preset_changed)
        fallback_layout.addWidget(self.fallback_combo)
        self.fallback_widgets = [self.fallback_label, self.fallback_combo]
        real_layout.addLayout(fallback_layout)

        pixel_layout = QHBoxLayout()
        self.pixel_size_label = QLabel("Pixel size:")
        pixel_layout.addWidget(self.pixel_size_label)
        self.pixel_size_spinbox = QDoubleSpinBox()
        self.pixel_size_spinbox.setRange(0.00001, 100000.0)
        self.pixel_size_spinbox.setDecimals(3)
        self.pixel_size_spinbox.setValue(35.6)
        pixel_layout.addWidget(self.pixel_size_spinbox)

        self.pixel_unit_combo = QComboBox()
        self.pixel_unit_combo.addItems(["nm", "µm"])
        pixel_layout.addWidget(self.pixel_unit_combo)
        real_layout.addLayout(pixel_layout)

        self.auto_info_label = QLabel(
            "Auto: each .rodhypix file's header pixel size is used; files without one "
            "(e.g. TIFF) use the fallback preset above."
        )
        self.auto_info_label.setWordWrap(True)
        self.auto_info_label.setStyleSheet("font-style: italic")
        real_layout.addWidget(self.auto_info_label)

        # Diffraction calibration (shown for diffraction patterns only)
        dd = self.diffraction_defaults
        diff_box = QCollapsibleBox("Diffraction Calibration", expanded=False)
        self.batch_diffraction_box = diff_box
        diff_layout = QVBoxLayout()

        self.diff_use_header_checkbox = QCheckBox("Use file header values where available")
        self.diff_use_header_checkbox.setChecked(bool(dd.get("use_header", True)))
        diff_layout.addWidget(self.diff_use_header_checkbox)

        def _float_default(key: str, fallback: float) -> float:
            try:
                value = float(dd.get(key, fallback))
            except (TypeError, ValueError):
                return fallback
            return value if value > 0 else fallback

        cl_layout = QHBoxLayout()
        cl_layout.addWidget(QLabel("Camera length (mm):"))
        self.diff_camera_length_spinbox = QDoubleSpinBox()
        self.diff_camera_length_spinbox.setRange(0.1, 100000.0)
        self.diff_camera_length_spinbox.setDecimals(1)
        self.diff_camera_length_spinbox.setValue(_float_default("camera_length_mm", 650.0))
        cl_layout.addWidget(self.diff_camera_length_spinbox)
        diff_layout.addLayout(cl_layout)

        wl_layout = QHBoxLayout()
        wl_layout.addWidget(QLabel("Wavelength (Å):"))
        self.diff_wavelength_spinbox = QDoubleSpinBox()
        self.diff_wavelength_spinbox.setRange(0.00001, 10.0)
        self.diff_wavelength_spinbox.setDecimals(5)
        self.diff_wavelength_spinbox.setSingleStep(0.0001)
        self.diff_wavelength_spinbox.setValue(_float_default("wavelength_angstrom", 0.02508))
        wl_layout.addWidget(self.diff_wavelength_spinbox)
        diff_layout.addLayout(wl_layout)

        px_layout = QHBoxLayout()
        px_layout.addWidget(QLabel("Detector pixel size (µm):"))
        self.diff_pixel_size_spinbox = QDoubleSpinBox()
        self.diff_pixel_size_spinbox.setRange(0.01, 10000.0)
        self.diff_pixel_size_spinbox.setDecimals(2)
        self.diff_pixel_size_spinbox.setValue(_float_default("pixel_size_um", 100.0))
        px_layout.addWidget(self.diff_pixel_size_spinbox)
        diff_layout.addLayout(px_layout)

        diff_info = QLabel(
            "Values above are fallbacks for files without header values (e.g. TIFF), or are "
            "used for all files when the header option is off. Beam centre: the header beam "
            "origin (shifted by the crop below) if present, otherwise the image centre."
        )
        diff_info.setWordWrap(True)
        diff_info.setStyleSheet("font-style: italic")
        diff_layout.addWidget(diff_info)

        diff_box.setContentLayout(diff_layout)
        params_layout.addWidget(diff_box)

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

        scaling_layout = QHBoxLayout()
        scaling_layout.addWidget(QLabel("Intensity scaling:"))
        self.intensity_scaling_combo = QComboBox()
        self.intensity_scaling_combo.addItems(list(ImageProcessor.INTENSITY_SCALING_MODES))
        self.intensity_scaling_combo.setToolTip(
            "Mapping from raw counts to display brightness. Logarithmic suits diffraction "
            "patterns (very bright direct beam, weak reflections)."
        )
        scaling_layout.addWidget(self.intensity_scaling_combo)
        params_layout.addLayout(scaling_layout)

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
        self.scalebar_length_spinbox.setDecimals(3)
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

        rings_group = QCollapsibleBox("Resolution Rings", expanded=False)
        self.batch_rings_box = rings_group
        rings_layout = QVBoxLayout()

        self.rings_checkbox = QCheckBox("Add resolution rings")
        self.rings_checkbox.setChecked(bool(getattr(self.renderer, "rings_enabled", False)))
        self.rings_checkbox.stateChanged.connect(self._update_batch_section_titles)
        rings_layout.addWidget(self.rings_checkbox)

        rings_layout.addWidget(QLabel("Resolutions (d-spacing in Å, comma-separated):"))
        initial_rings = []
        for entry in getattr(self.renderer, "ring_resolutions", []) or []:
            try:
                if bool(entry.get("enabled", True)):
                    initial_rings.append(f"{float(entry.get('d')):g}")
            except (TypeError, ValueError, AttributeError):
                continue
        self.rings_edit = QLineEdit(", ".join(initial_rings) if initial_rings else "0.8, 1.0, 1.2, 2.0")
        self.rings_edit.setPlaceholderText("e.g. 0.8, 1.0, 1.2, 2.0")
        rings_layout.addWidget(self.rings_edit)

        ring_style_layout = QHBoxLayout()
        ring_style_layout.addWidget(QLabel("Color:"))
        self.ring_color_btn = QPushButton("Choose...")
        self.ring_color = QColor(getattr(self.renderer, "ring_color", QColor(0, 255, 255)))
        self.ring_color_btn.clicked.connect(self._choose_ring_color)
        set_color_button_indicator(self.ring_color_btn, self.ring_color)
        ring_style_layout.addWidget(self.ring_color_btn)
        ring_style_layout.addWidget(QLabel("Width (px):"))
        self.ring_width_spinbox = QSpinBox()
        self.ring_width_spinbox.setRange(1, 20)
        self.ring_width_spinbox.setValue(int(getattr(self.renderer, "ring_line_width", 2)))
        ring_style_layout.addWidget(self.ring_width_spinbox)
        rings_layout.addLayout(ring_style_layout)

        self.ring_labels_checkbox = QCheckBox("Show resolution labels")
        self.ring_labels_checkbox.setChecked(bool(getattr(self.renderer, "ring_show_labels", True)))
        rings_layout.addWidget(self.ring_labels_checkbox)

        rings_group.setContentLayout(rings_layout)
        params_layout.addWidget(rings_group)

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
        self._on_preset_changed(AUTO_PRESET_LABEL)

        # Per-image-type scalebar state (value, unit) restored when switching types.
        self._real_scalebar_state = (
            float(self.scalebar_length_spinbox.value()),
            self.scalebar_unit_combo.currentText(),
        )
        recip_unit = getattr(self.renderer, "recip_scalebar_unit", RECIPROCAL_ANGSTROM)
        if recip_unit not in RECIPROCAL_UNITS:
            recip_unit = RECIPROCAL_ANGSTROM
        self._recip_scalebar_state = (
            float(getattr(self.renderer, "recip_scalebar_length_value", 0.5)),
            recip_unit,
        )
        self._active_image_type = "real"
        self.image_type_combo.currentIndexChanged.connect(self._on_image_type_changed)
        target_index = self.image_type_combo.findData(self.initial_image_type)
        if target_index > 0:
            self.image_type_combo.setCurrentIndex(target_index)  # triggers _on_image_type_changed
        else:
            self._on_image_type_changed()

        initial_scaling = str(self.diffraction_defaults.get("intensity_scaling", ""))
        if self._is_diffraction() and initial_scaling in ImageProcessor.INTENSITY_SCALING_MODES:
            self.intensity_scaling_combo.setCurrentText(initial_scaling)

    def _is_diffraction(self) -> bool:
        return self.image_type_combo.currentData() == "diffraction"

    def _on_image_type_changed(self, _index: int = 0):
        """Swap calibration/overlay sections, scalebar units and default scaling."""
        diffraction = self._is_diffraction()
        new_type = "diffraction" if diffraction else "real"

        self.real_calibration_widget.setVisible(not diffraction)
        self.batch_aperture_box.setVisible(not diffraction)
        self.batch_diffraction_box.setVisible(diffraction)
        self.batch_rings_box.setVisible(diffraction)

        if new_type != self._active_image_type:
            current_state = (
                float(self.scalebar_length_spinbox.value()),
                self.scalebar_unit_combo.currentText(),
            )
            if self._active_image_type == "diffraction":
                self._recip_scalebar_state = current_state
            else:
                self._real_scalebar_state = current_state
            self._active_image_type = new_type

        value, unit = self._recip_scalebar_state if diffraction else self._real_scalebar_state
        units = list(RECIPROCAL_UNITS) if diffraction else ["nm", "µm"]
        self.scalebar_unit_combo.blockSignals(True)
        self.scalebar_unit_combo.clear()
        self.scalebar_unit_combo.addItems(units)
        self.scalebar_unit_combo.setCurrentText(unit if unit in units else units[0])
        self.scalebar_unit_combo.blockSignals(False)
        self.scalebar_length_spinbox.setValue(float(value))
        # A raw label typed for the other image type must not leak into this one.
        self._batch_scalebar_length_text_raw = None

        self.intensity_scaling_combo.setCurrentText("Logarithmic" if diffraction else "Linear")
        self._update_batch_section_titles()

    def _choose_ring_color(self):
        color = QColorDialog.getColor(self.ring_color, self, "Choose Resolution Ring Color")
        if color.isValid():
            self.ring_color = color
            set_color_button_indicator(self.ring_color_btn, self.ring_color)

    def _parse_ring_resolutions(self) -> tuple[list[float], list[str]]:
        """Parse the ring d-spacing list. Returns (valid values in Å, invalid tokens)."""
        values: list[float] = []
        invalid: list[str] = []
        text = self.rings_edit.text().replace(";", ",")
        for token in text.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                value = float(token)
            except ValueError:
                invalid.append(token)
                continue
            if not np.isfinite(value) or value <= 0:
                invalid.append(token)
                continue
            if value not in values:
                values.append(value)
        return values, invalid

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
        if hasattr(self, "batch_rings_box") and hasattr(self, "rings_checkbox"):
            self.batch_rings_box.setTitle(
                self._format_batch_section_title("Resolution Rings", self.rings_checkbox.isChecked())
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

    def _effective_preset_name(self) -> str:
        """Preset whose pixel size applies (the fallback preset when in Auto mode)."""
        mode = self.preset_combo.currentText()
        return self.fallback_combo.currentText() if mode == AUTO_PRESET_LABEL else mode

    def _on_preset_changed(self, _text: str = ""):
        is_auto = self.preset_combo.currentText() == AUTO_PRESET_LABEL
        for widget in self.fallback_widgets:
            widget.setVisible(is_auto)
        self.auto_info_label.setVisible(is_auto)
        self.pixel_size_label.setText("Fallback pixel size:" if is_auto else "Pixel size:")

        preset_name = self._effective_preset_name()
        is_custom = preset_name == "Custom"
        self.pixel_size_spinbox.setEnabled(is_custom)
        self.pixel_unit_combo.setEnabled(is_custom)

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
            # Real-space scalebar defaults only; diffraction mode uses reciprocal units.
            if defaults is not None and not self._is_diffraction():
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

    @staticmethod
    def _resolve_file_geometry(
        processor: ImageProcessor, use_header: bool, fallback: dict
    ) -> DiffractionGeometry | None:
        """Diffraction geometry for the currently loaded (and cropped) file, or None if invalid."""
        header = processor.get_header_diffraction_geometry() if use_header else {}
        image = processor.get_current_image()
        if image is None:
            return None
        height, width = image.shape[:2]
        header_center = header.get("beam_center_px") if use_header else None
        if header_center is not None:
            beam_center = processor.map_loaded_to_current(*header_center)
        else:
            beam_center = (width / 2.0, height / 2.0)
        geometry = DiffractionGeometry(
            camera_length_mm=float(header.get("camera_length_mm", fallback["camera_length_mm"])),
            wavelength_angstrom=float(header.get("wavelength_angstrom", fallback["wavelength_angstrom"])),
            pixel_size_mm=float(header.get("pixel_size_mm", fallback["pixel_size_mm"])),
            beam_center_px=(float(beam_center[0]), float(beam_center[1])),
        )
        return geometry if geometry.is_valid() else None

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
        fallback_nm_per_pixel = nm_per_pixel
        use_file_pixel_size = self.preset_combo.currentText() == AUTO_PRESET_LABEL

        auto_bc = self.auto_bc_checkbox.isChecked()

        scalebar_enabled = self.scalebar_checkbox.isChecked()
        scalebar_length = self.scalebar_length_spinbox.value()
        scalebar_unit = self.scalebar_unit_combo.currentText()
        scalebar_thickness = self.scalebar_thickness_spinbox.value()
        scalebar_position = self.position_combo.currentText()

        aperture_enabled = self.aperture_checkbox.isChecked()
        aperture_size = int(self.aperture_size_combo.currentText())

        is_diffraction = self._is_diffraction()
        intensity_scaling = self.intensity_scaling_combo.currentText()
        diff_use_header = self.diff_use_header_checkbox.isChecked()
        diff_fallback = {
            "camera_length_mm": float(self.diff_camera_length_spinbox.value()),
            "wavelength_angstrom": float(self.diff_wavelength_spinbox.value()),
            "pixel_size_mm": float(self.diff_pixel_size_spinbox.value()) / 1000.0,
        }
        rings_enabled = is_diffraction and self.rings_checkbox.isChecked()
        ring_values: list[float] = []
        if rings_enabled:
            ring_values, invalid_tokens = self._parse_ring_resolutions()
            if invalid_tokens:
                answer = QMessageBox.question(
                    self,
                    "Invalid Ring Resolutions",
                    "These resolution ring entries are not positive numbers and will be ignored:\n"
                    + ", ".join(invalid_tokens)
                    + "\n\nContinue processing?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return

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

        processor.intensity_scaling = intensity_scaling  # used by load_image
        if is_diffraction:
            renderer.scalebar_unit = "nm"  # real-space unit unused in diffraction mode
            renderer.recip_scalebar_unit = scalebar_unit
            renderer.recip_scalebar_length_value = float(scalebar_length)
            renderer.aperture_enabled = False
            renderer.rings_enabled = rings_enabled and bool(ring_values)
            # Carry over label positions dragged in the main window (matched by d-spacing).
            main_rings = {
                round(float(r["d"]), 6): r for r in (getattr(self.renderer, "ring_resolutions", []) or [])
                if isinstance(r, dict) and r.get("label_angle") is not None
            }
            renderer.ring_resolutions = []
            for d in ring_values:
                ring = {"d": float(d), "enabled": True}
                source = main_rings.get(round(float(d), 6))
                if source is not None:
                    ring["label_angle"] = float(source["label_angle"])
                    ring["label_radial"] = float(source.get("label_radial", 0.0))
                renderer.ring_resolutions.append(ring)
            renderer.ring_color = QColor(self.ring_color)
            renderer.ring_line_width = int(self.ring_width_spinbox.value())
            renderer.ring_show_labels = self.ring_labels_checkbox.isChecked()
            renderer.ring_font = getattr(self.renderer, "ring_font", renderer.ring_font)
            renderer.beam_center_marker_enabled = False
        renderer.measurement_enabled = False

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
                success, error, _ = processor.load_image(file_path)
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

                if auto_bc:
                    processor.auto_adjust_contrast()

                geometry = None
                if is_diffraction:
                    geometry = self._resolve_file_geometry(processor, diff_use_header, diff_fallback)
                    if geometry is None:
                        failed.append(
                            (
                                file_path,
                                "Invalid diffraction calibration (camera length, wavelength and "
                                "pixel size must be positive).",
                            )
                        )
                        continue
                    nm_per_pixel = fallback_nm_per_pixel
                else:
                    file_nm = processor.get_file_pixel_size_nm() if use_file_pixel_size else None
                    nm_per_pixel = file_nm if file_nm else fallback_nm_per_pixel

                q_image = renderer.render_image_with_overlays(
                    processor.get_current_image(), nm_per_pixel, diffraction=geometry
                )
                if q_image is None:
                    failed.append((file_path, "Failed to render image"))
                    continue

                input_path = Path(file_path)
                output_dir = output_folder if output_folder else input_path.parent
                output_name = input_path.stem + suffix + "." + output_format
                output_path = output_dir / output_name

                export_rgba = qimage_to_rgba_array(q_image)

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
