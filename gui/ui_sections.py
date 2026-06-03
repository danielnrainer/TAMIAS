"""Extracted UI setup sections for the TAMIAS main window."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
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

from gui.collapsible_box import QCollapsibleBox
from gui.custom_widgets import ClickClearTableWidget, SmartDoubleSpinBox, set_color_button_indicator


def setup_preset_controls(editor: Any, parent_layout):
    """Setup imaging mode preset controls on the main editor."""
    preset_box = QCollapsibleBox("Imaging Mode", expanded=True)
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

    preset_info_label = QLabel(
        "To change the pixel size of presets, go to Settings > Manage Presets in the main menu."
    )
    preset_info_label.setWordWrap(True)
    preset_info_label.setStyleSheet("font-style: italic")
    preset_layout.addWidget(preset_info_label)

    if "Standard" in editor.presets:
        editor.preset_combo.setCurrentText("Standard")
        QTimer.singleShot(0, editor._apply_initial_scalebar_defaults)

    editor._update_pixel_size_editable_state(editor.preset_combo.currentText())

    preset_box.setContentLayout(preset_layout)
    parent_layout.addWidget(preset_box)


def setup_brightness_contrast_controls(editor: Any, parent_layout):
    """Setup brightness/contrast controls on the main editor."""
    bc_box = QCollapsibleBox("Brightness/Contrast", expanded=False)
    bc_layout = QVBoxLayout()

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
    editor.scalebar_length_spinbox.setDecimals(2)
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
