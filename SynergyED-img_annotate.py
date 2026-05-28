"""
SynergyED Image Annotating - Main GUI application.
A PyQt6 application for processing TEM images with scalebar addition,
brightness/contrast adjustment, and export capabilities.
"""

import sys
import os
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QFileDialog, QComboBox, QDoubleSpinBox,
    QGroupBox, QCheckBox, QMessageBox, QSpinBox, QDialog, QListWidget,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
    QProgressDialog, QScrollArea, QSplitter, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QModelIndex, QSize
from PyQt6.QtGui import QPixmap, QImage, QAction, QActionGroup, QColor, QFont, QPalette, QBrush, QIcon
from PyQt6.QtWidgets import QColorDialog, QFontDialog

# Helpers
class SmartDoubleSpinBox(QDoubleSpinBox):
    """A QDoubleSpinBox that displays integers without decimals and
    non-integers with up to 2 decimals (without trailing zeros)."""
    def textFromValue(self, value: float) -> str:  # type: ignore[override]
        try:
            if abs(value - round(value)) < 1e-9:
                return str(int(round(value)))
            # Show up to 2 decimals without trailing zeros
            return (f"{value:.2f}").rstrip('0').rstrip('.')
        except Exception:
            return super().textFromValue(value)


class ImageDisplayLabel(QLabel):
    """Image label that supports both click-drag (draw) and label-drag (move) modes."""
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

    def mousePressEvent(self, event):  # type: ignore[override]
        idx = self.indexAt(event.pos())
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

# Import our modules
from core.image_processor import ImageProcessor
from core.overlay_renderer import OverlayRenderer
from utils.preset_manager import PresetManager, PresetStorage
from gui.collapsible_box import QCollapsibleBox
from gui.crop_controller import CropControllerMixin
from gui.batch_processing_dialog import BatchProcessingDialog


class TEMImageEditor(CropControllerMixin, QMainWindow):
    """Main application window for TEM image editing."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SynergyED Image Annotate")
        self.setGeometry(100, 100, 1100, 700)
        
        # Initialize modules
        self.image_processor = ImageProcessor()
        self.overlay_renderer = OverlayRenderer()
        
        # Current file and calibration
        self.current_file: Optional[str] = None
        self.nm_per_pixel = 1.0
        self.pixel_size_unit = "nm"

        # Measurement interaction state
        self._draw_mode_active = False
        self._draw_preview_start: Optional[tuple[int, int]] = None
        self._label_drag_active = False
        self._label_drag_index: Optional[int] = None        # which measurement
        self._label_drag_origin_img: Optional[tuple[float, float]] = None  # img coords at press
        self._label_drag_offset_start: tuple[float, float] = (0.0, 0.0)   # offset at drag start
        self._line_drag_active = False
        self._line_drag_index: Optional[int] = None
        self._line_drag_origin_img: Optional[tuple[float, float]] = None
        self._line_drag_start_start: tuple[float, float] = (0.0, 0.0)
        self._line_drag_start_end: tuple[float, float] = (0.0, 0.0)
        self._scalebar_drag_active = False
        self._scalebar_drag_origin_img: Optional[tuple[float, float]] = None
        self._scalebar_drag_offset_start: tuple[float, float] = (0.0, 0.0)
        self._init_crop_state()
        self._last_rendered_image_size: Optional[tuple[int, int]] = None
        
        # Load presets
        self.presets = PresetStorage.load_presets()
        if "Custom" not in self.presets:
            self.presets["Custom"] = 1.0
        
        # Setup UI
        self.setup_ui()
        self.setup_menu()

        # Theme mode: auto follows the OS color scheme.
        self._theme_mode = "auto"
        self._apply_theme_mode(self._theme_mode)

        app = QApplication.instance()
        if app is not None:
            try:
                app.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)
            except Exception:
                # Older Qt builds may not expose this signal; Auto still applies at startup.
                pass
        
    def setup_menu(self):
        """Setup the menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open Image...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.load_image)
        file_menu.addAction(open_action)
        
        save_action = QAction("Export Image...", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.export_image)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        batch_action = QAction("Batch Processing...", self)
        batch_action.setShortcut("Ctrl+B")
        batch_action.triggered.connect(self.batch_annotate)
        file_menu.addAction(batch_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Image menu
        image_menu = menubar.addMenu("Image")
        crop_rows_action = QAction("Crop Top/Bottom Rows...", self)
        crop_rows_action.triggered.connect(self.crop_top_bottom_rows)
        image_menu.addAction(crop_rows_action)
        
        # Presets menu
        presets_menu = menubar.addMenu("Presets")
        manage_presets_action = QAction("Manage Presets...", self)
        manage_presets_action.triggered.connect(self.manage_presets)
        presets_menu.addAction(manage_presets_action)

        # Theme menu
        theme_menu = menubar.addMenu("Theme")
        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)

        self.theme_actions = {
            "auto": QAction("Auto (System)", self),
            "light": QAction("Light", self),
            "dark": QAction("Dark", self),
        }
        for key, action in self.theme_actions.items():
            action.setCheckable(True)
            action.triggered.connect(lambda checked, mode=key: self._on_theme_action_triggered(mode, checked))
            self.theme_action_group.addAction(action)
            theme_menu.addAction(action)

        self.theme_actions["auto"].setChecked(True)

    def _on_theme_action_triggered(self, mode: str, checked: bool):
        if checked:
            self._apply_theme_mode(mode)

    def _sync_theme_action_checks(self):
        if not hasattr(self, "theme_actions"):
            return
        for mode, action in self.theme_actions.items():
            action.setChecked(mode == self._theme_mode)

    def _is_system_dark_mode(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        try:
            return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except Exception:
            window_color = app.palette().color(QPalette.ColorRole.Window)
            return window_color.lightness() < 128

    def _create_dark_palette(self) -> QPalette:
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
        pal.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        pal.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
        return pal

    def _apply_theme_mode(self, mode: str):
        app = QApplication.instance()
        if app is None:
            return

        resolved_mode = mode
        if mode == "auto":
            resolved_mode = "dark" if self._is_system_dark_mode() else "light"

        if resolved_mode == "dark":
            app.setPalette(self._create_dark_palette())
        else:
            app.setPalette(app.style().standardPalette())

        self._theme_mode = mode
        self._sync_theme_action_checks()

    def _on_system_color_scheme_changed(self, _scheme):
        if self._theme_mode == "auto":
            self._apply_theme_mode("auto")
        
    def setup_ui(self):
        """Setup the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()

        # Left side - Image display
        image_widget = QWidget()
        image_layout = QVBoxLayout()
        
        self.image_label = ImageDisplayLabel()
        self.image_label.setMinimumSize(200, 200)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setStyleSheet(
            "QLabel { background-color: #2b2b2b; border: 2px solid #555; color: #e6e6e6; }"
        )
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setText("No image loaded")
        self.image_label.mouse_pressed.connect(self.on_draw_press)
        self.image_label.mouse_moved.connect(self.on_draw_move)
        self.image_label.mouse_released.connect(self.on_draw_release)
        
        image_layout.addWidget(self.image_label)
        
        self.file_info_label = QLabel("No file loaded")
        self.file_info_label.setStyleSheet("QLabel { color: palette(mid); padding: 5px; }")
        image_layout.addWidget(self.file_info_label)
        image_widget.setLayout(image_layout)
        
        # Right side - Controls in a scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setMinimumWidth(260)
        
        controls_widget = QWidget()
        controls_layout = QVBoxLayout()
        controls_widget.setLayout(controls_layout)
        
        # Load button
        load_btn = QPushButton("Load Image")
        load_btn.setMinimumHeight(40)
        load_btn.clicked.connect(self.load_image)
        controls_layout.addWidget(load_btn)
        
        # Imaging mode preset
        self._setup_preset_controls(controls_layout)

        # Image cropping controls
        self._setup_crop_controls(controls_layout)
        
        # Brightness/Contrast controls
        self._setup_brightness_contrast_controls(controls_layout)
        
        # Transform controls
        self._setup_transform_controls(controls_layout)
        
        # Scalebar controls
        self._setup_scalebar_controls(controls_layout)
        
        # Aperture controls
        self._setup_aperture_controls(controls_layout)

        # Particle measurement controls
        self._setup_measurement_controls(controls_layout)
        
        # Export button
        export_btn = QPushButton("Export Image")
        export_btn.setMinimumHeight(40)
        export_btn.clicked.connect(self.export_image)
        controls_layout.addWidget(export_btn)
        
        controls_layout.addStretch()
        
        # Set the scroll area's widget and add to main layout
        scroll_area.setWidget(controls_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(image_widget)
        splitter.addWidget(scroll_area)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([900, 350])
        splitter.splitterMoved.connect(self._on_main_splitter_moved)
        self.main_splitter = splitter

        main_layout.addWidget(splitter)
        central_widget.setLayout(main_layout)

    def _on_main_splitter_moved(self, _pos: int, _index: int):
        """Rescale the displayed image when pane sizes change via splitter drag."""
        if self.image_processor.has_image():
            self.update_display()
        
    def _setup_preset_controls(self, parent_layout):
        """Setup imaging mode preset controls."""
        preset_box = QCollapsibleBox("Imaging Mode", expanded=True)
        preset_layout = QVBoxLayout()
        
        self.preset_combo = QComboBox()
        self._update_preset_combo()
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        preset_layout.addWidget(QLabel("Select Preset:"))
        preset_layout.addWidget(self.preset_combo)
        
        # Pixel size input
        pixel_size_layout = QHBoxLayout()
        pixel_size_layout.addWidget(QLabel("Pixel size:"))
        
        self.pixel_size_spinbox = QDoubleSpinBox()
        self.pixel_size_spinbox.setRange(0.00001, 100000.0)
        self.pixel_size_spinbox.setDecimals(3)
        self.pixel_size_spinbox.setValue(1.0)
        self.pixel_size_spinbox.valueChanged.connect(self.on_pixel_size_changed)
        pixel_size_layout.addWidget(self.pixel_size_spinbox)
        
        self.pixel_size_unit_combo = QComboBox()
        self.pixel_size_unit_combo.addItems(["nm", "µm"])
        self.pixel_size_unit_combo.currentTextChanged.connect(self.on_pixel_size_unit_changed)
        pixel_size_layout.addWidget(self.pixel_size_unit_combo)
        
        preset_layout.addLayout(pixel_size_layout)

        preset_info_label = QLabel(
            "To change the pixel size of presets, go to Presets > Manage Presets in the main menu."
        )
        preset_info_label.setWordWrap(True)
        # preset_info_label.setStyleSheet("QLabel { color: palette(mid); font-size: 10pt; }")
        preset_info_label.setStyleSheet("QLabel { font-style: italic; }")
        preset_layout.addWidget(preset_info_label)
        
        # Set default preset
        if "Standard" in self.presets:
            self.preset_combo.setCurrentText("Standard")
            # Apply preset-specific scalebar defaults for Standard
            QTimer.singleShot(0, self._apply_initial_scalebar_defaults)

        self._update_pixel_size_editable_state(self.preset_combo.currentText())
        
        preset_box.setContentLayout(preset_layout)
        parent_layout.addWidget(preset_box)
        
    def _setup_brightness_contrast_controls(self, parent_layout):
        """Setup brightness/contrast controls."""
        bc_box = QCollapsibleBox("Brightness/Contrast", expanded=False)
        bc_layout = QVBoxLayout()
        
        auto_btn = QPushButton("Auto Adjust")
        auto_btn.clicked.connect(self.auto_adjust)
        bc_layout.addWidget(auto_btn)
        
        # Min slider
        bc_layout.addWidget(QLabel("Min Value:"))
        min_layout = QHBoxLayout()
        self.min_slider = QSlider(Qt.Orientation.Horizontal)
        self.min_slider.setRange(0, 255)
        self.min_slider.setValue(0)
        self.min_slider.valueChanged.connect(self.on_brightness_contrast_changed)
        self.min_value_label = QLabel("0")
        min_layout.addWidget(self.min_slider)
        min_layout.addWidget(self.min_value_label)
        bc_layout.addLayout(min_layout)
        
        # Max slider
        bc_layout.addWidget(QLabel("Max Value:"))
        max_layout = QHBoxLayout()
        self.max_slider = QSlider(Qt.Orientation.Horizontal)
        self.max_slider.setRange(0, 255)
        self.max_slider.setValue(255)
        self.max_slider.valueChanged.connect(self.on_brightness_contrast_changed)
        self.max_value_label = QLabel("255")
        max_layout.addWidget(self.max_slider)
        max_layout.addWidget(self.max_value_label)
        bc_layout.addLayout(max_layout)
        
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self.reset_brightness_contrast)
        bc_layout.addWidget(reset_btn)
        
        bc_box.setContentLayout(bc_layout)
        parent_layout.addWidget(bc_box)

    def _setup_transform_controls(self, parent_layout):
        """Setup image transform controls."""
        transform_box = QCollapsibleBox("Image Transform", expanded=False)
        transform_layout = QHBoxLayout()
        
        flip_h_btn = QPushButton("Flip Horizontal")
        flip_h_btn.clicked.connect(self.flip_horizontal)
        transform_layout.addWidget(flip_h_btn)
        
        flip_v_btn = QPushButton("Flip Vertical")
        flip_v_btn.clicked.connect(self.flip_vertical)
        transform_layout.addWidget(flip_v_btn)
        
        transform_box.setContentLayout(transform_layout)
        parent_layout.addWidget(transform_box)
        
    def _setup_scalebar_controls(self, parent_layout):
        """Setup scalebar controls."""
        scalebar_box = QCollapsibleBox("Scalebar", expanded=False)
        scalebar_layout = QVBoxLayout()
        
        self.scalebar_checkbox = QCheckBox("Show Scalebar")
        self.scalebar_checkbox.setChecked(True)
        self.scalebar_checkbox.stateChanged.connect(self.on_scalebar_toggled)
        scalebar_layout.addWidget(self.scalebar_checkbox)

        self.move_scalebar_btn = QPushButton("☰  Move Scalebar Box")
        self.move_scalebar_btn.setCheckable(True)
        self.move_scalebar_btn.setToolTip(
            "Click and drag on the image to reposition the full scalebar box"
        )
        self.move_scalebar_btn.toggled.connect(self.on_scalebar_drag_mode_toggled)
        scalebar_layout.addWidget(self.move_scalebar_btn)
        
        # Length
        length_layout = QHBoxLayout()
        length_layout.addWidget(QLabel("Length:"))
        self.scalebar_length_spinbox = SmartDoubleSpinBox()
        self.scalebar_length_spinbox.setDecimals(2)
        self.scalebar_length_spinbox.setSingleStep(0.1)
        self.scalebar_length_spinbox.setRange(0.01, 10000.0)
        self.scalebar_length_spinbox.setValue(100.0)
        self.scalebar_length_spinbox.valueChanged.connect(self.on_scalebar_changed)
        # Track raw user text to preserve trailing zeros if provided
        try:
            self.scalebar_length_spinbox.lineEdit().textEdited.connect(self.on_scalebar_length_text_edited)
        except Exception:
            pass
        length_layout.addWidget(self.scalebar_length_spinbox)
        
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["nm", "µm"])
        self.unit_combo.currentTextChanged.connect(self.on_scalebar_unit_changed)
        length_layout.addWidget(self.unit_combo)
        scalebar_layout.addLayout(length_layout)
        
        # Thickness
        thickness_layout = QHBoxLayout()
        thickness_layout.addWidget(QLabel("Thickness (px):"))
        self.scalebar_thickness_spinbox = QSpinBox()
        self.scalebar_thickness_spinbox.setRange(5, 100)
        self.scalebar_thickness_spinbox.setValue(15)
        self.scalebar_thickness_spinbox.valueChanged.connect(self.on_scalebar_changed)
        thickness_layout.addWidget(self.scalebar_thickness_spinbox)
        scalebar_layout.addLayout(thickness_layout)
        
        # Position
        scalebar_layout.addWidget(QLabel("Position:"))
        self.position_combo = QComboBox()
        self.position_combo.addItems(["bottom-right", "bottom-left", "top-right", "top-left", "custom"])
        self.position_combo.currentTextChanged.connect(self.on_scalebar_changed)
        scalebar_layout.addWidget(self.position_combo)
        
        # Bar color
        bar_color_layout = QHBoxLayout()
        bar_color_layout.addWidget(QLabel("Bar Color:"))
        self.bar_color_btn = QPushButton("Choose Color…")
        self.bar_color_btn.clicked.connect(self.choose_bar_color)
        set_color_button_indicator(self.bar_color_btn, self.overlay_renderer.bar_color)
        bar_color_layout.addWidget(self.bar_color_btn)
        scalebar_layout.addLayout(bar_color_layout)
        
        # Text color
        text_color_layout = QHBoxLayout()
        text_color_layout.addWidget(QLabel("Text Color:"))
        self.text_color_btn = QPushButton("Choose Color…")
        self.text_color_btn.clicked.connect(self.choose_text_color)
        set_color_button_indicator(self.text_color_btn, self.overlay_renderer.text_color)
        text_color_layout.addWidget(self.text_color_btn)
        scalebar_layout.addLayout(text_color_layout)
        
        # Font
        font_layout = QHBoxLayout()
        self.font_label = QLabel("Font: Arial, 20pt")
        choose_font_btn = QPushButton("Choose Font…")
        choose_font_btn.clicked.connect(self.choose_font)
        font_layout.addWidget(self.font_label)
        font_layout.addWidget(choose_font_btn)
        scalebar_layout.addLayout(font_layout)
        
        # Background box
        bg_inner_box = QCollapsibleBox("Background Box", expanded=False)
        bg_layout = QVBoxLayout()
        self.bg_checkbox = QCheckBox("Enable background box for legibility")
        self.bg_checkbox.stateChanged.connect(self.on_bg_toggled)
        bg_layout.addWidget(self.bg_checkbox)
        
        bg_controls_layout = QHBoxLayout()
        self.bg_color_btn = QPushButton("Choose Color…")
        self.bg_color_btn.clicked.connect(self.choose_bg_color)
        set_color_button_indicator(self.bg_color_btn, self.overlay_renderer.scalebar_bg_color)
        bg_controls_layout.addWidget(self.bg_color_btn)
        
        bg_controls_layout.addWidget(QLabel("Opacity:"))
        self.bg_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.bg_opacity_slider.setRange(0, 255)
        self.bg_opacity_slider.setValue(255)
        self.bg_opacity_slider.valueChanged.connect(self.on_bg_opacity_changed)
        bg_controls_layout.addWidget(self.bg_opacity_slider)
        
        bg_layout.addLayout(bg_controls_layout)
        self.bg_checkbox.setChecked(True)
        bg_inner_box.setContentLayout(bg_layout)
        scalebar_layout.addWidget(bg_inner_box)
        
        scalebar_box.setContentLayout(scalebar_layout)
        parent_layout.addWidget(scalebar_box)
        
    def _setup_aperture_controls(self, parent_layout):
        """Setup aperture overlay controls."""
        aperture_box = QCollapsibleBox("Aperture Overlay", expanded=False)
        aperture_layout = QVBoxLayout()
        
        self.aperture_checkbox = QCheckBox("Show Aperture")
        self.aperture_checkbox.setChecked(False)
        self.aperture_checkbox.stateChanged.connect(self.on_aperture_toggled)
        aperture_layout.addWidget(self.aperture_checkbox)
        
        # Size selector
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Nominal diameter (µm):"))
        self.aperture_size_combo = QComboBox()
        self.aperture_size_combo.addItems(["300", "200", "100", "50"])
        self.aperture_size_combo.setCurrentText("100")
        self.aperture_size_combo.currentTextChanged.connect(self.on_aperture_size_changed)
        size_layout.addWidget(self.aperture_size_combo)
        aperture_layout.addLayout(size_layout)
        
        self.aperture_info_label = QLabel("Apparent diameter: 2.0 µm")
        self.aperture_info_label.setStyleSheet("QLabel { color: palette(mid); font-size: 10pt; }")
        aperture_layout.addWidget(self.aperture_info_label)
        
        # Color
        aperture_color_layout = QHBoxLayout()
        aperture_color_layout.addWidget(QLabel("Circle color:"))
        self.aperture_color_btn = QPushButton("Choose Color...")
        self.aperture_color_btn.clicked.connect(self.choose_aperture_color)
        set_color_button_indicator(self.aperture_color_btn, self.overlay_renderer.aperture_color)
        aperture_color_layout.addWidget(self.aperture_color_btn)
        aperture_layout.addLayout(aperture_color_layout)
        
        aperture_box.setContentLayout(aperture_layout)
        parent_layout.addWidget(aperture_box)

    def _setup_measurement_controls(self, parent_layout):
        """Setup particle measurement controls."""
        measurement_box = QCollapsibleBox("Particle Measurement", expanded=False)
        measurement_layout = QVBoxLayout()

        self.measurement_checkbox = QCheckBox("Show Measurement Annotations")
        self.measurement_checkbox.setChecked(False)
        self.measurement_checkbox.stateChanged.connect(self.on_measurement_toggled)
        measurement_layout.addWidget(self.measurement_checkbox)

        self.measurement_label_checkbox = QCheckBox("Include Length Label")
        self.measurement_label_checkbox.setChecked(self.overlay_renderer.measurement_show_label)
        self.measurement_label_checkbox.stateChanged.connect(self.on_measurement_changed)
        measurement_layout.addWidget(self.measurement_label_checkbox)

        # Draw mode toggle
        self.draw_measurement_btn = QPushButton("✏  Draw Measurement")
        self.draw_measurement_btn.setCheckable(True)
        self.draw_measurement_btn.setToolTip(
            "Click and drag on the image to draw a measurement line"
        )
        self.draw_measurement_btn.toggled.connect(self.on_draw_mode_toggled)
        measurement_layout.addWidget(self.draw_measurement_btn)

        self.move_label_btn = QPushButton("☰  Move Label")
        self.move_label_btn.setCheckable(True)
        self.move_label_btn.setToolTip(
            "Click and drag a measurement label to reposition it"
        )
        self.move_label_btn.toggled.connect(self.on_label_drag_mode_toggled)
        measurement_layout.addWidget(self.move_label_btn)

        self.move_line_btn = QPushButton("↔  Move Line")
        self.move_line_btn.setCheckable(True)
        self.move_line_btn.setToolTip(
            "Click and drag a measurement line to move the full annotation"
        )
        self.move_line_btn.toggled.connect(self.on_line_drag_mode_toggled)
        measurement_layout.addWidget(self.move_line_btn)

        # Style controls
        unit_layout = QHBoxLayout()
        unit_layout.addWidget(QLabel("Length Unit:"))
        self.measurement_unit_combo = QComboBox()
        self.measurement_unit_combo.addItems(["nm", "µm"])
        self.measurement_unit_combo.currentTextChanged.connect(self.on_measurement_changed)
        unit_layout.addWidget(self.measurement_unit_combo)
        measurement_layout.addLayout(unit_layout)

        thickness_layout = QHBoxLayout()
        thickness_layout.addWidget(QLabel("Line Width (px):"))
        self.measurement_thickness_spinbox = QSpinBox()
        self.measurement_thickness_spinbox.setRange(1, 20)
        self.measurement_thickness_spinbox.setValue(self.overlay_renderer.measurement_line_width)
        self.measurement_thickness_spinbox.valueChanged.connect(self.on_measurement_changed)
        thickness_layout.addWidget(self.measurement_thickness_spinbox)
        measurement_layout.addLayout(thickness_layout)

        line_color_layout = QHBoxLayout()
        line_color_layout.addWidget(QLabel("Line Color:"))
        self.measurement_line_color_btn = QPushButton("Choose Color...")
        self.measurement_line_color_btn.clicked.connect(self.choose_measurement_line_color)
        set_color_button_indicator(self.measurement_line_color_btn, self.overlay_renderer.measurement_line_color)
        line_color_layout.addWidget(self.measurement_line_color_btn)
        measurement_layout.addLayout(line_color_layout)

        text_color_layout = QHBoxLayout()
        text_color_layout.addWidget(QLabel("Text Color:"))
        self.measurement_text_color_btn = QPushButton("Choose Color...")
        self.measurement_text_color_btn.clicked.connect(self.choose_measurement_text_color)
        set_color_button_indicator(self.measurement_text_color_btn, self.overlay_renderer.measurement_text_color)
        text_color_layout.addWidget(self.measurement_text_color_btn)
        measurement_layout.addLayout(text_color_layout)

        end_style_layout = QHBoxLayout()
        end_style_layout.addWidget(QLabel("Start Cap:"))
        self.measurement_start_end_combo = QComboBox()
        self.measurement_start_end_combo.addItems(["head", "tick", "dot", "none"])
        self.measurement_start_end_combo.currentTextChanged.connect(self._on_selected_measurement_end_style_changed)
        end_style_layout.addWidget(self.measurement_start_end_combo)

        end_style_layout.addWidget(QLabel("End Cap:"))
        self.measurement_end_end_combo = QComboBox()
        self.measurement_end_end_combo.addItems(["head", "tick", "dot", "none"])
        self.measurement_end_end_combo.currentTextChanged.connect(self._on_selected_measurement_end_style_changed)
        end_style_layout.addWidget(self.measurement_end_end_combo)
        measurement_layout.addLayout(end_style_layout)
        
        # Measurement list
        measurement_layout.addWidget(QLabel("Measurements:"))
        self.measurement_table = ClickClearTableWidget()
        self.measurement_table.setColumnCount(8)
        self.measurement_table.setHorizontalHeaderLabels([
            "#", "Length", "Label", "Line", "Text", "Width", "Start", "End"
        ])
        self.measurement_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.measurement_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.measurement_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.measurement_table.setMaximumHeight(170)
        self.measurement_table.currentCellChanged.connect(
            lambda current_row, _current_col, _prev_row, _prev_col: self._on_measurement_selection_changed(current_row)
        )
        self.measurement_table.cellClicked.connect(self._on_measurement_table_cell_clicked)
        measurement_layout.addWidget(self.measurement_table)


        apply_all_btn = QPushButton("Apply Style to All")
        apply_all_btn.clicked.connect(self.apply_current_measurement_style_to_all)
        apply_selected_btn = QPushButton("Apply Style to Selected")
        apply_selected_btn.clicked.connect(self.apply_current_measurement_style_to_selected)
        apply_btn_layout = QHBoxLayout()
        apply_btn_layout.addWidget(apply_selected_btn)
        apply_btn_layout.addWidget(apply_all_btn)
        measurement_layout.addLayout(apply_btn_layout)

        list_btn_layout = QHBoxLayout()
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_selected_measurement)
        list_btn_layout.addWidget(remove_btn)
        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.clicked.connect(self.clear_all_measurements)
        list_btn_layout.addWidget(clear_all_btn)
        measurement_layout.addLayout(list_btn_layout)

        self.measurement_status_label = QLabel(
            "Enable 'Show Annotations', then click 'Draw Measurement' and drag on the image."
        )
        self.measurement_status_label.setStyleSheet("QLabel { color: palette(mid); font-size: 10pt; }")
        self.measurement_status_label.setWordWrap(True)
        measurement_layout.addWidget(self.measurement_status_label)

        # Start disabled until measurement overlay is enabled.
        self.draw_measurement_btn.setEnabled(False)
        self.move_line_btn.setEnabled(False)
        self.move_label_btn.setEnabled(False)
        self.measurement_start_end_combo.setEnabled(False)
        self.measurement_end_end_combo.setEnabled(False)

        measurement_box.setContentLayout(measurement_layout)
        parent_layout.addWidget(measurement_box)
        
    # Event handlers
    def load_image(self):
        """Load an image file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "",
            "Image Files (*.rodhypix *.tif *.tiff *.png *.jpg *.jpeg *.bmp);;RODHyPix Files (*.rodhypix);;TIFF Files (*.tif *.tiff);;All Files (*.*)"
        )
        
        if file_path:
            success, error, dimensions, pixel_metadata = self.image_processor.load_image(file_path)
            
            if success:
                self.current_file = file_path
                width, height = dimensions
                filename = Path(file_path).name
                self.file_info_label.setText(f"File: {filename} | Size: {width}x{height}px")
                
                # If we got pixel metadata from rodhypix file, automatically set the calibration
                if pixel_metadata and 'pixel_size_nm' in pixel_metadata:
                    # Set the pixel size calibration automatically
                    nm_per_pixel = float(pixel_metadata['pixel_size_nm'])
                    um_per_pixel = float(pixel_metadata['pixel_size_um'])
                    
                    # Determine which unit is more appropriate (prefer nm for < 1 µm, µm for >= 1 µm)
                    preferred_unit = "µm" if um_per_pixel >= 1.0 else "nm"

                    # Keep calibration in nm/pixel internally and avoid signal-driven overwrites.
                    self.nm_per_pixel = nm_per_pixel
                    self.pixel_size_unit = preferred_unit
                    self.pixel_size_unit_combo.blockSignals(True)
                    self.pixel_size_unit_combo.setCurrentText(preferred_unit)
                    self.pixel_size_unit_combo.blockSignals(False)
                    
                    # Show a message to the user
                    info_text = f"Pixel size from file header: {nm_per_pixel:.1f} nm ({um_per_pixel:.3f} µm)"
                    print(info_text)
                    self.file_info_label.setText(f"File: {filename} | Size: {width}x{height}px | {info_text}")
                
                # Auto adjust and display
                self.image_processor.auto_adjust_contrast()
                self._update_brightness_sliders()

                # Reset overlays that are image-specific
                self._reset_image_specific_overlays(disable_scalebar=True)

                self._refresh_scale_information()
            else:
                QMessageBox.critical(self, "Error", f"Failed to load image:\n{error}")

    def _reset_image_specific_overlays(self, disable_scalebar: bool):
        """Reset overlays that depend on source image geometry."""
        if disable_scalebar:
            self.scalebar_checkbox.setChecked(False)
        self.overlay_renderer.scalebar_offset = (0.0, 0.0)
        if hasattr(self, 'position_combo'):
            self.position_combo.blockSignals(True)
            self.position_combo.setCurrentText(self.overlay_renderer.scalebar_position)
            self.position_combo.blockSignals(False)

        self.overlay_renderer.measurements.clear()
        self.overlay_renderer.measurement_preview = None
        self._draw_preview_start = None
        self._label_drag_index = None
        self._line_drag_index = None
        self._scalebar_drag_origin_img = None
        self.reset_crop_state()
        if hasattr(self, 'measurement_table'):
            self.measurement_table.setRowCount(0)
        self._on_measurement_selection_changed(-1)
    
    def on_preset_changed(self, preset_name: str):
        """Handle preset selection change."""
        self._update_pixel_size_editable_state(preset_name)
        if preset_name in self.presets:
            try:
                npp = float(self.presets[preset_name])
                if npp <= 0:
                    npp = 1.0
            except Exception:
                npp = 1.0
            
            self.nm_per_pixel = npp
            
            # Set preset-specific scalebar defaults (only if UI is fully initialized)
            if hasattr(self, 'unit_combo') and hasattr(self, 'scalebar_length_spinbox'):
                if preset_name == "Standard":
                    self.unit_combo.setCurrentText("µm")
                    self.scalebar_length_spinbox.setValue(5.0)
                    self.scalebar_length_text_raw = "5"
                elif preset_name == "High Res":
                    self.unit_combo.setCurrentText("nm")
                    self.scalebar_length_spinbox.setValue(500.0)
                    self.scalebar_length_text_raw = "500"

            self._refresh_scale_information()

    def _refresh_scale_information(self):
        """Refresh scale-dependent UI and overlays after calibration or preset updates."""
        self._update_pixel_size_display()
        self._update_measurement_info_label()
        if hasattr(self, 'scalebar_length_spinbox'):
            self.on_scalebar_changed()
        else:
            self.update_display()
    
    def _update_pixel_size_display(self):
        """Update pixel size spinbox display."""
        display_value = self.nm_per_pixel / 1000.0 if self.pixel_size_unit == "µm" else self.nm_per_pixel
        self.pixel_size_spinbox.blockSignals(True)
        self.pixel_size_spinbox.setValue(display_value)
        self.pixel_size_spinbox.blockSignals(False)
    
    def on_pixel_size_changed(self, value: float):
        """Handle manual pixel size change."""
        if self.preset_combo.currentText() != "Custom":
            return
        npp = value * 1000.0 if self.pixel_size_unit == "µm" else value
        if npp <= 0:
            npp = 1.0
        self.nm_per_pixel = npp
        self.presets["Custom"] = npp
        self._update_measurement_info_label()
        self.update_display()
    
    def on_pixel_size_unit_changed(self, unit: str):
        """Handle pixel size unit change."""
        old_unit = self.pixel_size_unit
        self.pixel_size_unit = unit
        
        current_val = self.pixel_size_spinbox.value()
        self.pixel_size_spinbox.blockSignals(True)
        if old_unit == "nm" and unit == "µm":
            self.pixel_size_spinbox.setValue(current_val / 1000.0)
        elif old_unit == "µm" and unit == "nm":
            self.pixel_size_spinbox.setValue(current_val * 1000.0)
        self.pixel_size_spinbox.blockSignals(False)
        self._update_measurement_info_label()
        self.update_display()
    
    def on_brightness_contrast_changed(self):
        """Handle brightness/contrast slider changes."""
        min_val = self.min_slider.value()
        max_val = self.max_slider.value()
        
        if min_val >= max_val:
            if self.sender() == self.min_slider:
                min_val = max_val - 1
                self.min_slider.setValue(min_val)
            else:
                max_val = min_val + 1
                self.max_slider.setValue(max_val)
        
        self.min_value_label.setText(str(min_val))
        self.max_value_label.setText(str(max_val))
        
        self.image_processor.set_brightness_contrast(min_val, max_val)
        self.update_display()
    
    def reset_brightness_contrast(self):
        """Reset brightness/contrast."""
        self.image_processor.reset_brightness_contrast()
        self._update_brightness_sliders()
        self._update_measurement_info_label()
        self.update_display()
    
    def auto_adjust(self):
        """Auto-adjust brightness/contrast."""
        self.image_processor.auto_adjust_contrast()
        self._update_brightness_sliders()
        self.update_display()
    
    def _update_brightness_sliders(self):
        """Update brightness/contrast sliders from processor."""
        self.min_slider.setValue(self.image_processor.min_val)
        self.max_slider.setValue(self.image_processor.max_val)
        self.min_value_label.setText(str(self.image_processor.min_val))
        self.max_value_label.setText(str(self.image_processor.max_val))
    
    def flip_horizontal(self):
        """Flip image horizontally."""
        self.image_processor.flip_horizontal()
        self.update_display()
    
    def flip_vertical(self):
        """Flip image vertically."""
        self.image_processor.flip_vertical()
        self.update_display()
    
    def on_scalebar_toggled(self, state):
        """Handle scalebar checkbox toggle."""
        enabled = (state == Qt.CheckState.Checked.value)
        self.overlay_renderer.scalebar_enabled = enabled
        self.move_scalebar_btn.setEnabled(enabled)
        if not enabled and self.move_scalebar_btn.isChecked():
            self.move_scalebar_btn.setChecked(False)
        self.update_display()
    
    def on_scalebar_changed(self):
        """Handle scalebar parameter changes."""
        # numeric value for pixel conversion
        self.overlay_renderer.scalebar_length_value = float(self.scalebar_length_spinbox.value())
        self.overlay_renderer.scalebar_thickness = self.scalebar_thickness_spinbox.value()
        selected_position = self.position_combo.currentText()
        # Preset anchors are absolute to the full image; "custom" keeps current dragged offset.
        if selected_position != "custom":
            self.overlay_renderer.scalebar_position = selected_position
            self.overlay_renderer.scalebar_offset = (0.0, 0.0)
        # Preserve label decimals as typed, if available and valid
        override = getattr(self, 'scalebar_length_text_raw', None)
        if isinstance(override, str) and override.strip() != "":
            try:
                float(override)
                self.overlay_renderer.scalebar_label_override = override.strip()
            except ValueError:
                self.overlay_renderer.scalebar_label_override = None
        else:
            self.overlay_renderer.scalebar_label_override = None
        self.update_display()
    
    def on_scalebar_unit_changed(self, unit: str):
        """Handle scalebar unit change."""
        self.overlay_renderer.scalebar_unit = unit
        # Update renderer label consistency
        self.on_scalebar_changed()
        self.update_display()

    def on_scalebar_length_text_edited(self, text: str):
        """Capture raw text as typed in the length spinbox to preserve trailing zeros in label."""
        self.scalebar_length_text_raw = text
        self.on_scalebar_changed()
    
    def choose_bar_color(self):
        """Choose custom bar color."""
        color = QColorDialog.getColor(self.overlay_renderer.bar_color, self, "Choose Scalebar Bar Color")
        if color.isValid():
            self.overlay_renderer.bar_color = color
            set_color_button_indicator(self.bar_color_btn, self.overlay_renderer.bar_color)
            self.update_display()
    
    def choose_text_color(self):
        """Choose custom text color."""
        color = QColorDialog.getColor(self.overlay_renderer.text_color, self, "Choose Scalebar Text Color")
        if color.isValid():
            self.overlay_renderer.text_color = color
            set_color_button_indicator(self.text_color_btn, self.overlay_renderer.text_color)
            self.update_display()
    
    def choose_font(self):
        """Choose scalebar font."""
        options = QFontDialog.FontDialogOption.ScalableFonts | QFontDialog.FontDialogOption.DontUseNativeDialog
        font, ok = QFontDialog.getFont(self.overlay_renderer.scalebar_font, self, "Choose Scalebar Font", options=options)
        if ok:
            try:
                self.overlay_renderer.scalebar_font = QFont(font)
                pt = font.pointSize()
                px = font.pixelSize()
                size_text = f"{pt}pt" if pt > 0 else f"{px}px" if px > 0 else ""
                label_text = f"Font: {font.family()}" + (f", {size_text}" if size_text else "")
                self.font_label.setText(label_text)
            except Exception as e:
                QMessageBox.warning(self, "Font Error", f"Selected font could not be applied.\n{e}")
                self.overlay_renderer.scalebar_font = QFont("Arial", 20)
                self.font_label.setText("Font: Arial, 20pt")
            self.update_display()
    
    def on_bg_toggled(self, state):
        """Handle background box toggle."""
        enabled = (state == Qt.CheckState.Checked.value)
        self.bg_color_btn.setEnabled(enabled)
        self.bg_opacity_slider.setEnabled(enabled)
        self.overlay_renderer.scalebar_bg_enabled = enabled
        self.update_display()
    
    def choose_bg_color(self):
        """Choose background color."""
        color = QColorDialog.getColor(self.overlay_renderer.scalebar_bg_color, self, "Choose Background Color")
        if color.isValid():
            self.overlay_renderer.scalebar_bg_color = color
            set_color_button_indicator(self.bg_color_btn, self.overlay_renderer.scalebar_bg_color)
            self.update_display()
    
    def on_bg_opacity_changed(self, value: int):
        """Handle background opacity change."""
        self.overlay_renderer.scalebar_bg_opacity = value
        self.update_display()
    
    def on_aperture_toggled(self, state):
        """Handle aperture checkbox toggle."""
        self.overlay_renderer.aperture_enabled = (state == Qt.CheckState.Checked.value)
        self.update_display()
    
    def on_aperture_size_changed(self, size_str: str):
        """Handle aperture size change."""
        try:
            nominal_size = int(size_str)
            self.overlay_renderer.aperture_nominal_size = nominal_size
            apparent_diameter = nominal_size / 50.0
            self.aperture_info_label.setText(f"Apparent diameter: {apparent_diameter:.1f} µm")
            self.update_display()
        except ValueError:
            pass
    
    def choose_aperture_color(self):
        """Choose aperture color."""
        color = QColorDialog.getColor(self.overlay_renderer.aperture_color, self, "Choose Aperture Color")
        if color.isValid():
            self.overlay_renderer.aperture_color = color
            set_color_button_indicator(self.aperture_color_btn, self.overlay_renderer.aperture_color)
            self.update_display()

    def on_measurement_toggled(self, state):
        """Enable or disable particle measurement overlay."""
        enabled = (state == Qt.CheckState.Checked.value)
        self.overlay_renderer.measurement_enabled = enabled
        self.draw_measurement_btn.setEnabled(enabled)
        self.move_line_btn.setEnabled(enabled)
        self.move_label_btn.setEnabled(enabled and self._has_any_visible_measurement_labels())
        self._sync_measurement_end_style_controls_enabled()
        if not enabled:
            if self.draw_measurement_btn.isChecked():
                self.draw_measurement_btn.setChecked(False)
            if self.move_line_btn.isChecked():
                self.move_line_btn.setChecked(False)
            if self.move_label_btn.isChecked():
                self.move_label_btn.setChecked(False)
        self.update_display()

    def on_measurement_changed(self):
        """Handle measurement style changes (unit, thickness, label visibility)."""
        self.overlay_renderer.measurement_unit = self.measurement_unit_combo.currentText()
        selected_rows = self._get_selected_measurement_rows()
        if selected_rows:
            for row in selected_rows:
                if 0 <= row < len(self.overlay_renderer.measurements):
                    self.overlay_renderer.measurements[row]["line_width"] = self.measurement_thickness_spinbox.value()
                    self.overlay_renderer.measurements[row]["show_label"] = self.measurement_label_checkbox.isChecked()
        else:
            self.overlay_renderer.measurement_line_width = self.measurement_thickness_spinbox.value()
            self.overlay_renderer.measurement_show_label = self.measurement_label_checkbox.isChecked()
        move_labels_enabled = self._has_any_visible_measurement_labels()
        self.move_label_btn.setEnabled(move_labels_enabled)
        if not move_labels_enabled and self.move_label_btn.isChecked():
            self.move_label_btn.setChecked(False)
            self.measurement_status_label.setText(
                "Length labels hidden. Enable 'Include Length Label' to move label positions."
            )
        self._refresh_measurements_list()
        for row in selected_rows:
            if 0 <= row < self.measurement_table.rowCount():
                self.measurement_table.selectRow(row)
        self._sync_measurement_end_style_controls_enabled()
        self.update_display()

    def _sync_measurement_end_style_controls_enabled(self):
        """Enable cap-style controls only when overlay is on and a measurement is selected."""
        has_selection = len(self._get_selected_measurement_rows()) > 0
        enabled = self.overlay_renderer.measurement_enabled and has_selection
        self.measurement_start_end_combo.setEnabled(enabled)
        self.measurement_end_end_combo.setEnabled(enabled)

    def _on_measurement_selection_changed(self, row: int):
        """Load selected measurement cap styles into the end-style controls."""
        if row < 0 or row >= len(self.overlay_renderer.measurements):
            self.measurement_label_checkbox.blockSignals(True)
            self.measurement_label_checkbox.setChecked(self.overlay_renderer.measurement_show_label)
            self.measurement_label_checkbox.blockSignals(False)
            set_color_button_indicator(self.measurement_line_color_btn, self.overlay_renderer.measurement_line_color)
            set_color_button_indicator(self.measurement_text_color_btn, self.overlay_renderer.measurement_text_color)
            self.move_label_btn.setEnabled(self.overlay_renderer.measurement_enabled and self._has_any_visible_measurement_labels())
            self._sync_measurement_end_style_controls_enabled()
            return

        m = self.overlay_renderer.measurements[row]
        start_cap = str(m.get("start_cap", "head")).strip().lower()
        end_cap = str(m.get("end_cap", "head")).strip().lower()
        show_label = bool(m.get("show_label", self.overlay_renderer.measurement_show_label))
        line_width = int(m.get("line_width", self.overlay_renderer.measurement_line_width))
        if start_cap not in {"head", "tick", "dot", "none"}:
            start_cap = "head"
        if end_cap not in {"head", "tick", "dot", "none"}:
            end_cap = "head"

        self.measurement_label_checkbox.blockSignals(True)
        self.measurement_label_checkbox.setChecked(show_label)
        self.measurement_label_checkbox.blockSignals(False)
        self.measurement_thickness_spinbox.blockSignals(True)
        self.measurement_thickness_spinbox.setValue(max(1, min(20, line_width)))
        self.measurement_thickness_spinbox.blockSignals(False)
        self.measurement_start_end_combo.blockSignals(True)
        self.measurement_end_end_combo.blockSignals(True)
        self.measurement_start_end_combo.setCurrentText(start_cap)
        self.measurement_end_end_combo.setCurrentText(end_cap)
        self.measurement_start_end_combo.blockSignals(False)
        self.measurement_end_end_combo.blockSignals(False)
        line_color = QColor(m.get("line_color", self.overlay_renderer.measurement_line_color))
        text_color = QColor(m.get("text_color", self.overlay_renderer.measurement_text_color))
        set_color_button_indicator(self.measurement_line_color_btn, line_color)
        set_color_button_indicator(self.measurement_text_color_btn, text_color)
        self.move_label_btn.setEnabled(self.overlay_renderer.measurement_enabled and self._has_any_visible_measurement_labels())
        self._sync_measurement_end_style_controls_enabled()

    def _on_selected_measurement_end_style_changed(self):
        """Persist end-style changes for the currently selected measurement."""
        selected_rows = self._get_selected_measurement_rows()
        if not selected_rows:
            return
        for row in selected_rows:
            if 0 <= row < len(self.overlay_renderer.measurements):
                self.overlay_renderer.measurements[row]["start_cap"] = self.measurement_start_end_combo.currentText()
                self.overlay_renderer.measurements[row]["end_cap"] = self.measurement_end_end_combo.currentText()
        self._refresh_measurements_list()
        for row in selected_rows:
            if 0 <= row < self.measurement_table.rowCount():
                self.measurement_table.selectRow(row)
        self.update_display()

    def _on_measurement_table_cell_clicked(self, row: int, col: int):
        """Open color pickers directly when clicking color swatches in the table."""
        if row < 0 or row >= len(self.overlay_renderer.measurements):
            return
        if col == 3:
            self.choose_measurement_line_color(row)
        elif col == 4:
            self.choose_measurement_text_color(row)

    def _get_selected_measurement_rows(self) -> list[int]:
        """Return selected measurement rows in ascending order."""
        if not hasattr(self, 'measurement_table'):
            return []
        rows = self.measurement_table.selected_rows()
        return [row for row in rows if 0 <= row < len(self.overlay_renderer.measurements)]

    def choose_measurement_line_color(self, row_override: Optional[int] = None):
        """Choose measurement line color."""
        if row_override is not None:
            selected_rows = self._get_selected_measurement_rows()
            target_rows = selected_rows if row_override in selected_rows else [row_override]
        else:
            target_rows = self._get_selected_measurement_rows()

        initial = self.overlay_renderer.measurement_line_color
        if target_rows and 0 <= target_rows[0] < len(self.overlay_renderer.measurements):
            initial = QColor(self.overlay_renderer.measurements[target_rows[0]].get("line_color", initial))
        color = QColorDialog.getColor(
            initial, self, "Choose Measurement Line Color"
        )
        if color.isValid():
            if target_rows:
                for row in target_rows:
                    if 0 <= row < len(self.overlay_renderer.measurements):
                        self.overlay_renderer.measurements[row]["line_color"] = QColor(color)
                self._refresh_measurements_list()
                for row in target_rows:
                    if 0 <= row < self.measurement_table.rowCount():
                        self.measurement_table.selectRow(row)
                set_color_button_indicator(self.measurement_line_color_btn, color)
            else:
                self.overlay_renderer.measurement_line_color = color
                set_color_button_indicator(self.measurement_line_color_btn, self.overlay_renderer.measurement_line_color)
            self.update_display()

    def choose_measurement_text_color(self, row_override: Optional[int] = None):
        """Choose measurement label color."""
        if row_override is not None:
            selected_rows = self._get_selected_measurement_rows()
            target_rows = selected_rows if row_override in selected_rows else [row_override]
        else:
            target_rows = self._get_selected_measurement_rows()

        initial = self.overlay_renderer.measurement_text_color
        if target_rows and 0 <= target_rows[0] < len(self.overlay_renderer.measurements):
            initial = QColor(self.overlay_renderer.measurements[target_rows[0]].get("text_color", initial))
        color = QColorDialog.getColor(
            initial, self, "Choose Measurement Text Color"
        )
        if color.isValid():
            if target_rows:
                for row in target_rows:
                    if 0 <= row < len(self.overlay_renderer.measurements):
                        self.overlay_renderer.measurements[row]["text_color"] = QColor(color)
                self._refresh_measurements_list()
                for row in target_rows:
                    if 0 <= row < self.measurement_table.rowCount():
                        self.measurement_table.selectRow(row)
                set_color_button_indicator(self.measurement_text_color_btn, color)
            else:
                self.overlay_renderer.measurement_text_color = color
                set_color_button_indicator(self.measurement_text_color_btn, self.overlay_renderer.measurement_text_color)
            self.update_display()

    def apply_current_measurement_style_to_selected(self):
        """Apply currently selected style controls to selected measurements only."""
        selected_rows = self._get_selected_measurement_rows()
        if not selected_rows:
            self.measurement_status_label.setText("Select one or more measurements first.")
            return

        line_color = QColor(self.overlay_renderer.measurement_line_color)
        text_color = QColor(self.overlay_renderer.measurement_text_color)
        first_row = selected_rows[0]
        if 0 <= first_row < len(self.overlay_renderer.measurements):
            selected = self.overlay_renderer.measurements[first_row]
            line_color = QColor(selected.get("line_color", line_color))
            text_color = QColor(selected.get("text_color", text_color))

        show_label = self.measurement_label_checkbox.isChecked()
        line_width = self.measurement_thickness_spinbox.value()
        start_cap = self.measurement_start_end_combo.currentText()
        end_cap = self.measurement_end_end_combo.currentText()

        for row in selected_rows:
            if 0 <= row < len(self.overlay_renderer.measurements):
                m = self.overlay_renderer.measurements[row]
                m["show_label"] = bool(show_label)
                m["line_width"] = int(line_width)
                m["line_color"] = QColor(line_color)
                m["text_color"] = QColor(text_color)
                m["start_cap"] = start_cap
                m["end_cap"] = end_cap

        self._refresh_measurements_list()
        for row in selected_rows:
            if 0 <= row < self.measurement_table.rowCount():
                self.measurement_table.selectRow(row)
        self.update_display()

    def apply_current_measurement_style_to_all(self):
        """Apply currently selected style controls to all measurements."""
        if not self.overlay_renderer.measurements:
            return
        line_color = QColor(self.overlay_renderer.measurement_line_color)
        text_color = QColor(self.overlay_renderer.measurement_text_color)
        row = self.measurement_table.currentRow() if hasattr(self, 'measurement_table') else -1
        if 0 <= row < len(self.overlay_renderer.measurements):
            selected = self.overlay_renderer.measurements[row]
            line_color = QColor(selected.get("line_color", line_color))
            text_color = QColor(selected.get("text_color", text_color))

        show_label = self.measurement_label_checkbox.isChecked()
        line_width = self.measurement_thickness_spinbox.value()
        start_cap = self.measurement_start_end_combo.currentText()
        end_cap = self.measurement_end_end_combo.currentText()

        for m in self.overlay_renderer.measurements:
            m["show_label"] = bool(show_label)
            m["line_width"] = int(line_width)
            m["line_color"] = QColor(line_color)
            m["text_color"] = QColor(text_color)
            m["start_cap"] = start_cap
            m["end_cap"] = end_cap

        self._refresh_measurements_list()
        if self.overlay_renderer.measurements:
            self.measurement_table.selectRow(0 if row < 0 else min(row, len(self.overlay_renderer.measurements) - 1))
        self.update_display()

    # --- Draw-mode drag handlers ---

    def on_draw_mode_toggled(self, checked: bool):
        """Toggle drag-draw mode on the image label."""
        self._draw_mode_active = checked
        self._refresh_image_interaction_mode()
        if checked:
            # Untoggle all move modes
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
            self._line_drag_index = None
            self._scalebar_drag_origin_img = None
            # Ensure the annotation overlay is active when drawing starts
            if not self.measurement_checkbox.isChecked():
                self.measurement_checkbox.setChecked(True)
            self.measurement_status_label.setText(
                "Draw mode ON — click and drag on the image to add a measurement."
            )
        else:
            self._draw_preview_start = None
            self.overlay_renderer.measurement_preview = None
            self.measurement_status_label.setText("Draw mode off.")
            self.update_display()

    def on_label_drag_mode_toggled(self, checked: bool):
        """Toggle label-drag (move label) mode."""
        self._label_drag_active = checked
        self._refresh_image_interaction_mode()
        if checked:
            # Untoggle draw mode
            self.draw_measurement_btn.blockSignals(True)
            self.draw_measurement_btn.setChecked(False)
            self.draw_measurement_btn.blockSignals(False)
            self._draw_mode_active = False
            self.move_line_btn.blockSignals(True)
            self.move_line_btn.setChecked(False)
            self.move_line_btn.blockSignals(False)
            self._line_drag_active = False
            self.move_scalebar_btn.blockSignals(True)
            self.move_scalebar_btn.setChecked(False)
            self.move_scalebar_btn.blockSignals(False)
            self._scalebar_drag_active = False
            self.measurement_status_label.setText(
                "Move Label mode ON — click and drag any label to reposition it."
            )
        else:
            self._label_drag_index = None
            self._label_drag_origin_img = None
            self.measurement_status_label.setText("Move Label mode off.")

    def on_line_drag_mode_toggled(self, checked: bool):
        """Toggle line-drag mode (move full measurement lines)."""
        self._line_drag_active = checked
        self._refresh_image_interaction_mode()
        if checked:
            self.draw_measurement_btn.blockSignals(True)
            self.draw_measurement_btn.setChecked(False)
            self.draw_measurement_btn.blockSignals(False)
            self._draw_mode_active = False
            self.move_label_btn.blockSignals(True)
            self.move_label_btn.setChecked(False)
            self.move_label_btn.blockSignals(False)
            self._label_drag_active = False
            self.move_scalebar_btn.blockSignals(True)
            self.move_scalebar_btn.setChecked(False)
            self.move_scalebar_btn.blockSignals(False)
            self._scalebar_drag_active = False
            self.measurement_status_label.setText(
                "Move Line mode ON — click and drag a measurement line to reposition it."
            )
        else:
            self._line_drag_index = None
            self._line_drag_origin_img = None
            self.measurement_status_label.setText("Move Line mode off.")

    def on_scalebar_drag_mode_toggled(self, checked: bool):
        """Toggle drag mode for moving the full scalebar box."""
        self._scalebar_drag_active = checked
        self._refresh_image_interaction_mode()
        if checked:
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
            self.measurement_status_label.setText(
                "Move Scalebar mode ON — drag the scalebar box to reposition it."
            )
        else:
            self._scalebar_drag_origin_img = None
            self.measurement_status_label.setText("Move Scalebar mode off.")

    def _refresh_image_interaction_mode(self):
        """Sync image-label interaction cursor/mode with current active tool."""
        if self.is_crop_move_active():
            self.image_label.set_label_drag_mode(True)
            return
        if self.is_crop_draw_active():
            self.image_label.set_draw_mode(True)
            return
        if self._draw_mode_active:
            self.image_label.set_draw_mode(True)
            return
        if self._label_drag_active or self._line_drag_active or self._scalebar_drag_active:
            self.image_label.set_label_drag_mode(True)
            return
        self.image_label.set_draw_mode(False)

    def on_draw_press(self, x: int, y: int):
        """Mouse press — either start a new line or grab a label."""
        if not self.image_processor.has_image():
            return
        if self.crop_handle_mouse_press(x, y):
            return
        if self._scalebar_drag_active:
            self._start_scalebar_drag(x, y)
            return
        if self._line_drag_active:
            self._start_line_drag(x, y)
            return
        if self._label_drag_active:
            self._start_label_drag(x, y)
            return
        # draw-mode branch
        mapped = self._map_label_to_image_coords(x, y)
        if mapped is None:
            return
        self._draw_preview_start = mapped
        self.overlay_renderer.measurement_preview = {"start": mapped, "end": mapped}
        self.update_display()

    def on_draw_move(self, x: int, y: int):
        """Mouse move — update live preview or drag a label."""
        if self.crop_handle_mouse_move(x, y):
            return
        if self._scalebar_drag_active:
            self._update_scalebar_drag(x, y)
            return
        if self._line_drag_active:
            self._update_line_drag(x, y)
            return
        if self._label_drag_active:
            self._update_label_drag(x, y)
            return
        if self._draw_preview_start is None:
            return
        mapped = self._map_label_to_image_coords(x, y)
        if mapped is None:
            return
        self.overlay_renderer.measurement_preview = {
            "start": self._draw_preview_start, "end": mapped
        }
        self.update_display()

    def on_draw_release(self, x: int, y: int):
        """Mouse release — commit a new line or drop a dragged label."""
        if self.crop_handle_mouse_release(x, y):
            return
        if self._scalebar_drag_active:
            self._finish_scalebar_drag(x, y)
            return
        if self._line_drag_active:
            self._finish_line_drag(x, y)
            return
        if self._label_drag_active:
            self._finish_label_drag(x, y)
            return
        if self._draw_preview_start is None:
            return
        mapped = self._map_label_to_image_coords(x, y)
        if mapped is None:
            mapped = self._draw_preview_start
        start = self._draw_preview_start
        end = mapped
        self._draw_preview_start = None
        self.overlay_renderer.measurement_preview = None
        if np.hypot(float(end[0] - start[0]), float(end[1] - start[1])) > 3:
            self.overlay_renderer.measurements.append(
                {
                    "start": start,
                    "end": end,
                    "start_cap": "head",
                    "end_cap": "head",
                    "show_label": bool(self.overlay_renderer.measurement_show_label),
                    "line_color": QColor(self.overlay_renderer.measurement_line_color),
                    "text_color": QColor(self.overlay_renderer.measurement_text_color),
                    "line_width": int(self.overlay_renderer.measurement_line_width),
                }
            )
            self._refresh_measurements_list()
            self.measurement_table.selectRow(len(self.overlay_renderer.measurements) - 1)
        self.update_display()

    # --- Label-drag helpers ---

    def _start_scalebar_drag(self, label_x: int, label_y: int):
        """Start dragging the full scalebar box when the click hits its current bounds."""
        self._scalebar_drag_origin_img = None
        if not self.overlay_renderer.scalebar_enabled or self._last_rendered_image_size is None:
            return

        mapped = self._map_label_to_image_coords(label_x, label_y)
        if mapped is None:
            return
        img_x, img_y = float(mapped[0]), float(mapped[1])

        img_w, img_h = self._last_rendered_image_size
        rect = self.overlay_renderer.get_scalebar_box_rect(img_w, img_h, self.nm_per_pixel)
        if rect is None:
            return

        hit_pad = 8.0
        left, top, right, bottom = rect
        if not (left - hit_pad <= img_x <= right + hit_pad and top - hit_pad <= img_y <= bottom + hit_pad):
            self.measurement_status_label.setText("Click on the scalebar box to move it.")
            return

        self._scalebar_drag_origin_img = (img_x, img_y)
        self._scalebar_drag_offset_start = tuple(self.overlay_renderer.scalebar_offset)
        # Mark dropdown as custom when the user starts manual repositioning.
        if self.position_combo.currentText() != "custom":
            self.position_combo.blockSignals(True)
            self.position_combo.setCurrentText("custom")
            self.position_combo.blockSignals(False)

    def _update_scalebar_drag(self, label_x: int, label_y: int):
        """Update scalebar offset while dragging."""
        if self._scalebar_drag_origin_img is None:
            return
        mapped = self._map_label_to_image_coords(label_x, label_y)
        if mapped is None:
            return
        ddx = float(mapped[0]) - float(self._scalebar_drag_origin_img[0])
        ddy = float(mapped[1]) - float(self._scalebar_drag_origin_img[1])
        self.overlay_renderer.scalebar_offset = (
            float(self._scalebar_drag_offset_start[0]) + ddx,
            float(self._scalebar_drag_offset_start[1]) + ddy,
        )
        self.update_display()

    def _finish_scalebar_drag(self, label_x: int, label_y: int):
        """Commit final scalebar box position."""
        self._update_scalebar_drag(label_x, label_y)
        self._scalebar_drag_origin_img = None

    def _start_line_drag(self, label_x: int, label_y: int):
        """Find the nearest measurement line under cursor and start dragging it."""
        self._line_drag_index = None
        if not self.overlay_renderer.measurements:
            self.measurement_status_label.setText("No measurements available to move.")
            return

        mapped = self._map_label_to_image_coords(label_x, label_y)
        if mapped is None:
            return

        img_w, img_h, scale, offset_x, offset_y = self._get_display_mapping()
        if scale <= 0:
            return

        best_idx = None
        best_dist = 18.0
        px = float(label_x)
        py = float(label_y)
        for idx, m in enumerate(self.overlay_renderer.measurements):
            sx1 = float(m["start"][0]) * scale + offset_x
            sy1 = float(m["start"][1]) * scale + offset_y
            sx2 = float(m["end"][0]) * scale + offset_x
            sy2 = float(m["end"][1]) * scale + offset_y
            dist = self._point_to_segment_distance(px, py, sx1, sy1, sx2, sy2)
            if dist < best_dist:
                best_dist = dist
                best_idx = idx

        if best_idx is None:
            self.measurement_status_label.setText("No line found nearby. Click closer to a measurement line.")
            return

        self._line_drag_index = best_idx
        self._line_drag_origin_img = (float(mapped[0]), float(mapped[1]))
        m = self.overlay_renderer.measurements[best_idx]
        self._line_drag_start_start = (float(m["start"][0]), float(m["start"][1]))
        self._line_drag_start_end = (float(m["end"][0]), float(m["end"][1]))

    def _update_line_drag(self, label_x: int, label_y: int):
        """Update selected line position while preserving its shape and label offset."""
        if self._line_drag_index is None or self._line_drag_origin_img is None:
            return
        mapped = self._map_label_to_image_coords(label_x, label_y)
        if mapped is None or self._last_rendered_image_size is None:
            return

        ddx = float(mapped[0]) - float(self._line_drag_origin_img[0])
        ddy = float(mapped[1]) - float(self._line_drag_origin_img[1])

        x1 = self._line_drag_start_start[0] + ddx
        y1 = self._line_drag_start_start[1] + ddy
        x2 = self._line_drag_start_end[0] + ddx
        y2 = self._line_drag_start_end[1] + ddy

        img_w, img_h = self._last_rendered_image_size
        min_x = min(x1, x2)
        max_x = max(x1, x2)
        min_y = min(y1, y2)
        max_y = max(y1, y2)
        shift_x = 0.0
        shift_y = 0.0
        if min_x < 0:
            shift_x = -min_x
        elif max_x > (img_w - 1):
            shift_x = (img_w - 1) - max_x
        if min_y < 0:
            shift_y = -min_y
        elif max_y > (img_h - 1):
            shift_y = (img_h - 1) - max_y

        x1 += shift_x
        y1 += shift_y
        x2 += shift_x
        y2 += shift_y

        self.overlay_renderer.measurements[self._line_drag_index]["start"] = (int(round(x1)), int(round(y1)))
        self.overlay_renderer.measurements[self._line_drag_index]["end"] = (int(round(x2)), int(round(y2)))
        self._refresh_measurements_list()
        self.update_display()

    def _finish_line_drag(self, label_x: int, label_y: int):
        """Commit final measurement line position."""
        self._update_line_drag(label_x, label_y)
        self._line_drag_index = None
        self._line_drag_origin_img = None

    def _start_label_drag(self, label_x: int, label_y: int):
        """Find the nearest label under the cursor and start dragging it."""
        self._label_drag_index = None
        if not self.image_processor.has_image() or self._last_rendered_image_size is None:
            return
        _img_w, _img_h, scale, offset_x, offset_y = self._get_display_mapping()

        centres = self.overlay_renderer.get_label_centres()
        hit_radius_screen = 40.0   # pixels in screen space
        best_dist = hit_radius_screen
        best_idx = None
        for i, c in enumerate(centres):
            if c is None:
                continue
            # convert image coords -> screen coords
            sx = c[0] * scale + offset_x
            sy = c[1] * scale + offset_y
            dist = np.hypot(label_x - sx, label_y - sy)
            if dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx is None:
            self.measurement_status_label.setText(
                "No label found nearby. Click closer to a label."
            )
            return

        self._label_drag_index = best_idx
        mapped = self._map_label_to_image_coords(label_x, label_y)
        self._label_drag_origin_img = mapped if mapped is not None else (0.0, 0.0)
        m = self.overlay_renderer.measurements[best_idx]
        self._label_drag_offset_start = tuple(m.get("label_offset", (0.0, 0.0)))

    def _update_label_drag(self, label_x: int, label_y: int):
        """Update the dragged label's offset as the mouse moves."""
        if self._label_drag_index is None or self._label_drag_origin_img is None:
            return
        mapped = self._map_label_to_image_coords(label_x, label_y)
        if mapped is None:
            return
        ddx = float(mapped[0]) - float(self._label_drag_origin_img[0])
        ddy = float(mapped[1]) - float(self._label_drag_origin_img[1])
        new_offset = (
            float(self._label_drag_offset_start[0]) + ddx,
            float(self._label_drag_offset_start[1]) + ddy,
        )
        self.overlay_renderer.measurements[self._label_drag_index]["label_offset"] = new_offset
        self.update_display()

    def _finish_label_drag(self, label_x: int, label_y: int):
        """Commit the final label position."""
        self._update_label_drag(label_x, label_y)
        self._label_drag_index = None
        self._label_drag_origin_img = None

    @staticmethod
    def _point_to_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        """Return shortest distance from point P to segment AB in screen space."""
        vx = x2 - x1
        vy = y2 - y1
        wx = px - x1
        wy = py - y1
        vv = vx * vx + vy * vy
        if vv <= 1e-12:
            return float(np.hypot(px - x1, py - y1))
        t = (wx * vx + wy * vy) / vv
        t = max(0.0, min(1.0, t))
        proj_x = x1 + t * vx
        proj_y = y1 + t * vy
        return float(np.hypot(px - proj_x, py - proj_y))

    def _get_display_mapping(self) -> tuple[int, int, float, float, float]:
        """Return image/display mapping as (img_w, img_h, scale, offset_x, offset_y)."""
        img_w, img_h = self._last_rendered_image_size if self._last_rendered_image_size else (1, 1)
        display_w = max(1, self.image_label.width())
        display_h = max(1, self.image_label.height())
        scale = min(display_w / img_w, display_h / img_h)
        offset_x = (display_w - img_w * scale) / 2.0
        offset_y = (display_h - img_h * scale) / 2.0
        return img_w, img_h, scale, offset_x, offset_y

    def remove_selected_measurement(self):
        """Remove the selected measurement from the list."""
        rows = self._get_selected_measurement_rows()
        if not rows:
            return
        for row in sorted(rows, reverse=True):
            if 0 <= row < len(self.overlay_renderer.measurements):
                self.overlay_renderer.measurements.pop(row)
        self._refresh_measurements_list()
        if self.overlay_renderer.measurements:
            self.measurement_table.selectRow(min(rows[0], len(self.overlay_renderer.measurements) - 1))
        else:
            self._on_measurement_selection_changed(-1)
        self.update_display()

    def clear_all_measurements(self):
        """Clear all measurement annotations."""
        self.overlay_renderer.measurements.clear()
        self.overlay_renderer.measurement_preview = None
        self._draw_preview_start = None
        self.measurement_table.setRowCount(0)
        self._on_measurement_selection_changed(-1)
        self.measurement_status_label.setText("All measurements cleared.")
        self.update_display()

    def _refresh_measurements_list(self):
        """Repopulate the sidebar table with current measurements and properties."""
        if not hasattr(self, 'measurement_table'):
            return
        self.measurement_table.setRowCount(0)
        unit = self.overlay_renderer.measurement_unit
        for i, m in enumerate(self.overlay_renderer.measurements):
            if "start_cap" not in m:
                m["start_cap"] = "head"
            if "end_cap" not in m:
                m["end_cap"] = "head"
            if m["start_cap"] in {"arrow", "block"}:
                m["start_cap"] = "head"
            if m["end_cap"] in {"arrow", "block"}:
                m["end_cap"] = "head"
            if "show_label" not in m:
                m["show_label"] = bool(self.overlay_renderer.measurement_show_label)
            if "line_color" not in m:
                m["line_color"] = QColor(self.overlay_renderer.measurement_line_color)
            if "text_color" not in m:
                m["text_color"] = QColor(self.overlay_renderer.measurement_text_color)
            if "line_width" not in m:
                m["line_width"] = int(self.overlay_renderer.measurement_line_width)
            dx = float(m["end"][0] - m["start"][0])
            dy = float(m["end"][1] - m["start"][1])
            length_nm = float(np.hypot(dx, dy)) * float(self.nm_per_pixel)
            value = length_nm / 1000.0 if unit == "µm" else length_nm
            length_text = f"{value:.1f} {unit}"
            line_color = QColor(m["line_color"])
            text_color = QColor(m["text_color"])

            row = self.measurement_table.rowCount()
            self.measurement_table.insertRow(row)
            values = [
                str(i + 1),
                length_text,
                "Yes" if bool(m.get("show_label", True)) else "No",
                "",
                "",
                str(int(m.get("line_width", self.overlay_renderer.measurement_line_width))),
                str(m.get("start_cap", "head")),
                str(m.get("end_cap", "head")),
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col in (3, 4):
                    swatch_color = line_color if col == 3 else text_color
                    item.setBackground(QBrush(swatch_color))
                    item.setToolTip(f"Click to change color ({swatch_color.name().upper()})")
                self.measurement_table.setItem(row, col, item)

        self.measurement_table.resizeColumnsToContents()

    def _has_any_visible_measurement_labels(self) -> bool:
        """Return True if at least one measurement currently has a visible label."""
        if not self.overlay_renderer.measurements:
            return False
        for m in self.overlay_renderer.measurements:
            if bool(m.get("show_label", self.overlay_renderer.measurement_show_label)):
                return True
        return False

    def _map_label_to_image_coords(self, label_x: int, label_y: int) -> Optional[tuple[int, int]]:
        """Map click coordinates from QLabel space to source image pixel coordinates."""
        if self._last_rendered_image_size is None:
            return None

        img_w, img_h = self._last_rendered_image_size
        if img_w <= 0 or img_h <= 0:
            return None

        display_w = max(1, self.image_label.width())
        display_h = max(1, self.image_label.height())

        scale = min(display_w / img_w, display_h / img_h)
        scaled_w = img_w * scale
        scaled_h = img_h * scale
        offset_x = (display_w - scaled_w) / 2.0
        offset_y = (display_h - scaled_h) / 2.0

        if label_x < offset_x or label_y < offset_y:
            return None
        if label_x > offset_x + scaled_w or label_y > offset_y + scaled_h:
            return None

        img_x = int(round((label_x - offset_x) / scale))
        img_y = int(round((label_y - offset_y) / scale))
        img_x = max(0, min(img_w - 1, img_x))
        img_y = max(0, min(img_h - 1, img_y))
        return (img_x, img_y)

    def _update_measurement_info_label(self):
        """Refresh the measurement list (kept for compatibility with existing call sites)."""
        self._refresh_measurements_list()
    
    def update_display(self):
        """Update the displayed image."""
        if not self.image_processor.has_image():
            return
        
        # Get current image with overlays
        q_image = self.overlay_renderer.render_image_with_overlays(
            self.image_processor.get_current_image(),
            self.nm_per_pixel
        )
        
        if q_image is None:
            return

        self.draw_manual_crop_overlay(q_image)

        self._last_rendered_image_size = (q_image.width(), q_image.height())
        
        pixmap = QPixmap.fromImage(q_image)
        scaled_pixmap = pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)
    
    def export_image(self):
        """Export the current image."""
        if not self.image_processor.has_image():
            QMessageBox.warning(self, "Warning", "No image loaded to export.")
            return
        
        suggested_name = Path(self.current_file).stem + "_processed.png" if self.current_file else "tem_image.png"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Image", suggested_name,
            "PNG Image (*.png);;TIFF Image (*.tif *.tiff);;JPEG Image (*.jpg *.jpeg);;All Files (*.*)"
        )
        
        if file_path:
            try:
                q_image = self.overlay_renderer.render_image_with_overlays(
                    self.image_processor.get_current_image(),
                    self.nm_per_pixel
                )
                
                if q_image is None:
                    QMessageBox.warning(self, "Warning", "No image to export.")
                    return
                
                # Convert to RGBA8888
                q_rgba = q_image.convertToFormat(QImage.Format.Format_RGBA8888)
                width = q_rgba.width()
                height = q_rgba.height()
                ptr = q_rgba.bits()
                ptr.setsize(height * width * 4)
                arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))
                export_rgba = arr.copy()
                
                # Determine DPI
                input_dpi = self.image_processor.get_dpi()
                if input_dpi and all(v > 0 for v in input_dpi):
                    xdpi = min(input_dpi[0], 300.0)
                    ydpi = min(input_dpi[1], 300.0)
                else:
                    xdpi = ydpi = 300.0
                
                # Save
                ext = Path(file_path).suffix.lower()
                if ext in [".jpg", ".jpeg", ".bmp"]:
                    export_rgb = export_rgba[:, :, :3]
                    pil_image = Image.fromarray(export_rgb, mode='RGB')
                    pil_image.save(file_path, dpi=(xdpi, ydpi))
                else:
                    pil_image = Image.fromarray(export_rgba, mode='RGBA')
                    pil_image.save(file_path, dpi=(xdpi, ydpi))
                
                QMessageBox.information(self, "Success", f"Image exported successfully to:\n{file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export image:\n{str(e)}")
    
    def manage_presets(self):
        """Open preset manager dialog."""
        dialog = PresetManager(self.presets, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.presets = dialog.get_presets()
            PresetStorage.save_presets(self.presets)
            self._update_preset_combo()
    
    def _update_preset_combo(self):
        """Update preset combo box."""
        if "Custom" not in self.presets:
            self.presets["Custom"] = 1.0
        current = self.preset_combo.currentText() if self.preset_combo.count() > 0 else None
        self.preset_combo.clear()
        self.preset_combo.addItems(sorted(self.presets.keys()))
        if current and current in self.presets:
            self.preset_combo.setCurrentText(current)
        if hasattr(self, "pixel_size_spinbox") and hasattr(self, "pixel_size_unit_combo"):
            self._update_pixel_size_editable_state(self.preset_combo.currentText())

    def _update_pixel_size_editable_state(self, preset_name: str):
        """Allow editing pixel-size fields only for the Custom preset."""
        editable = (preset_name == "Custom")
        self.pixel_size_spinbox.setEnabled(editable)
        self.pixel_size_unit_combo.setEnabled(editable)
    
    def _apply_initial_scalebar_defaults(self):
        """Apply initial scalebar defaults for the default preset."""
        current_preset = self.preset_combo.currentText()
        if current_preset == "Standard":
            self.unit_combo.setCurrentText("µm")
            self.scalebar_length_spinbox.setValue(5)
        elif current_preset == "High Res":
            self.unit_combo.setCurrentText("nm")
            self.scalebar_length_spinbox.setValue(500)
    
    def resizeEvent(self, event):
        """Handle window resize."""
        super().resizeEvent(event)
        if self.image_processor.has_image():
            QTimer.singleShot(100, self.update_display)
    
    def batch_annotate(self):
        """Open batch annotation dialog."""
        dialog = BatchProcessingDialog(self.presets, self.overlay_renderer, self)
        dialog.exec()


def main():
    """Main entry point."""
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.debug=false;qt.qpa.fonts.warning=false")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = TEMImageEditor()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
