"""Extracted UI setup sections for the TAMIAS main window."""

from __future__ import annotations

from typing import Any

from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from core.diffraction import COMMON_ACCELERATING_VOLTAGES_KV
from core.image_processor import ImageProcessor
from gui.collapsible_box import QCollapsibleBox
from utils.imaging_mode_defaults import AUTO_PRESET_LABEL
from gui.custom_widgets import ClickClearTableWidget, SmartDoubleSpinBox, set_color_button_indicator


def setup_preset_controls(editor: Any, parent_layout):
    """Setup imaging mode preset controls on the main editor."""
    preset_box = QCollapsibleBox("Imaging Mode", expanded=False)
    preset_layout = QVBoxLayout()

    editor.preset_combo = QComboBox()
    editor._update_preset_combo()
    editor.preset_combo.currentTextChanged.connect(editor.on_preset_changed)
    preset_layout.addWidget(QLabel("Select Preset:"))
    preset_layout.addWidget(editor.preset_combo)

    pixel_size_layout = QHBoxLayout()
    pixel_size_layout.addWidget(QLabel("Pixel size:"))

    editor.pixel_size_spinbox = QDoubleSpinBox()
    editor.pixel_size_spinbox.setRange(0.00001, 100000.0)
    editor.pixel_size_spinbox.setDecimals(3)
    editor.pixel_size_spinbox.setValue(1.0)
    editor.pixel_size_spinbox.valueChanged.connect(editor.on_pixel_size_changed)
    pixel_size_layout.addWidget(editor.pixel_size_spinbox)

    editor.pixel_size_unit_combo = QComboBox()
    editor.pixel_size_unit_combo.addItems(["nm", "µm"])
    editor.pixel_size_unit_combo.currentTextChanged.connect(editor.on_pixel_size_unit_changed)
    pixel_size_layout.addWidget(editor.pixel_size_unit_combo)

    preset_layout.addLayout(pixel_size_layout)

    editor.calibration_source_label = QLabel("")
    editor.calibration_source_label.setWordWrap(True)
    preset_layout.addWidget(editor.calibration_source_label)

    preset_info_label = QLabel(
        "Auto uses the pixel size stored in .rodhypix files (not present in TIFFs or post-experiment images - choose a preset for those). "
        "To change the pixel size of presets, go to Settings > Manage Presets in the main menu."
    )
    preset_info_label.setWordWrap(True)
    preset_info_label.setStyleSheet("font-style: italic")
    preset_layout.addWidget(preset_info_label)

    # Default to Auto: use the file header pixel size where available, presets as fallback
    editor.preset_combo.setCurrentText(AUTO_PRESET_LABEL)
    QTimer.singleShot(0, editor._apply_initial_scalebar_defaults)

    editor._update_pixel_size_editable_state(editor.preset_combo.currentText())
    editor._update_calibration_source_label()

    preset_box.setContentLayout(preset_layout)
    editor.preset_box = preset_box
    parent_layout.addWidget(preset_box)


def setup_brightness_contrast_controls(editor: Any, parent_layout):
    """Setup brightness/contrast controls on the main editor."""
    bc_box = QCollapsibleBox("Brightness/Contrast", expanded=False)
    bc_layout = QVBoxLayout()

    scaling_layout = QHBoxLayout()
    scaling_layout.addWidget(QLabel("Intensity scaling:"))
    editor.intensity_scaling_combo = QComboBox()
    editor.intensity_scaling_combo.addItems(list(ImageProcessor.INTENSITY_SCALING_MODES))
    editor.intensity_scaling_combo.setToolTip(
        "How raw detector counts are mapped to display grey levels.\n"
        "Logarithmic or Square root reveal weak reflections next to the intense direct beam."
    )
    editor.intensity_scaling_combo.currentTextChanged.connect(editor.on_intensity_scaling_changed)
    scaling_layout.addWidget(editor.intensity_scaling_combo)
    bc_layout.addLayout(scaling_layout)

    auto_btn = QPushButton("Auto Adjust")
    auto_btn.clicked.connect(editor.auto_adjust)
    bc_layout.addWidget(auto_btn)

    bc_layout.addWidget(QLabel("Min Value:"))
    min_layout = QHBoxLayout()
    editor.min_slider = QSlider(Qt.Orientation.Horizontal)
    editor.min_slider.setRange(0, 255)
    editor.min_slider.setValue(0)
    editor.min_slider.valueChanged.connect(editor.on_brightness_contrast_changed)
    editor.min_value_label = QLabel("0")
    min_layout.addWidget(editor.min_slider)
    min_layout.addWidget(editor.min_value_label)
    bc_layout.addLayout(min_layout)

    bc_layout.addWidget(QLabel("Max Value:"))
    max_layout = QHBoxLayout()
    editor.max_slider = QSlider(Qt.Orientation.Horizontal)
    editor.max_slider.setRange(0, 255)
    editor.max_slider.setValue(255)
    editor.max_slider.valueChanged.connect(editor.on_brightness_contrast_changed)
    editor.max_value_label = QLabel("255")
    max_layout.addWidget(editor.max_slider)
    max_layout.addWidget(editor.max_value_label)
    bc_layout.addLayout(max_layout)

    reset_btn = QPushButton("Reset")
    reset_btn.clicked.connect(editor.reset_brightness_contrast)
    bc_layout.addWidget(reset_btn)

    bc_box.setContentLayout(bc_layout)
    parent_layout.addWidget(bc_box)


def setup_transform_controls(editor: Any, parent_layout):
    """Setup image transform controls on the main editor."""
    transform_box = QCollapsibleBox("Image Transform", expanded=False)
    transform_layout = QHBoxLayout()

    flip_h_btn = QPushButton("Flip Horizontal")
    flip_h_btn.clicked.connect(editor.flip_horizontal)
    transform_layout.addWidget(flip_h_btn)

    flip_v_btn = QPushButton("Flip Vertical")
    flip_v_btn.clicked.connect(editor.flip_vertical)
    transform_layout.addWidget(flip_v_btn)

    transform_box.setContentLayout(transform_layout)
    parent_layout.addWidget(transform_box)


def setup_scalebar_controls(editor: Any, parent_layout):
    """Setup scalebar controls on the main editor."""
    scalebar_box = QCollapsibleBox("Scalebar", expanded=False)
    scalebar_layout = QVBoxLayout()

    editor.scalebar_checkbox = QCheckBox("Show Scalebar")
    editor.scalebar_checkbox.setChecked(True)
    editor.scalebar_checkbox.stateChanged.connect(editor.on_scalebar_toggled)
    scalebar_layout.addWidget(editor.scalebar_checkbox)

    editor.move_scalebar_btn = QPushButton("☰  Move Scalebar Box")
    editor.move_scalebar_btn.setCheckable(True)
    editor.move_scalebar_btn.setToolTip(
        "Click and drag on the image to reposition the full scalebar box"
    )
    editor.move_scalebar_btn.toggled.connect(editor.on_scalebar_drag_mode_toggled)
    scalebar_layout.addWidget(editor.move_scalebar_btn)

    length_layout = QHBoxLayout()
    length_layout.addWidget(QLabel("Length:"))
    editor.scalebar_length_spinbox = SmartDoubleSpinBox()
    editor.scalebar_length_spinbox.setDecimals(3)
    editor.scalebar_length_spinbox.setSingleStep(0.1)
    editor.scalebar_length_spinbox.setRange(0.01, 10000.0)
    editor.scalebar_length_spinbox.setValue(100.0)
    editor.scalebar_length_spinbox.valueChanged.connect(editor.on_scalebar_changed)
    try:
        editor.scalebar_length_spinbox.lineEdit().textEdited.connect(editor.on_scalebar_length_text_edited)
    except Exception:
        pass
    length_layout.addWidget(editor.scalebar_length_spinbox)

    editor.unit_combo = QComboBox()
    editor.unit_combo.addItems(["nm", "µm"])
    editor.unit_combo.currentTextChanged.connect(editor.on_scalebar_unit_changed)
    mode_unit = editor._get_mode_dependent_unit(editor.preset_combo.currentText()) if hasattr(editor, "preset_combo") else None
    if mode_unit is not None:
        editor.unit_combo.blockSignals(True)
        editor.unit_combo.setCurrentText(mode_unit)
        editor.unit_combo.blockSignals(False)
        editor.overlay_renderer.scalebar_unit = mode_unit
    length_layout.addWidget(editor.unit_combo)
    scalebar_layout.addLayout(length_layout)

    thickness_layout = QHBoxLayout()
    thickness_layout.addWidget(QLabel("Thickness (px):"))
    editor.scalebar_thickness_spinbox = QSpinBox()
    editor.scalebar_thickness_spinbox.setRange(5, 100)
    editor.scalebar_thickness_spinbox.setValue(15)
    editor.scalebar_thickness_spinbox.valueChanged.connect(editor.on_scalebar_changed)
    thickness_layout.addWidget(editor.scalebar_thickness_spinbox)
    scalebar_layout.addLayout(thickness_layout)

    scalebar_layout.addWidget(QLabel("Position:"))
    editor.position_combo = QComboBox()
    editor.position_combo.addItems(["bottom-right", "bottom-left", "top-right", "top-left", "custom"])
    editor.position_combo.currentTextChanged.connect(editor.on_scalebar_changed)
    scalebar_layout.addWidget(editor.position_combo)

    bar_color_layout = QHBoxLayout()
    bar_color_layout.addWidget(QLabel("Bar Color:"))
    editor.bar_color_btn = QPushButton("Choose Color…")
    editor.bar_color_btn.clicked.connect(editor.choose_bar_color)
    set_color_button_indicator(editor.bar_color_btn, editor.overlay_renderer.bar_color)
    bar_color_layout.addWidget(editor.bar_color_btn)
    scalebar_layout.addLayout(bar_color_layout)

    text_color_layout = QHBoxLayout()
    text_color_layout.addWidget(QLabel("Text Color:"))
    editor.text_color_btn = QPushButton("Choose Color…")
    editor.text_color_btn.clicked.connect(editor.choose_text_color)
    set_color_button_indicator(editor.text_color_btn, editor.overlay_renderer.text_color)
    text_color_layout.addWidget(editor.text_color_btn)
    scalebar_layout.addLayout(text_color_layout)

    font_layout = QHBoxLayout()
    editor.font_label = QLabel("Font: Arial, 20pt")
    choose_font_btn = QPushButton("Choose Font…")
    choose_font_btn.clicked.connect(editor.choose_font)
    font_layout.addWidget(editor.font_label)
    font_layout.addWidget(choose_font_btn)
    scalebar_layout.addLayout(font_layout)

    bg_inner_box = QCollapsibleBox("Background Box", expanded=False)
    bg_layout = QVBoxLayout()
    editor.bg_checkbox = QCheckBox("Enable background box")
    editor.bg_checkbox.stateChanged.connect(editor.on_bg_toggled)
    bg_layout.addWidget(editor.bg_checkbox)

    bg_controls_layout = QHBoxLayout()
    editor.bg_color_btn = QPushButton("Choose Color…")
    editor.bg_color_btn.clicked.connect(editor.choose_bg_color)
    set_color_button_indicator(editor.bg_color_btn, editor.overlay_renderer.scalebar_bg_color)
    bg_controls_layout.addWidget(editor.bg_color_btn)

    bg_controls_layout.addWidget(QLabel("Opacity:"))
    editor.bg_opacity_slider = QSlider(Qt.Orientation.Horizontal)
    editor.bg_opacity_slider.setRange(0, 255)
    editor.bg_opacity_slider.setValue(255)
    editor.bg_opacity_slider.valueChanged.connect(editor.on_bg_opacity_changed)
    bg_controls_layout.addWidget(editor.bg_opacity_slider)

    bg_layout.addLayout(bg_controls_layout)
    editor.bg_checkbox.setChecked(True)
    bg_inner_box.setContentLayout(bg_layout)
    scalebar_layout.addWidget(bg_inner_box)

    scalebar_box.setContentLayout(scalebar_layout)
    scalebar_box.toggleButton.toggled.connect(editor._on_scalebar_section_toggled)
    parent_layout.addWidget(scalebar_box)


def setup_aperture_controls(editor: Any, parent_layout):
    """Setup aperture overlay controls on the main editor."""
    aperture_box = QCollapsibleBox("Aperture Overlay", expanded=False)
    aperture_layout = QVBoxLayout()

    editor.aperture_checkbox = QCheckBox("Show Aperture")
    editor.aperture_checkbox.setChecked(False)
    editor.aperture_checkbox.stateChanged.connect(editor.on_aperture_toggled)
    aperture_layout.addWidget(editor.aperture_checkbox)

    size_layout = QHBoxLayout()
    size_layout.addWidget(QLabel("Nominal diameter (µm):"))
    editor.aperture_size_combo = QComboBox()
    editor.aperture_size_combo.addItems(["300", "200", "100", "50"])
    editor.aperture_size_combo.setCurrentText("100")
    editor.aperture_size_combo.currentTextChanged.connect(editor.on_aperture_size_changed)
    size_layout.addWidget(editor.aperture_size_combo)
    aperture_layout.addLayout(size_layout)

    editor.aperture_info_label = QLabel("Apparent diameter: 2.0 µm")
    editor.aperture_info_label.setStyleSheet("font-style: italic; ")
    aperture_layout.addWidget(editor.aperture_info_label)

    aperture_color_layout = QHBoxLayout()
    aperture_color_layout.addWidget(QLabel("Circle color:"))
    editor.aperture_color_btn = QPushButton("Choose Color...")
    editor.aperture_color_btn.clicked.connect(editor.choose_aperture_color)
    set_color_button_indicator(editor.aperture_color_btn, editor.overlay_renderer.aperture_color)
    aperture_color_layout.addWidget(editor.aperture_color_btn)
    aperture_layout.addLayout(aperture_color_layout)

    aperture_box.setContentLayout(aperture_layout)
    editor.aperture_box = aperture_box
    parent_layout.addWidget(aperture_box)


def setup_measurement_controls(editor: Any, parent_layout):
    """Setup particle measurement controls on the main editor."""
    measurement_box = QCollapsibleBox("Particle Measurement", expanded=False)
    measurement_layout = QVBoxLayout()

    editor.measurement_checkbox = QCheckBox("Show Measurement Annotations")
    editor.measurement_checkbox.setChecked(True)
    editor.measurement_checkbox.stateChanged.connect(editor.on_measurement_toggled)
    measurement_layout.addWidget(editor.measurement_checkbox)

    editor.measurement_label_checkbox = QCheckBox("Include Length Label")
    editor.measurement_label_checkbox.setChecked(editor.overlay_renderer.measurement_show_label)
    editor.measurement_label_checkbox.stateChanged.connect(editor.on_measurement_changed)
    measurement_layout.addWidget(editor.measurement_label_checkbox)

    editor.draw_measurement_btn = QPushButton("✏  Draw Measurement")
    editor.draw_measurement_btn.setCheckable(True)
    editor.draw_measurement_btn.setToolTip(
        "Click and drag on the image to draw a measurement line"
    )
    editor.draw_measurement_btn.toggled.connect(editor.on_draw_mode_toggled)
    measurement_layout.addWidget(editor.draw_measurement_btn)

    editor.move_line_btn = QPushButton("↔  Move Line")
    editor.move_line_btn.setCheckable(True)
    editor.move_line_btn.setToolTip(
        "Click and drag a measurement line to move the full annotation"
    )
    editor.move_line_btn.toggled.connect(editor.on_line_drag_mode_toggled)
    measurement_layout.addWidget(editor.move_line_btn)

    editor.move_label_btn = QPushButton("☰  Move Label")
    editor.move_label_btn.setCheckable(True)
    editor.move_label_btn.setToolTip(
        "Click and drag a measurement label to reposition it"
    )
    editor.move_label_btn.toggled.connect(editor.on_label_drag_mode_toggled)
    measurement_layout.addWidget(editor.move_label_btn)

    unit_layout = QHBoxLayout()
    unit_layout.addWidget(QLabel("Length Unit:"))
    editor.measurement_unit_combo = QComboBox()
    editor.measurement_unit_combo.addItems(["nm", "µm"])
    editor.measurement_unit_combo.currentTextChanged.connect(editor.on_measurement_changed)
    mode_unit = editor._get_mode_dependent_unit(editor.preset_combo.currentText()) if hasattr(editor, "preset_combo") else None
    if mode_unit is not None:
        editor.measurement_unit_combo.blockSignals(True)
        editor.measurement_unit_combo.setCurrentText(mode_unit)
        editor.measurement_unit_combo.blockSignals(False)
        editor.overlay_renderer.measurement_unit = mode_unit
    unit_layout.addWidget(editor.measurement_unit_combo)
    measurement_layout.addLayout(unit_layout)

    thickness_layout = QHBoxLayout()
    thickness_layout.addWidget(QLabel("Line Width (px):"))
    editor.measurement_thickness_spinbox = QSpinBox()
    editor.measurement_thickness_spinbox.setRange(1, 20)
    editor.measurement_thickness_spinbox.setValue(editor.overlay_renderer.measurement_line_width)
    editor.measurement_thickness_spinbox.valueChanged.connect(editor.on_measurement_changed)
    thickness_layout.addWidget(editor.measurement_thickness_spinbox)
    measurement_layout.addLayout(thickness_layout)

    line_color_layout = QHBoxLayout()
    line_color_layout.addWidget(QLabel("Line Color:"))
    editor.measurement_line_color_btn = QPushButton("Choose Color...")
    editor.measurement_line_color_btn.clicked.connect(editor.choose_measurement_line_color)
    set_color_button_indicator(editor.measurement_line_color_btn, editor.overlay_renderer.measurement_line_color)
    line_color_layout.addWidget(editor.measurement_line_color_btn)
    measurement_layout.addLayout(line_color_layout)

    text_color_layout = QHBoxLayout()
    text_color_layout.addWidget(QLabel("Text Color:"))
    editor.measurement_text_color_btn = QPushButton("Choose Color...")
    editor.measurement_text_color_btn.clicked.connect(editor.choose_measurement_text_color)
    set_color_button_indicator(editor.measurement_text_color_btn, editor.overlay_renderer.measurement_text_color)
    text_color_layout.addWidget(editor.measurement_text_color_btn)
    measurement_layout.addLayout(text_color_layout)

    end_style_layout = QHBoxLayout()
    end_style_layout.addWidget(QLabel("Start Cap:"))
    editor.measurement_start_end_combo = QComboBox()
    editor.measurement_start_end_combo.addItems(["head", "tick", "dot", "none"])
    editor.measurement_start_end_combo.currentTextChanged.connect(editor._on_selected_measurement_end_style_changed)
    end_style_layout.addWidget(editor.measurement_start_end_combo)

    end_style_layout.addWidget(QLabel("End Cap:"))
    editor.measurement_end_end_combo = QComboBox()
    editor.measurement_end_end_combo.addItems(["head", "tick", "dot", "none"])
    editor.measurement_end_end_combo.currentTextChanged.connect(editor._on_selected_measurement_end_style_changed)
    end_style_layout.addWidget(editor.measurement_end_end_combo)
    measurement_layout.addLayout(end_style_layout)

    measurement_layout.addWidget(QLabel("Measurements:"))
    editor.measurement_table = ClickClearTableWidget()
    editor.measurement_table.setColumnCount(8)
    editor.measurement_table.setHorizontalHeaderLabels([
        "#", "Length", "Label", "Line", "Text", "Width", "Start", "End"
    ])
    editor.measurement_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    editor.measurement_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    editor.measurement_table.set_toggle_deselect_excluded_columns([3, 4])
    editor.measurement_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    editor.measurement_table.setMaximumHeight(170)
    editor.measurement_table.currentCellChanged.connect(
        lambda current_row, _current_col, _prev_row, _prev_col: editor._on_measurement_selection_changed(current_row)
    )
    editor.measurement_table.cellClicked.connect(editor._on_measurement_table_cell_clicked)
    measurement_layout.addWidget(editor.measurement_table)

    apply_all_btn = QPushButton("Apply Style to All")
    apply_all_btn.clicked.connect(editor.apply_current_measurement_style_to_all)
    apply_selected_btn = QPushButton("Apply Style to Selected")
    apply_selected_btn.clicked.connect(editor.apply_current_measurement_style_to_selected)
    apply_btn_layout = QHBoxLayout()
    apply_btn_layout.addWidget(apply_selected_btn)
    apply_btn_layout.addWidget(apply_all_btn)
    measurement_layout.addLayout(apply_btn_layout)

    list_btn_layout = QHBoxLayout()
    remove_btn = QPushButton("Remove Selected")
    remove_btn.clicked.connect(editor.remove_selected_measurement)
    list_btn_layout.addWidget(remove_btn)
    clear_all_btn = QPushButton("Clear All")
    clear_all_btn.clicked.connect(editor.clear_all_measurements)
    list_btn_layout.addWidget(clear_all_btn)
    measurement_layout.addLayout(list_btn_layout)

    editor.measurement_status_label = QLabel(
        "Enable 'Show Annotations', then click 'Draw Measurement' and drag on the image."
    )
    editor.measurement_status_label.setStyleSheet("font-style: italic")
    editor.measurement_status_label.setWordWrap(True)
    measurement_layout.addWidget(editor.measurement_status_label)

    editor.draw_measurement_btn.setEnabled(False)
    editor.move_line_btn.setEnabled(False)
    editor.move_label_btn.setEnabled(False)
    editor.measurement_start_end_combo.setEnabled(True)
    editor.measurement_end_end_combo.setEnabled(True)
    editor.on_measurement_toggled(editor.measurement_checkbox.checkState().value)

    measurement_box.setContentLayout(measurement_layout)
    measurement_box.toggleButton.toggled.connect(editor._on_measurement_section_toggled)
    parent_layout.addWidget(measurement_box)


IMAGE_TYPE_LABELS = {
    "real": "Real space image",
    "diffraction": "Diffraction pattern",
}


def setup_image_type_controls(editor: Any, parent_layout):
    """Image type selector (real-space image vs diffraction pattern), always visible."""
    type_layout = QHBoxLayout()
    type_layout.addWidget(QLabel("Image type:"))
    editor.image_type_combo = QComboBox()
    for key, label in IMAGE_TYPE_LABELS.items():
        editor.image_type_combo.addItem(label, key)
    editor.image_type_combo.setToolTip(
        "Real space: calibrated in nm/µm per pixel.\n"
        "Diffraction pattern: reciprocal space, calibrated from camera length, wavelength and "
        "detector pixel size."
    )
    editor.image_type_combo.currentIndexChanged.connect(editor.on_image_type_combo_changed)
    type_layout.addWidget(editor.image_type_combo, 1)
    parent_layout.addLayout(type_layout)

    hint_layout = QHBoxLayout()
    editor.image_type_hint_label = QLabel("")
    editor.image_type_hint_label.setWordWrap(True)
    editor.image_type_hint_label.setStyleSheet("font-style: italic")
    hint_layout.addWidget(editor.image_type_hint_label, 1)
    editor.image_type_hint_btn = QPushButton("Switch")
    editor.image_type_hint_btn.clicked.connect(editor.on_image_type_hint_clicked)
    hint_layout.addWidget(editor.image_type_hint_btn)
    parent_layout.addLayout(hint_layout)
    editor.image_type_hint_label.setVisible(False)
    editor.image_type_hint_btn.setVisible(False)


def _make_spinbox(minimum: float, maximum: float, decimals: int, step: float, suffix: str = "") -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    spin.setKeyboardTracking(False)
    if suffix:
        spin.setSuffix(suffix)
    return spin


def setup_diffraction_calibration_controls(editor: Any, parent_layout):
    """Calibration of diffraction patterns: camera length, wavelength, pixel size, beam centre."""
    box = QCollapsibleBox("Diffraction Calibration", expanded=True)
    layout = QVBoxLayout()

    editor.diffraction_use_header_checkbox = QCheckBox("Use file header values where available")
    editor.diffraction_use_header_checkbox.setToolTip(
        "Take camera length (detector distance), wavelength, detector pixel size and beam centre "
        "from the .rodhypix header. Untick to enter your own values."
    )
    editor.diffraction_use_header_checkbox.toggled.connect(editor.on_diffraction_use_header_toggled)
    layout.addWidget(editor.diffraction_use_header_checkbox)

    cl_layout = QHBoxLayout()
    cl_layout.addWidget(QLabel("Camera length:"))
    editor.camera_length_spinbox = _make_spinbox(1.0, 100000.0, 1, 1.0, " mm")
    editor.camera_length_spinbox.valueChanged.connect(editor.on_diffraction_parameter_changed)
    cl_layout.addWidget(editor.camera_length_spinbox)
    layout.addLayout(cl_layout)

    wl_layout = QHBoxLayout()
    wl_layout.addWidget(QLabel("Wavelength:"))
    editor.wavelength_spinbox = _make_spinbox(0.00001, 10.0, 5, 0.0001, " Å")
    editor.wavelength_spinbox.valueChanged.connect(editor.on_diffraction_parameter_changed)
    wl_layout.addWidget(editor.wavelength_spinbox)
    editor.voltage_combo = QComboBox()
    editor.voltage_combo.addItem("From kV…", None)
    for kv in COMMON_ACCELERATING_VOLTAGES_KV:
        editor.voltage_combo.addItem(f"{kv} kV", float(kv))
    editor.voltage_combo.setToolTip("Set the relativistic electron wavelength for an accelerating voltage")
    editor.voltage_combo.activated.connect(editor.on_voltage_preset_selected)
    wl_layout.addWidget(editor.voltage_combo)
    layout.addLayout(wl_layout)

    px_layout = QHBoxLayout()
    px_layout.addWidget(QLabel("Detector pixel size:"))
    editor.detector_pixel_spinbox = _make_spinbox(0.01, 10000.0, 2, 1.0, " µm")
    editor.detector_pixel_spinbox.valueChanged.connect(editor.on_diffraction_parameter_changed)
    px_layout.addWidget(editor.detector_pixel_spinbox)
    layout.addLayout(px_layout)

    editor.diffraction_source_label = QLabel("")
    editor.diffraction_source_label.setWordWrap(True)
    editor.diffraction_source_label.setStyleSheet("font-style: italic")
    layout.addWidget(editor.diffraction_source_label)

    layout.addWidget(QLabel("Beam centre (px):"))
    bc_layout = QHBoxLayout()
    bc_layout.addWidget(QLabel("X"))
    editor.beam_center_x_spinbox = _make_spinbox(-100000.0, 100000.0, 1, 0.5)
    editor.beam_center_x_spinbox.valueChanged.connect(editor.on_beam_center_spinbox_changed)
    bc_layout.addWidget(editor.beam_center_x_spinbox)
    bc_layout.addWidget(QLabel("Y"))
    editor.beam_center_y_spinbox = _make_spinbox(-100000.0, 100000.0, 1, 0.5)
    editor.beam_center_y_spinbox.valueChanged.connect(editor.on_beam_center_spinbox_changed)
    bc_layout.addWidget(editor.beam_center_y_spinbox)
    layout.addLayout(bc_layout)

    bc_btn_layout = QHBoxLayout()
    editor.pick_beam_center_btn = QPushButton("⌖  Pick on Image")
    editor.pick_beam_center_btn.setCheckable(True)
    editor.pick_beam_center_btn.setToolTip("Click the direct beam (or the centre of the pattern) on the image")
    editor.pick_beam_center_btn.toggled.connect(editor.on_beam_center_pick_toggled)
    bc_btn_layout.addWidget(editor.pick_beam_center_btn)
    editor.reset_beam_center_btn = QPushButton("Reset")
    editor.reset_beam_center_btn.setToolTip("Reset to the header beam position, or the image centre if there is none")
    editor.reset_beam_center_btn.clicked.connect(editor.reset_beam_center)
    bc_btn_layout.addWidget(editor.reset_beam_center_btn)
    layout.addLayout(bc_btn_layout)

    editor.snap_beam_center_checkbox = QCheckBox("Snap to nearby intensity peak")
    editor.snap_beam_center_checkbox.setToolTip(
        "When picking, refine the click to the intensity-weighted centre of the brightest "
        "spot within 15 px (useful for an unblocked direct beam)."
    )
    editor.snap_beam_center_checkbox.setChecked(True)
    layout.addWidget(editor.snap_beam_center_checkbox)

    editor.diffraction_info_label = QLabel("")
    editor.diffraction_info_label.setWordWrap(True)
    editor.diffraction_info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(editor.diffraction_info_label)

    box.setContentLayout(layout)
    box.toggleButton.toggled.connect(editor._on_diffraction_section_toggled)
    editor.diffraction_box = box
    parent_layout.addWidget(box)


def setup_resolution_ring_controls(editor: Any, parent_layout):
    """Resolution ring overlay controls (diffraction mode replacement for the aperture overlay)."""
    box = QCollapsibleBox("Resolution Rings", expanded=False)
    layout = QVBoxLayout()

    editor.rings_checkbox = QCheckBox("Show Resolution Rings")
    editor.rings_checkbox.stateChanged.connect(editor.on_rings_toggled)
    layout.addWidget(editor.rings_checkbox)

    layout.addWidget(QLabel("Rings (d-spacing, tick to show):"))
    editor.ring_list = QListWidget()
    editor.ring_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    editor.ring_list.setMaximumHeight(130)
    editor.ring_list.itemChanged.connect(editor.on_ring_item_changed)
    layout.addWidget(editor.ring_list)

    add_layout = QHBoxLayout()
    editor.ring_add_spinbox = _make_spinbox(0.01, 1000.0, 3, 0.1, " Å")
    editor.ring_add_spinbox.setValue(1.5)
    add_layout.addWidget(editor.ring_add_spinbox)
    add_btn = QPushButton("Add Ring")
    add_btn.clicked.connect(editor.add_resolution_ring)
    add_layout.addWidget(add_btn)
    layout.addLayout(add_layout)

    list_btn_layout = QHBoxLayout()
    remove_btn = QPushButton("Remove Selected")
    remove_btn.clicked.connect(editor.remove_selected_resolution_rings)
    list_btn_layout.addWidget(remove_btn)
    restore_btn = QPushButton("Restore Presets")
    restore_btn.setToolTip("Reset the list to 0.8, 1.0, 1.2 and 2.0 Å")
    restore_btn.clicked.connect(editor.restore_resolution_ring_presets)
    list_btn_layout.addWidget(restore_btn)
    layout.addLayout(list_btn_layout)

    style_layout = QHBoxLayout()
    style_layout.addWidget(QLabel("Line width (px):"))
    editor.ring_width_spinbox = QSpinBox()
    editor.ring_width_spinbox.setRange(1, 20)
    editor.ring_width_spinbox.setValue(int(editor.overlay_renderer.ring_line_width))
    editor.ring_width_spinbox.valueChanged.connect(editor.on_ring_style_changed)
    style_layout.addWidget(editor.ring_width_spinbox)
    layout.addLayout(style_layout)

    color_layout = QHBoxLayout()
    color_layout.addWidget(QLabel("Ring color:"))
    editor.ring_color_btn = QPushButton("Choose Color...")
    editor.ring_color_btn.clicked.connect(editor.choose_ring_color)
    set_color_button_indicator(editor.ring_color_btn, editor.overlay_renderer.ring_color)
    color_layout.addWidget(editor.ring_color_btn)
    layout.addLayout(color_layout)

    editor.ring_labels_checkbox = QCheckBox("Label rings with resolution")
    editor.ring_labels_checkbox.setChecked(bool(editor.overlay_renderer.ring_show_labels))
    editor.ring_labels_checkbox.stateChanged.connect(editor.on_ring_style_changed)
    layout.addWidget(editor.ring_labels_checkbox)

    editor.beam_marker_checkbox = QCheckBox("Mark beam centre")
    editor.beam_marker_checkbox.setChecked(bool(editor.overlay_renderer.beam_center_marker_enabled))
    editor.beam_marker_checkbox.stateChanged.connect(editor.on_ring_style_changed)
    layout.addWidget(editor.beam_marker_checkbox)

    editor.ring_info_label = QLabel(
        "Ring radius from Bragg's law on a flat detector: R = L·tan(2θ), sin θ = λ/(2d)."
    )
    editor.ring_info_label.setWordWrap(True)
    editor.ring_info_label.setStyleSheet("font-style: italic")
    layout.addWidget(editor.ring_info_label)

    box.setContentLayout(layout)
    editor.rings_box = box
    parent_layout.addWidget(box)
