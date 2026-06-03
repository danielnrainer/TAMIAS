"""
TAMIAS - Main GUI application.
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
from PyQt6.QtCore import Qt, QTimer, QSize, QUrl
from PyQt6.QtGui import QPixmap, QImage, QAction, QActionGroup, QColor, QFont, QPalette, QBrush, QIcon, QDesktopServices
from PyQt6.QtWidgets import QColorDialog, QFontDialog

# Import our modules
from core.image_processor import ImageProcessor
from core.overlay_renderer import OverlayRenderer
from core.crop_geometry import compute_display_mapping, map_label_to_image_coords, point_to_segment_distance
from utils.preset_manager import PresetManager, PresetStorage
from utils.app_settings_manager import AppSettingsStorage
from utils.imaging_mode_defaults import get_mode_overlay_defaults
from utils.storage_paths import ensure_app_storage_dir
from gui.custom_widgets import (
    ClickClearTableWidget,
    ImageDisplayLabel,
    SmartDoubleSpinBox,
    set_color_button_indicator,
)
from gui.theme_manager import ThemeManager
from gui.app_state_manager import AppStateManager
from gui.measurement_interaction import MeasurementInteractionController
from gui import ui_sections
from gui.collapsible_box import QCollapsibleBox
from gui.crop_controller import CropControllerMixin
from gui.batch_processing_dialog import BatchProcessingDialog


def get_resource_path(relative_path: str) -> Path:
    """Resolve paths for both source runs and PyInstaller bundles."""
    if getattr(sys, "frozen", False):
        base_path = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base_path = Path(__file__).resolve().parent
    return base_path / relative_path


class TEMImageEditor(CropControllerMixin, QMainWindow):
    """Main application window for TEM image editing."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TAMIAS")
        self.setGeometry(100, 100, 1100, 700)

        self._app_settings = AppSettingsStorage.load_settings()
        self._theme_manager = ThemeManager()
        self._app_state_manager = AppStateManager()
        self._measurement_interaction = MeasurementInteractionController(self)
        
        # Initialize modules
        self.image_processor = ImageProcessor()
        self.overlay_renderer = OverlayRenderer()
        self._apply_overlay_settings(self._app_settings.get("overlay", {}))
        
        # Current file and calibration
        self.current_file: Optional[str] = None
        self.nm_per_pixel = 1.0
        self.pixel_size_unit = "nm"
        self.single_io_directory = str(self._app_settings.get("single_io_directory", ""))
        self.batch_input_directory = str(self._app_settings.get("batch_input_directory", ""))
        self.batch_output_directory = str(self._app_settings.get("batch_output_directory", ""))

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
        default_payload = PresetStorage.get_default_payload()
        default_custom_value = float(default_payload.get("pixel_size_presets", {}).get("Custom", 1.0))
        self.presets = PresetStorage.load_presets()
        if "Custom" not in self.presets:
            self.presets["Custom"] = default_custom_value
        crop_defaults = PresetStorage.load_crop_defaults()
        shipped_crop_defaults = dict(default_payload.get("crop_defaults", {}))
        self._default_crop_top_rows = int(crop_defaults.get("top_rows", shipped_crop_defaults.get("top_rows", 0)))
        self._default_crop_bottom_rows = int(crop_defaults.get("bottom_rows", shipped_crop_defaults.get("bottom_rows", 0)))
        self._session_preset_baseline = PresetStorage.normalize_payload(PresetStorage.load_preset_payload())
        
        # Setup UI
        self.setup_ui()
        self.setup_menu()

        if hasattr(self, "crop_top_spinbox"):
            self.crop_top_spinbox.setValue(max(0, self._default_crop_top_rows))
            self.crop_top_spinbox.valueChanged.connect(self._on_crop_defaults_changed)
        if hasattr(self, "crop_bottom_spinbox"):
            self.crop_bottom_spinbox.setValue(max(0, self._default_crop_bottom_rows))
            self.crop_bottom_spinbox.valueChanged.connect(self._on_crop_defaults_changed)

        self._apply_overlay_settings_to_controls()
        self._restore_window_state_from_settings()

        # Theme mode: auto follows the OS color scheme.
        saved_theme = str(self._app_settings.get("theme_mode", "auto"))
        self._theme_mode = saved_theme if saved_theme in {"auto", "light", "dark"} else "auto"
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
        
        # Settings menu
        settings_menu = menubar.addMenu("Settings")

        manage_presets_action = QAction("Manage Presets...", self)
        manage_presets_action.triggered.connect(self.manage_presets)
        settings_menu.addAction(manage_presets_action)

        import_presets_action = QAction("Load Presets from File...", self)
        import_presets_action.triggered.connect(self.load_presets_from_file)
        settings_menu.addAction(import_presets_action)

        export_presets_action = QAction("Save Presets to File...", self)
        export_presets_action.triggered.connect(self.save_presets_to_file)
        settings_menu.addAction(export_presets_action)

        settings_menu.addSeparator()

        restore_default_presets_action = QAction("Restore Presets to TAMIAS Defaults", self)
        restore_default_presets_action.triggered.connect(self.restore_default_presets)
        settings_menu.addAction(restore_default_presets_action)

        restore_default_app_settings_action = QAction("Restore App Settings to TAMIAS Defaults", self)
        restore_default_app_settings_action.triggered.connect(self.restore_default_app_settings)
        settings_menu.addAction(restore_default_app_settings_action)

        settings_menu.addSeparator()

        theme_menu = settings_menu.addMenu("Select Theme")
        open_settings_folder_action = QAction("Open Settings Folder", self)
        open_settings_folder_action.triggered.connect(self.open_settings_folder)
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

        settings_menu.addSeparator()
        settings_menu.addAction(open_settings_folder_action)

        # Help menu
        help_menu = menubar.addMenu("Help")
        about_action = QAction("About / Citation", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def _on_theme_action_triggered(self, mode: str, checked: bool):
        if checked:
            self._apply_theme_mode(mode)

    def open_settings_folder(self):
        """Open the persisted settings folder in the OS file browser."""
        settings_dir = ensure_app_storage_dir()
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(settings_dir)))
        if not ok:
            QMessageBox.warning(self, "Settings", f"Could not open settings folder:\n{settings_dir}")

    def load_presets_from_file(self):
        """Import preset definitions from an external JSON file."""
        start_dir = self.single_io_directory or str(ensure_app_storage_dir())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Presets from JSON",
            start_dir,
            "JSON Files (*.json);;All Files (*.*)",
        )
        if not file_path:
            return

        try:
            payload = PresetStorage.load_preset_payload_from_file(Path(file_path))
        except Exception as e:
            QMessageBox.critical(self, "Preset Import", f"Failed to import presets:\n{e}")
            return

        default_payload = PresetStorage.get_default_payload()
        default_custom_value = float(default_payload.get("pixel_size_presets", {}).get("Custom", 1.0))
        imported_presets = dict(payload.get("pixel_size_presets", {}))
        if "Custom" not in imported_presets:
            imported_presets["Custom"] = default_custom_value
        self.presets = imported_presets
        self._update_preset_combo()

        crop_defaults = dict(payload.get("crop_defaults", {}))
        shipped_crop_defaults = dict(default_payload.get("crop_defaults", {}))
        if hasattr(self, "crop_top_spinbox") and hasattr(self, "crop_bottom_spinbox"):
            self.crop_top_spinbox.setValue(max(0, int(crop_defaults.get("top_rows", shipped_crop_defaults.get("top_rows", 0)))))
            self.crop_bottom_spinbox.setValue(max(0, int(crop_defaults.get("bottom_rows", shipped_crop_defaults.get("bottom_rows", 0)))))

        self.single_io_directory = str(Path(file_path).parent)
        QMessageBox.information(
            self,
            "Preset Import",
            f"Imported {len(imported_presets)} presets from:\n{file_path}",
        )

    def save_presets_to_file(self):
        """Export current presets and crop defaults to an external JSON file."""
        start_dir = str(ensure_app_storage_dir())
        suggested_file = str(Path(start_dir) / "tamias_presets.json")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Presets to JSON",
            suggested_file,
            "JSON Files (*.json);;All Files (*.*)",
        )
        if not file_path:
            return

        payload = PresetStorage.load_preset_payload()
        payload["pixel_size_presets"] = dict(self.presets)
        if hasattr(self, "crop_top_spinbox") and hasattr(self, "crop_bottom_spinbox"):
            payload["crop_defaults"] = {
                "top_rows": max(0, int(self.crop_top_spinbox.value())),
                "bottom_rows": max(0, int(self.crop_bottom_spinbox.value())),
            }

        try:
            PresetStorage.save_preset_payload_to_file(payload, Path(file_path))
        except Exception as e:
            QMessageBox.critical(self, "Preset Export", f"Failed to save presets:\n{e}")
            return

        self.single_io_directory = str(Path(file_path).parent)
        QMessageBox.information(self, "Preset Export", f"Saved presets to:\n{file_path}")

    def restore_default_presets(self):
        """Restore shipped default imaging presets and crop defaults."""
        answer = QMessageBox.question(
            self,
            "Restore Presets",
            "Restore shipped TAMIAS default presets and crop defaults?\n\n"
            "This will overwrite your current preset defaults.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        payload = PresetStorage.get_default_payload()
        default_payload = PresetStorage.get_default_payload()
        default_custom_value = float(default_payload.get("pixel_size_presets", {}).get("Custom", 1.0))
        self.presets = dict(payload.get("pixel_size_presets", {}))
        if "Custom" not in self.presets:
            self.presets["Custom"] = default_custom_value
        self._update_preset_combo()

        crop_defaults = dict(payload.get("crop_defaults", {}))
        shipped_crop_defaults = dict(default_payload.get("crop_defaults", {}))
        self._default_crop_top_rows = int(crop_defaults.get("top_rows", shipped_crop_defaults.get("top_rows", 0)))
        self._default_crop_bottom_rows = int(crop_defaults.get("bottom_rows", shipped_crop_defaults.get("bottom_rows", 0)))
        if hasattr(self, "crop_top_spinbox") and hasattr(self, "crop_bottom_spinbox"):
            self.crop_top_spinbox.setValue(max(0, self._default_crop_top_rows))
            self.crop_bottom_spinbox.setValue(max(0, self._default_crop_bottom_rows))

        if hasattr(self, "preset_combo"):
            self.on_preset_changed(self.preset_combo.currentText())

        QMessageBox.information(self, "Restore Presets", "Shipped TAMIAS preset defaults were restored.")

    def restore_default_app_settings(self):
        """Restore shipped default app settings and apply them immediately."""
        answer = QMessageBox.question(
            self,
            "Restore App Settings",
            "Restore shipped TAMIAS app settings defaults?\n\n"
            "This will overwrite persisted theme, window layout, directories, and overlay defaults.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._app_settings = AppSettingsStorage.reset_to_defaults()
        self.single_io_directory = str(self._app_settings.get("single_io_directory", ""))
        self.batch_input_directory = str(self._app_settings.get("batch_input_directory", ""))
        self.batch_output_directory = str(self._app_settings.get("batch_output_directory", ""))

        self._apply_overlay_settings(self._app_settings.get("overlay", {}))
        self._apply_overlay_settings_to_controls()

        saved_theme = str(self._app_settings.get("theme_mode", "auto"))
        self._theme_mode = saved_theme if saved_theme in {"auto", "light", "dark"} else "auto"
        self._apply_theme_mode(self._theme_mode)

        self._restore_window_state_from_settings()
        if self.image_processor.has_image():
            self.update_display()

        QMessageBox.information(self, "Restore App Settings", "Shipped TAMIAS app settings were restored.")

    def show_about_dialog(self):
        """Show app information and citation links in a compact custom dialog."""
        github_url = "https://github.com/danielnrainer/TAMIAS"
        zenodo_url = "https://doi.org/10.5281/zenodo.20403971"

        dialog = QDialog(self)
        dialog.setWindowTitle("About TAMIAS")
        dialog.setModal(True)
        dialog.resize(550, 200)

        root_layout = QHBoxLayout(dialog)

        left_panel = QVBoxLayout()
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setFixedWidth(120)

        icon = QIcon(str(get_resource_path("tamias.png")))
        if icon.isNull():
            icon = QIcon(str(get_resource_path("tamias.ico")))

        logo_pixmap = icon.pixmap(96, 96)
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap)
        else:
            logo_label.setText("TAMIAS")
            logo_label.setStyleSheet("font-weight: bold; font-size: 16pt")

        left_panel.addWidget(logo_label)
        left_panel.addStretch()

        right_panel = QVBoxLayout()

        title_label = QLabel("<b>TAMIAS</b>")
        subtitle_label = QLabel("Tool for Annotation and Markup of Images from a Synergy-ED")
        subtitle_label.setWordWrap(True)

        github_label = QLabel(f"GitHub: <a href='{github_url}'>{github_url}</a>")
        github_label.setOpenExternalLinks(True)
        github_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

        zenodo_label = QLabel(f"Citation (Zenodo DOI): <a href='{zenodo_url}'>{zenodo_url}</a>")
        zenodo_label.setOpenExternalLinks(True)
        zenodo_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

        note_label = QLabel("Please cite TAMIAS via the Zenodo DOI when relevant.")

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        close_row.addWidget(close_btn)

        right_panel.addWidget(title_label)
        right_panel.addWidget(subtitle_label)
        right_panel.addSpacing(6)
        right_panel.addWidget(github_label)
        right_panel.addWidget(zenodo_label)
        right_panel.addSpacing(8)
        right_panel.addWidget(note_label)
        right_panel.addStretch()
        right_panel.addLayout(close_row)

        root_layout.addLayout(left_panel)
        root_layout.addLayout(right_panel, 1)

        dialog.exec()

    def _sync_theme_action_checks(self):
        self._theme_manager.sync_action_checks(getattr(self, "theme_actions", None))
        self._theme_mode = self._theme_manager.mode

    def _is_system_dark_mode(self) -> bool:
        return self._theme_manager.is_system_dark_mode()

    def _create_dark_palette(self) -> QPalette:
        return self._theme_manager.create_dark_palette()

    def _apply_theme_mode(self, mode: str):
        self._theme_manager.apply_theme_mode(mode, getattr(self, "theme_actions", None))
        self._theme_mode = self._theme_manager.mode

    def _on_system_color_scheme_changed(self, _scheme):
        self._theme_manager.on_system_color_scheme_changed(_scheme, getattr(self, "theme_actions", None))
        self._theme_mode = self._theme_manager.mode

    def _apply_overlay_settings(self, settings: dict):
        self._app_state_manager.apply_overlay_settings(self, settings)

    def _apply_overlay_settings_to_controls(self):
        self._app_state_manager.apply_overlay_settings_to_controls(self)

    def _restore_window_state_from_settings(self):
        self._app_state_manager.restore_window_state_from_settings(self)

    def _on_crop_defaults_changed(self, _value=None):
        """Update in-session top/bottom crop defaults."""
        if not hasattr(self, "crop_top_spinbox") or not hasattr(self, "crop_bottom_spinbox"):
            return

    def _current_session_preset_payload(self) -> dict:
        """Build the preset payload represented by the current UI session."""
        crop_top = int(self.crop_top_spinbox.value()) if hasattr(self, "crop_top_spinbox") else 0
        crop_bottom = int(self.crop_bottom_spinbox.value()) if hasattr(self, "crop_bottom_spinbox") else 0
        return PresetStorage.normalize_payload(
            {
                "pixel_size_presets": dict(self.presets),
                "crop_defaults": {
                    "top_rows": crop_top,
                    "bottom_rows": crop_bottom,
                },
            }
        )

    def _session_presets_dirty(self) -> bool:
        return self._current_session_preset_payload() != self._session_preset_baseline

    def _confirm_exit_with_preset_changes(self) -> QMessageBox.StandardButton:
        """Prompt when unsaved session preset changes would be persisted on exit."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Unsaved Preset Changes")
        box.setText(
            "Your preset values have changed and will be saved (overwrites the existing presets.json) on exiting TAMIAS."
        )
        box.setInformativeText("Do you want to continue with these new preset values?")
        yes_button = box.addButton("Yes (Save and exit)", QMessageBox.ButtonRole.YesRole)
        no_button = box.addButton("No (Discard and exit)", QMessageBox.ButtonRole.NoRole)
        cancel_button = box.addButton("Cancel (Return to TAMIAS)", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(yes_button)
        box.exec()

        clicked = box.clickedButton()
        if clicked == yes_button:
            return QMessageBox.StandardButton.Yes
        if clicked == no_button:
            return QMessageBox.StandardButton.No
        if clicked == cancel_button:
            return QMessageBox.StandardButton.Cancel
        return QMessageBox.StandardButton.Cancel

    def _collect_app_settings(self) -> dict:
        return self._app_state_manager.collect_app_settings(self)

    def _persist_user_state(self):
        self._app_state_manager.persist_user_state(self, persist_presets=False)

    def closeEvent(self, event):
        """Persist user settings and handle preset-save confirmation when needed."""
        save_presets = False
        if self._session_presets_dirty():
            answer = self._confirm_exit_with_preset_changes()
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Yes:
                save_presets = True

        self._persist_user_state()
        if save_presets:
            PresetStorage.save_preset_payload(self._current_session_preset_payload())
        super().closeEvent(event)
        
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
        self.file_info_label.setStyleSheet("QLabel { font-style: italic; padding: 5px; }")
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
        ui_sections.setup_preset_controls(self, parent_layout)
        
    def _setup_brightness_contrast_controls(self, parent_layout):
        """Setup brightness/contrast controls."""
        ui_sections.setup_brightness_contrast_controls(self, parent_layout)

    def _setup_transform_controls(self, parent_layout):
        """Setup image transform controls."""
        ui_sections.setup_transform_controls(self, parent_layout)
        
    def _setup_scalebar_controls(self, parent_layout):
        """Setup scalebar controls."""
        ui_sections.setup_scalebar_controls(self, parent_layout)
        
    def _setup_aperture_controls(self, parent_layout):
        """Setup aperture overlay controls."""
        ui_sections.setup_aperture_controls(self, parent_layout)

    def _setup_measurement_controls(self, parent_layout):
        """Setup particle measurement controls."""
        ui_sections.setup_measurement_controls(self, parent_layout)
        
    # Event handlers
    def load_image(self):
        """Load an image file."""
        start_dir = self.single_io_directory
        if not start_dir and self.current_file:
            try:
                start_dir = str(Path(self.current_file).parent)
            except Exception:
                start_dir = ""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", start_dir,
            "Image Files (*.rodhypix *.tif *.tiff *.png *.jpg *.jpeg *.bmp);;RODHyPix Files (*.rodhypix);;TIFF Files (*.tif *.tiff);;All Files (*.*)"
        )
        
        if file_path:
            self.single_io_directory = str(Path(file_path).parent)
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
            
            defaults = get_mode_overlay_defaults(preset_name)
            mode_unit = defaults["unit"] if defaults is not None else None

            # Set preset-specific scalebar defaults (only if UI is fully initialized)
            if defaults is not None and hasattr(self, 'unit_combo') and hasattr(self, 'scalebar_length_spinbox'):
                if self.unit_combo.currentText() != defaults["unit"]:
                    self.unit_combo.setCurrentText(defaults["unit"])
                self.scalebar_length_spinbox.setValue(defaults["scalebar_length_value"])
                self.scalebar_length_text_raw = defaults["scalebar_length_text"]

            if mode_unit is not None and hasattr(self, 'measurement_unit_combo') and self.measurement_unit_combo.currentText() != mode_unit:
                self.measurement_unit_combo.setCurrentText(mode_unit)

            self._refresh_scale_information()

    def _get_mode_dependent_unit(self, preset_name: str) -> str | None:
        """Return the measurement/scalebar unit associated with the active image mode."""
        defaults = get_mode_overlay_defaults(preset_name)
        if defaults is not None:
            return defaults["unit"]
        return None

    def _get_mode_dependent_scalebar_defaults(self, preset_name: str) -> dict | None:
        """Compatibility wrapper around shared imaging-mode overlay defaults."""
        return get_mode_overlay_defaults(preset_name)

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
        # Keep the raw label text synchronized even when value changes come from
        # spinbox stepping, wheel, or programmatic setValue calls.
        raw_text = ""
        try:
            raw_text = self.scalebar_length_spinbox.lineEdit().text().strip()
        except Exception:
            raw_text = ""
        if not raw_text:
            try:
                raw_text = self.scalebar_length_spinbox.cleanText().strip()
            except Exception:
                raw_text = ""
        if raw_text:
            self.scalebar_length_text_raw = raw_text
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
        """Keep cap-style controls available like other global measurement style controls."""
        self.measurement_start_end_combo.setEnabled(True)
        self.measurement_end_end_combo.setEnabled(True)

    def _on_measurement_selection_changed(self, row: int):
        """Load selected measurement cap styles into the end-style controls."""
        if row < 0 or row >= len(self.overlay_renderer.measurements):
            self.measurement_label_checkbox.blockSignals(True)
            self.measurement_label_checkbox.setChecked(self.overlay_renderer.measurement_show_label)
            self.measurement_label_checkbox.blockSignals(False)
            self.measurement_start_end_combo.blockSignals(True)
            self.measurement_end_end_combo.blockSignals(True)
            self.measurement_start_end_combo.setCurrentText(self.overlay_renderer.measurement_start_cap)
            self.measurement_end_end_combo.setCurrentText(self.overlay_renderer.measurement_end_cap)
            self.measurement_start_end_combo.blockSignals(False)
            self.measurement_end_end_combo.blockSignals(False)
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
        self.overlay_renderer.measurement_start_cap = self.measurement_start_end_combo.currentText()
        self.overlay_renderer.measurement_end_cap = self.measurement_end_end_combo.currentText()
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
            target_rows = selected_rows if selected_rows and row_override in selected_rows else []
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
            target_rows = selected_rows if selected_rows and row_override in selected_rows else []
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

    def _on_measurement_section_toggled(self, expanded: bool):
        """Turn off measurement interaction modes when the section is collapsed."""
        if expanded:
            return
        if self.draw_measurement_btn.isChecked():
            self.draw_measurement_btn.setChecked(False)
        if self.move_label_btn.isChecked():
            self.move_label_btn.setChecked(False)
        if self.move_line_btn.isChecked():
            self.move_line_btn.setChecked(False)

    def _on_scalebar_section_toggled(self, expanded: bool):
        """Turn off scalebar move mode when the section is collapsed."""
        if expanded:
            return
        if self.move_scalebar_btn.isChecked():
            self.move_scalebar_btn.setChecked(False)

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
        self._measurement_interaction.on_draw_press(x, y)

    def on_draw_move(self, x: int, y: int):
        """Mouse move — update live preview or drag a label."""
        self._measurement_interaction.on_draw_move(x, y)

    def on_draw_release(self, x: int, y: int):
        """Mouse release — commit a new line or drop a dragged label."""
        self._measurement_interaction.on_draw_release(x, y)

    # --- Label-drag helpers ---

    def _start_scalebar_drag(self, label_x: int, label_y: int):
        """Start dragging the full scalebar box when the click hits its current bounds."""
        self._measurement_interaction.start_scalebar_drag(label_x, label_y)

    def _update_scalebar_drag(self, label_x: int, label_y: int):
        """Update scalebar offset while dragging."""
        self._measurement_interaction.update_scalebar_drag(label_x, label_y)

    def _finish_scalebar_drag(self, label_x: int, label_y: int):
        """Commit final scalebar box position."""
        self._measurement_interaction.finish_scalebar_drag(label_x, label_y)

    def _start_line_drag(self, label_x: int, label_y: int):
        """Find the nearest measurement line under cursor and start dragging it."""
        self._measurement_interaction.start_line_drag(label_x, label_y)

    def _update_line_drag(self, label_x: int, label_y: int):
        """Update selected line position while preserving its shape and label offset."""
        self._measurement_interaction.update_line_drag(label_x, label_y)

    def _finish_line_drag(self, label_x: int, label_y: int):
        """Commit final measurement line position."""
        self._measurement_interaction.finish_line_drag(label_x, label_y)

    def _start_label_drag(self, label_x: int, label_y: int):
        """Find the nearest label under the cursor and start dragging it."""
        self._measurement_interaction.start_label_drag(label_x, label_y)

    def _update_label_drag(self, label_x: int, label_y: int):
        """Update the dragged label's offset as the mouse moves."""
        self._measurement_interaction.update_label_drag(label_x, label_y)

    def _finish_label_drag(self, label_x: int, label_y: int):
        """Commit the final label position."""
        self._measurement_interaction.finish_label_drag(label_x, label_y)

    @staticmethod
    def _point_to_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        """Return shortest distance from point P to segment AB in screen space."""
        return point_to_segment_distance(px, py, x1, y1, x2, y2)

    def _get_display_mapping(self) -> tuple[int, int, float, float, float]:
        """Return image/display mapping as (img_w, img_h, scale, offset_x, offset_y)."""
        img_w, img_h = self._last_rendered_image_size if self._last_rendered_image_size else (1, 1)
        display_w = max(1, self.image_label.width())
        display_h = max(1, self.image_label.height())
        return compute_display_mapping(img_w, img_h, display_w, display_h)

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
        display_w = max(1, self.image_label.width())
        display_h = max(1, self.image_label.height())
        mapped = map_label_to_image_coords(label_x, label_y, img_w, img_h, display_w, display_h)
        return mapped

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
        if self.single_io_directory:
            initial_path = str(Path(self.single_io_directory) / suggested_name)
        elif self.current_file:
            initial_path = str(Path(self.current_file).with_name(suggested_name))
        else:
            initial_path = suggested_name
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Image", initial_path,
            "PNG Image (*.png);;TIFF Image (*.tif *.tiff);;JPEG Image (*.jpg *.jpeg);;All Files (*.*)"
        )
        
        if file_path:
            self.single_io_directory = str(Path(file_path).parent)
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
        crop_defaults = {
            "top_rows": int(self.crop_top_spinbox.value()) if hasattr(self, "crop_top_spinbox") else 0,
            "bottom_rows": int(self.crop_bottom_spinbox.value()) if hasattr(self, "crop_bottom_spinbox") else 0,
        }
        dialog = PresetManager(
            self.presets,
            self,
            preset_file=PresetStorage.get_preset_file(),
            crop_defaults=crop_defaults,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.presets = dialog.get_presets()
            self._update_preset_combo()
    
    def _update_preset_combo(self):
        """Update preset combo box."""
        default_payload = PresetStorage.get_default_payload()
        default_custom_value = float(default_payload.get("pixel_size_presets", {}).get("Custom", 1.0))
        if "Custom" not in self.presets:
            self.presets["Custom"] = default_custom_value
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
        defaults = self._get_mode_dependent_scalebar_defaults(current_preset)
        if defaults is None:
            return
        self.unit_combo.setCurrentText(defaults["unit"])
        self.scalebar_length_spinbox.setValue(defaults["scalebar_length_value"])
        self.scalebar_length_text_raw = defaults["scalebar_length_text"]
    
    def resizeEvent(self, event):
        """Handle window resize."""
        super().resizeEvent(event)
        if self.image_processor.has_image():
            QTimer.singleShot(100, self.update_display)
    
    def batch_annotate(self):
        """Open batch annotation dialog."""
        dialog = BatchProcessingDialog(
            self.presets,
            self.overlay_renderer,
            self,
            initial_input_directory=self.batch_input_directory,
            initial_output_directory=self.batch_output_directory,
            default_crop_top_rows=int(self.crop_top_spinbox.value()) if hasattr(self, "crop_top_spinbox") else 10,
            default_crop_bottom_rows=int(self.crop_bottom_spinbox.value()) if hasattr(self, "crop_bottom_spinbox") else 9,
        )
        result = dialog.exec()
        self.batch_input_directory, self.batch_output_directory = dialog.get_last_directories()
        if result == QDialog.DialogCode.Accepted and hasattr(self, "crop_top_spinbox") and hasattr(self, "crop_bottom_spinbox"):
            top_rows, bottom_rows = dialog.get_crop_defaults()
            self.crop_top_spinbox.setValue(int(top_rows))
            self.crop_bottom_spinbox.setValue(int(bottom_rows))


def main():
    """Main entry point."""
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.debug=false;qt.qpa.fonts.warning=false")

    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TAMIAS")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    icon_path = get_resource_path("tamias.ico")
    if icon_path.exists():
        app_icon = QIcon(str(icon_path))
        if not app_icon.isNull():
            app.setWindowIcon(app_icon)
    
    window = TEMImageEditor()
    if not app.windowIcon().isNull():
        window.setWindowIcon(app.windowIcon())
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
