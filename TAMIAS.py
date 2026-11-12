"""
TAMIAS - Main GUI application.
A Qt application for processing TEM images with scalebar addition,
brightness/contrast adjustment, and export capabilities.
"""

import sys
import os
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from qtpy.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QFileDialog, QComboBox, QDoubleSpinBox,
    QGroupBox, QCheckBox, QMessageBox, QSpinBox, QDialog, QListWidget,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
    QProgressDialog, QScrollArea, QSplitter, QSizePolicy
)
from qtpy.QtCore import Qt, QTimer, QSize, QUrl
from qtpy.QtGui import QPixmap, QImage, QAction, QActionGroup, QColor, QFont, QPalette, QBrush, QIcon, QDesktopServices
from qtpy.QtWidgets import QColorDialog, QFontDialog

# Import our modules
from core.image_processor import ImageProcessor
from core.overlay_renderer import OverlayRenderer, qimage_to_rgba_array
from core.crop_geometry import compute_display_mapping, map_label_to_image_coords, point_to_segment_distance
from core.diffraction import (
    D_SPACING_ANGSTROM,
    DEFAULT_RING_RESOLUTIONS,
    RECIPROCAL_MEASUREMENT_UNITS,
    RECIPROCAL_UNITS,
    DiffractionGeometry,
    electron_wavelength_angstrom,
    format_reciprocal_value,
    format_resolution_label,
    format_resolution_value,
    looks_like_diffraction_header,
)
from utils.preset_manager import PresetManager, PresetStorage
from utils.app_settings_manager import AppSettingsStorage
from utils.imaging_mode_defaults import (
    AUTO_FALLBACK_PRESET,
    AUTO_PRESET_LABEL,
    derive_overlay_defaults,
    get_mode_overlay_defaults,
)
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
        self.setGeometry(100, 100, 1100, 600)

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

        # Diffraction (reciprocal-space) state
        self.image_type = "real"  # "real" or "diffraction"
        self._beam_center_loaded: Optional[tuple[float, float]] = None  # as-loaded pixel coords
        self._beam_pick_active = False
        self._diffraction_manual = {"camera_length_mm": 650.0, "wavelength_angstrom": 0.0251, "pixel_size_um": 100.0}
        self._intensity_scaling_by_type = {"real": "Linear", "diffraction": "Logarithmic"}
        self._scalebar_text_raw_by_type: dict[str, Optional[str]] = {"real": None, "diffraction": None}
        self._syncing_diffraction_controls = False
        self._ring_label_drag_active = False
        self._ring_label_drag: Optional[dict] = None  # {"entry": ring dict, "grab": (dx, dy)}
        
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
        self._apply_diffraction_settings(self._app_settings.get("diffraction", {}))
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

        # Controls must show real-space values while the (real-space) overlay defaults are
        # synced into them, otherwise the reciprocal scalebar length gets overwritten.
        self.set_image_type("real", initial=True)
        self._apply_overlay_settings(self._app_settings.get("overlay", {}))
        self._apply_overlay_settings_to_controls()
        self._apply_diffraction_settings(self._app_settings.get("diffraction", {}))

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
        
        # Real-space image vs diffraction pattern
        ui_sections.setup_image_type_controls(self, controls_layout)

        # Imaging mode preset (real space) / diffraction calibration (reciprocal space)
        self._setup_preset_controls(controls_layout)
        ui_sections.setup_diffraction_calibration_controls(self, controls_layout)

        # Image cropping controls
        self._setup_crop_controls(controls_layout)
        
        # Brightness/Contrast controls
        self._setup_brightness_contrast_controls(controls_layout)
        
        # Transform controls
        self._setup_transform_controls(controls_layout)
        
        # Scalebar controls
        self._setup_scalebar_controls(controls_layout)
        
        # Aperture controls (real space) / resolution rings (diffraction)
        self._setup_aperture_controls(controls_layout)
        ui_sections.setup_resolution_ring_controls(self, controls_layout)

        # Measurement controls
        self._setup_measurement_controls(controls_layout)
        
        controls_layout.addStretch()

        # Set the scroll area's widget
        scroll_area.setWidget(controls_widget)

        # Export button stays pinned below the scrollable controls
        export_btn = QPushButton("Export Image")
        export_btn.setMinimumHeight(40)
        export_btn.clicked.connect(self.export_image)

        right_panel = QWidget()
        right_panel.setMinimumWidth(260)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        # Load button stays pinned above the scrollable controls
        load_btn = QPushButton("Load Image")
        load_btn.setMinimumHeight(40)
        load_btn.clicked.connect(self.load_image)
        right_layout.addWidget(load_btn)
        right_layout.addWidget(scroll_area, 1)
        right_layout.addWidget(export_btn)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(image_widget)
        splitter.addWidget(right_panel)
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
            success, error, dimensions = self.image_processor.load_image(file_path)

            if success:
                self.current_file = file_path
                width, height = dimensions
                filename = Path(file_path).name
                self.file_info_label.setText(f"File: {filename} | Size: {width}x{height}px")

                # Auto adjust and display
                self.image_processor.auto_adjust_contrast()
                self._update_brightness_sliders()

                # Reset overlays that are image-specific
                self._reset_image_specific_overlays(disable_scalebar=True)

                # Auto mode: (re)calibrate from the new file's header, else fall back to a preset
                self._select_calibration_for_loaded_file()

                # Diffraction: beam centre / calibration from the new header; image-type hint
                self._on_image_loaded_diffraction()
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
        if not getattr(self, "_programmatic_preset_change", False):
            self._auto_fell_back = False  # user made an explicit choice
        self._update_pixel_size_editable_state(preset_name)
        if preset_name == AUTO_PRESET_LABEL:
            npp, defaults = self._resolve_auto_calibration()
        elif preset_name in self.presets:
            try:
                npp = float(self.presets[preset_name])
                if npp <= 0:
                    npp = 1.0
            except Exception:
                npp = 1.0
            defaults = get_mode_overlay_defaults(preset_name)
        else:
            return

        self.nm_per_pixel = npp
        self._update_calibration_source_label()
        mode_unit = defaults["unit"] if defaults is not None else None

        if self.image_type == "diffraction":
            # The unit/length widgets show reciprocal-space values right now: only update the
            # stored real-space values so they are restored when switching back.
            if defaults is not None:
                self.overlay_renderer.scalebar_unit = defaults["unit"]
                self.overlay_renderer.scalebar_length_value = float(defaults["scalebar_length_value"])
                self._scalebar_text_raw_by_type["real"] = defaults["scalebar_length_text"]
                self.overlay_renderer.measurement_unit = defaults["unit"]
            self._refresh_scale_information()
            return

        # Set preset-specific scalebar defaults (only if UI is fully initialized)
        if defaults is not None and hasattr(self, 'unit_combo') and hasattr(self, 'scalebar_length_spinbox'):
            if self.unit_combo.currentText() != defaults["unit"]:
                self.unit_combo.setCurrentText(defaults["unit"])
            self.scalebar_length_spinbox.setValue(defaults["scalebar_length_value"])
            self.scalebar_length_text_raw = defaults["scalebar_length_text"]

        if mode_unit is not None and hasattr(self, 'measurement_unit_combo') and self.measurement_unit_combo.currentText() != mode_unit:
            self.measurement_unit_combo.setCurrentText(mode_unit)

        self._refresh_scale_information()

    def _select_calibration_for_loaded_file(self):
        """Pick the imaging mode for a newly loaded file.

        Files with a header pixel size use Auto. Files without one switch the
        dropdown to the fallback preset (and back to Auto for the next file that
        has a header value), unless the user chose a preset themselves.
        """
        has_file_size = bool(self.image_processor.get_file_pixel_size_nm())
        current = self.preset_combo.currentText()
        target = current
        if current == AUTO_PRESET_LABEL and not has_file_size and AUTO_FALLBACK_PRESET in self.presets:
            target = AUTO_FALLBACK_PRESET
            self._auto_fell_back = True
        elif has_file_size and getattr(self, "_auto_fell_back", False):
            target = AUTO_PRESET_LABEL
            self._auto_fell_back = False

        if target != current:
            self._programmatic_preset_change = True
            try:
                self.preset_combo.setCurrentText(target)  # triggers on_preset_changed
            finally:
                self._programmatic_preset_change = False
        elif current == AUTO_PRESET_LABEL:
            self.on_preset_changed(AUTO_PRESET_LABEL)
        else:
            self._update_calibration_source_label()
            self._refresh_scale_information()

    def _resolve_auto_calibration(self):
        """Pixel size (nm) and overlay defaults for Auto mode.

        Uses the loaded file's header pixel size when present; otherwise falls back
        to the 'Standard' preset (or Custom if it is missing).
        """
        file_nm = self.image_processor.get_file_pixel_size_nm()
        if file_nm:
            width = None
            if self.image_processor.original_image is not None:
                width = int(self.image_processor.original_image.shape[1])
            return file_nm, derive_overlay_defaults(file_nm, width)
        fallback = AUTO_FALLBACK_PRESET if AUTO_FALLBACK_PRESET in self.presets else "Custom"
        try:
            npp = float(self.presets.get(fallback, 1.0))
        except Exception:
            npp = 1.0
        return (npp if npp > 0 else 1.0), get_mode_overlay_defaults(fallback)

    def _update_calibration_source_label(self):
        """Show where the active pixel size comes from."""
        label = getattr(self, "calibration_source_label", None)
        if label is None:
            return
        if self.preset_combo.currentText() != AUTO_PRESET_LABEL:
            if getattr(self, "_auto_fell_back", False):
                label.setText("No pixel size in file - using preset. Select 'Auto (from file)' to re-enable.")
            else:
                label.setText("Pixel size source: preset")
        elif self.image_processor.get_file_pixel_size_nm():
            label.setText("Pixel size source: file header")
        elif self.image_processor.has_image():
            label.setText(f"No pixel size in file - using '{AUTO_FALLBACK_PRESET}' preset. Pick a preset to override.")
        else:
            label.setText(f"Pixel size source: file header if available, else '{AUTO_FALLBACK_PRESET}' preset")

    def _get_mode_dependent_unit(self, preset_name: str) -> str | None:
        """Return the measurement/scalebar unit associated with the active image mode."""
        if preset_name == AUTO_PRESET_LABEL:
            defaults = self._resolve_auto_calibration()[1]
            return defaults["unit"] if defaults is not None else None
        defaults = get_mode_overlay_defaults(preset_name)
        if defaults is not None:
            return defaults["unit"]
        return None

    def _get_mode_dependent_scalebar_defaults(self, preset_name: str) -> dict | None:
        """Compatibility wrapper around shared imaging-mode overlay defaults."""
        if preset_name == AUTO_PRESET_LABEL:
            return self._resolve_auto_calibration()[1]
        return get_mode_overlay_defaults(preset_name)

    def _refresh_scale_information(self):
        """Refresh scale-dependent UI and overlays after calibration or preset updates."""
        self._update_pixel_size_display()
        self._sync_beam_center_controls()
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
        self._sync_beam_center_controls()
        self._update_measurement_info_label()
        self.update_display()

    def flip_vertical(self):
        """Flip image vertically."""
        self.image_processor.flip_vertical()
        self._sync_beam_center_controls()
        self._update_measurement_info_label()
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
        # numeric value for pixel conversion (stored per image type)
        if self.image_type == "diffraction":
            self.overlay_renderer.recip_scalebar_length_value = float(self.scalebar_length_spinbox.value())
        else:
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
        if self.image_type == "diffraction":
            if unit in RECIPROCAL_UNITS:
                self.overlay_renderer.recip_scalebar_unit = unit
        elif unit in ("nm", "µm"):
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
        unit = self.measurement_unit_combo.currentText()
        if self.image_type == "diffraction":
            if unit in RECIPROCAL_MEASUREMENT_UNITS:
                self.overlay_renderer.recip_measurement_unit = unit
        elif unit in ("nm", "µm"):
            self.overlay_renderer.measurement_unit = unit
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
            self._cancel_diffraction_tools()
            self._refresh_image_interaction_mode()
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
            self._cancel_diffraction_tools()
            self._refresh_image_interaction_mode()
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
            self._cancel_diffraction_tools()
            self._refresh_image_interaction_mode()
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
            self._cancel_diffraction_tools()
            self._refresh_image_interaction_mode()
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
        if self._beam_pick_active or self._draw_mode_active:
            self.image_label.set_draw_mode(True)
            return
        if (self._label_drag_active or self._line_drag_active or self._scalebar_drag_active
                or self._ring_label_drag_active):
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
        self._sync_anchored_measurements()
        self.measurement_table.setRowCount(0)
        diffraction = self.current_diffraction_geometry()
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
            value, unit = self.overlay_renderer.measurement_value(
                m["start"], m["end"], self.nm_per_pixel, diffraction
            )
            if diffraction is None:
                length_text = f"{value:.1f} {unit}"
            elif self.overlay_renderer.recip_measurement_unit == D_SPACING_ANGSTROM:
                length_text = format_resolution_value(value)
            else:
                length_text = f"{format_reciprocal_value(value)} {unit}"
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
    
    # ------------------------------------------------------------------------------------
    # Diffraction patterns (reciprocal space)
    # ------------------------------------------------------------------------------------

    def _apply_diffraction_settings(self, settings: dict):
        """Restore persisted diffraction settings and the last used image type."""
        if not isinstance(settings, dict):
            settings = {}

        def _pos_float(key: str, current: float) -> float:
            try:
                value = float(settings.get(key, current))
            except (TypeError, ValueError):
                return current
            return value if np.isfinite(value) and value > 0 else current

        for key in ("camera_length_mm", "wavelength_angstrom", "pixel_size_um"):
            self._diffraction_manual[key] = _pos_float(key, self._diffraction_manual[key])
        for image_type in ("real", "diffraction"):
            mode = str(settings.get(f"intensity_scaling_{image_type}", self._intensity_scaling_by_type[image_type]))
            if mode in ImageProcessor.INTENSITY_SCALING_MODES:
                self._intensity_scaling_by_type[image_type] = mode

        self.diffraction_use_header_checkbox.blockSignals(True)
        self.diffraction_use_header_checkbox.setChecked(bool(settings.get("use_header", True)))
        self.diffraction_use_header_checkbox.blockSignals(False)
        self.snap_beam_center_checkbox.setChecked(bool(settings.get("snap_beam_center", True)))
        self.measure_from_center_checkbox.setChecked(bool(settings.get("measure_from_center", True)))
        self.snap_measurement_end_checkbox.setChecked(bool(settings.get("snap_measurement_end", False)))

        image_type = str(settings.get("image_type", "real"))
        self.set_image_type(image_type if image_type in ("real", "diffraction") else "real", initial=True)

    def _collect_diffraction_settings(self) -> dict:
        return {
            "image_type": self.image_type,
            "use_header": bool(self.diffraction_use_header_checkbox.isChecked()),
            "camera_length_mm": float(self._diffraction_manual["camera_length_mm"]),
            "wavelength_angstrom": float(self._diffraction_manual["wavelength_angstrom"]),
            "pixel_size_um": float(self._diffraction_manual["pixel_size_um"]),
            "snap_beam_center": bool(self.snap_beam_center_checkbox.isChecked()),
            "measure_from_center": bool(self.measure_from_center_checkbox.isChecked()),
            "snap_measurement_end": bool(self.snap_measurement_end_checkbox.isChecked()),
            "intensity_scaling_real": self._intensity_scaling_by_type["real"],
            "intensity_scaling_diffraction": self._intensity_scaling_by_type["diffraction"],
        }

    def on_image_type_combo_changed(self, _index: int):
        self.set_image_type(str(self.image_type_combo.currentData() or "real"))

    def on_image_type_hint_clicked(self):
        self.set_image_type("real" if self.image_type == "diffraction" else "diffraction")

    def set_image_type(self, new_type: str, initial: bool = False):
        """Switch between real-space images and diffraction patterns."""
        if new_type not in ("real", "diffraction"):
            new_type = "real"
        old_type = self.image_type
        if not initial and new_type == old_type:
            return
        if not initial:
            self._scalebar_text_raw_by_type[old_type] = getattr(self, "scalebar_length_text_raw", None)
        if self.pick_beam_center_btn.isChecked():
            self.pick_beam_center_btn.setChecked(False)

        self.image_type = new_type
        diffraction = new_type == "diffraction"
        renderer = self.overlay_renderer

        index = self.image_type_combo.findData(new_type)
        if index >= 0 and self.image_type_combo.currentIndex() != index:
            self.image_type_combo.blockSignals(True)
            self.image_type_combo.setCurrentIndex(index)
            self.image_type_combo.blockSignals(False)

        self.preset_box.setVisible(not diffraction)
        self.aperture_box.setVisible(not diffraction)
        self.diffraction_box.setVisible(diffraction)
        self.rings_box.setVisible(diffraction)
        self.diffraction_measure_widget.setVisible(diffraction)
        self.measurement_unit_label.setText("Label shows:" if diffraction else "Length Unit:")
        self._cancel_ring_label_drag()

        # Unit selectors and scalebar length: each image type keeps its own values
        self.unit_combo.blockSignals(True)
        self.unit_combo.clear()
        self.unit_combo.addItems(list(RECIPROCAL_UNITS) if diffraction else ["nm", "µm"])
        self.unit_combo.setCurrentText(renderer.recip_scalebar_unit if diffraction else renderer.scalebar_unit)
        self.unit_combo.blockSignals(False)

        self.measurement_unit_combo.blockSignals(True)
        self.measurement_unit_combo.clear()
        self.measurement_unit_combo.addItems(list(RECIPROCAL_MEASUREMENT_UNITS) if diffraction else ["nm", "µm"])
        self.measurement_unit_combo.setCurrentText(
            renderer.recip_measurement_unit if diffraction else renderer.measurement_unit
        )
        self.measurement_unit_combo.blockSignals(False)

        length = float(renderer.recip_scalebar_length_value if diffraction else renderer.scalebar_length_value)
        raw = self._scalebar_text_raw_by_type.get(new_type)
        try:
            if raw is not None and abs(float(raw) - length) > 1e-9:
                raw = None
        except ValueError:
            raw = None
        self.scalebar_length_text_raw = raw
        self.scalebar_length_spinbox.blockSignals(True)
        self.scalebar_length_spinbox.setValue(length)
        self.scalebar_length_spinbox.blockSignals(False)

        mode = self._intensity_scaling_by_type[new_type]
        self.intensity_scaling_combo.blockSignals(True)
        self.intensity_scaling_combo.setCurrentText(mode)
        self.intensity_scaling_combo.blockSignals(False)
        self._apply_intensity_scaling(mode)

        self._populate_diffraction_fields()
        self._update_image_type_hint()
        self._refresh_scale_information()

    def _update_image_type_hint(self):
        """Suggest switching image type when the file header disagrees with the selection."""
        text = ""
        button = ""
        if self.image_processor.has_image():
            header = self.image_processor.rod_header_info
            if self.image_type == "real" and looks_like_diffraction_header(header):
                text = "This file looks like a diffraction pattern (its header has no direct-space pixel size)."
                button = "Switch to Diffraction"
            elif self.image_type == "diffraction" and self.image_processor.get_file_pixel_size_nm():
                text = "This file has a direct-space pixel size, so it looks like a real-space image."
                button = "Switch to Real Space"
        self.image_type_hint_label.setText(text)
        self.image_type_hint_btn.setText(button)
        self.image_type_hint_label.setVisible(bool(text))
        self.image_type_hint_btn.setVisible(bool(text))

    def on_intensity_scaling_changed(self, mode: str):
        if mode not in ImageProcessor.INTENSITY_SCALING_MODES:
            return
        self._intensity_scaling_by_type[self.image_type] = mode
        self._apply_intensity_scaling(mode)
        self.update_display()

    def _apply_intensity_scaling(self, mode: str):
        """Rebuild the display image with a new raw -> 8-bit mapping and re-run auto contrast."""
        processor = self.image_processor
        if processor.intensity_scaling == mode:
            return
        processor.intensity_scaling = mode
        if processor.has_image() and processor.set_intensity_scaling(mode):
            processor.auto_adjust_contrast()
            self._update_brightness_sliders()

    # --- Calibration values ---

    def _header_geometry(self) -> dict:
        if not self.image_processor.has_image():
            return {}
        return self.image_processor.get_header_diffraction_geometry()

    def _populate_diffraction_fields(self):
        """Fill camera length / wavelength / pixel size from the header or manual values."""
        header = self._header_geometry()
        use_header = self.diffraction_use_header_checkbox.isChecked()
        fields = (
            ("camera_length_mm", self.camera_length_spinbox, "camera_length_mm", 1.0),
            ("wavelength_angstrom", self.wavelength_spinbox, "wavelength_angstrom", 1.0),
            ("pixel_size_mm", self.detector_pixel_spinbox, "pixel_size_um", 1000.0),
        )
        sources = []
        self._syncing_diffraction_controls = True
        try:
            for header_key, spin, manual_key, factor in fields:
                if use_header and header_key in header:
                    spin.setValue(float(header[header_key]) * factor)
                    spin.setEnabled(False)
                    sources.append("header")
                else:
                    spin.setValue(float(self._diffraction_manual[manual_key]))
                    spin.setEnabled(True)
                    sources.append("manual")
            self.voltage_combo.setEnabled(self.wavelength_spinbox.isEnabled())
        finally:
            self._syncing_diffraction_controls = False

        if not self.image_processor.has_image():
            text = "Header values are used when the loaded file provides them." if use_header else "Using manual values."
        elif all(s == "header" for s in sources):
            text = "Camera length, wavelength and pixel size from the file header."
        elif all(s == "manual" for s in sources):
            text = ("Using manual values (no header values in this file)." if use_header
                    else "Using manual values.")
        else:
            missing = [name for name, s in zip(("camera length", "wavelength", "pixel size"), sources) if s == "manual"]
            text = f"From file header, except {', '.join(missing)} (not in header - enter manually)."
        self.diffraction_source_label.setText(text)

    def on_diffraction_use_header_toggled(self, checked: bool):
        self._populate_diffraction_fields()
        if checked and self.image_processor.has_image() and "beam_center_px" in self._header_geometry():
            self._beam_center_loaded = tuple(self._header_geometry()["beam_center_px"])
        self._refresh_scale_information()

    def on_diffraction_parameter_changed(self, _value: float = 0.0):
        if self._syncing_diffraction_controls:
            return
        if self.camera_length_spinbox.isEnabled():
            self._diffraction_manual["camera_length_mm"] = float(self.camera_length_spinbox.value())
        if self.wavelength_spinbox.isEnabled():
            self._diffraction_manual["wavelength_angstrom"] = float(self.wavelength_spinbox.value())
        if self.detector_pixel_spinbox.isEnabled():
            self._diffraction_manual["pixel_size_um"] = float(self.detector_pixel_spinbox.value())
        self._update_diffraction_info_label()
        self._update_measurement_info_label()
        self.update_display()

    def on_voltage_preset_selected(self, index: int):
        kv = self.voltage_combo.itemData(index)
        self.voltage_combo.setCurrentIndex(0)
        if kv is None or not self.wavelength_spinbox.isEnabled():
            return
        self.wavelength_spinbox.setValue(electron_wavelength_angstrom(float(kv)))

    def current_diffraction_geometry(self) -> Optional[DiffractionGeometry]:
        """Active diffraction calibration, or None for real-space images."""
        if self.image_type != "diffraction" or not hasattr(self, "camera_length_spinbox"):
            return None
        center = self._beam_center_current()
        if center is None:
            center = (float("nan"), float("nan"))
        return DiffractionGeometry(
            camera_length_mm=float(self.camera_length_spinbox.value()),
            wavelength_angstrom=float(self.wavelength_spinbox.value()),
            pixel_size_mm=float(self.detector_pixel_spinbox.value()) / 1000.0,
            beam_center_px=(float(center[0]), float(center[1])),
        )

    # --- Beam centre ---

    def _default_beam_center_loaded(self) -> Optional[tuple[float, float]]:
        """Header beam position (as loaded) if enabled/available, else the current image centre."""
        if not self.image_processor.has_image():
            return None
        header = self._header_geometry()
        if self.diffraction_use_header_checkbox.isChecked() and "beam_center_px" in header:
            return tuple(header["beam_center_px"])
        h, w = self.image_processor.get_current_image().shape[:2]
        return self.image_processor.map_current_to_loaded(w / 2.0, h / 2.0)

    def _beam_center_current(self) -> Optional[tuple[float, float]]:
        if not self.image_processor.has_image():
            return None
        if self._beam_center_loaded is None:
            self._beam_center_loaded = self._default_beam_center_loaded()
        if self._beam_center_loaded is None:
            return None
        return self.image_processor.map_loaded_to_current(*self._beam_center_loaded)

    def _on_image_loaded_diffraction(self):
        """New file: take calibration and beam centre from its header (or defaults)."""
        self._beam_center_loaded = None
        self._beam_center_loaded = self._default_beam_center_loaded()
        self._populate_diffraction_fields()
        self._update_image_type_hint()
        self._refresh_scale_information()

    def _sync_beam_center_controls(self):
        """Show the beam centre in current image coordinates (follows crops and flips)."""
        if not hasattr(self, "beam_center_x_spinbox"):
            return
        center = self._beam_center_current()
        self._syncing_diffraction_controls = True
        try:
            enabled = center is not None
            self.beam_center_x_spinbox.setEnabled(enabled)
            self.beam_center_y_spinbox.setEnabled(enabled)
            if center is not None:
                self.beam_center_x_spinbox.setValue(center[0])
                self.beam_center_y_spinbox.setValue(center[1])
        finally:
            self._syncing_diffraction_controls = False
        self._update_diffraction_info_label()

    def on_beam_center_spinbox_changed(self, _value: float = 0.0):
        if self._syncing_diffraction_controls or not self.image_processor.has_image():
            return
        self._beam_center_loaded = self.image_processor.map_current_to_loaded(
            float(self.beam_center_x_spinbox.value()), float(self.beam_center_y_spinbox.value())
        )
        self._update_diffraction_info_label()
        self._update_measurement_info_label()
        self.update_display()

    def reset_beam_center(self):
        self._beam_center_loaded = self._default_beam_center_loaded()
        self._sync_beam_center_controls()
        self._update_measurement_info_label()
        self.update_display()

    def _cancel_diffraction_tools(self):
        """Switch off diffraction-only mouse tools when another interaction mode starts."""
        self._cancel_beam_pick()
        self._cancel_ring_label_drag()

    def _cancel_ring_label_drag(self):
        if hasattr(self, "move_ring_label_btn") and self.move_ring_label_btn.isChecked():
            self.move_ring_label_btn.blockSignals(True)
            self.move_ring_label_btn.setChecked(False)
            self.move_ring_label_btn.blockSignals(False)
        self._ring_label_drag_active = False
        self._ring_label_drag = None

    def on_ring_label_drag_mode_toggled(self, checked: bool):
        self._ring_label_drag_active = checked
        self._ring_label_drag = None
        if checked:
            self._cancel_beam_pick()
            for btn_name in ("draw_measurement_btn", "move_line_btn", "move_label_btn", "move_scalebar_btn",
                             "manual_crop_select_btn", "manual_crop_move_btn"):
                btn = getattr(self, btn_name, None)
                if btn is not None and btn.isChecked():
                    btn.setChecked(False)
            self._ring_label_drag_active = True
            if not self.ring_labels_checkbox.isChecked():
                self.ring_labels_checkbox.setChecked(True)
            self.measurement_status_label.setText("Move Ring Labels: drag a ring label to reposition it.")
        self._refresh_image_interaction_mode()

    def _on_rings_section_toggled(self, expanded: bool):
        if not expanded:
            self._cancel_ring_label_drag()
            self._refresh_image_interaction_mode()

    def _label_to_image_float(self, label_x: int, label_y: int) -> Optional[tuple[float, float]]:
        if self._last_rendered_image_size is None:
            return None
        _w, _h, scale, offset_x, offset_y = self._get_display_mapping()
        if scale <= 0:
            return None
        return ((float(label_x) - offset_x) / scale, (float(label_y) - offset_y) / scale)

    def start_ring_label_drag(self, label_x: int, label_y: int):
        self._ring_label_drag = None
        geometry = self.current_diffraction_geometry()
        point = self._label_to_image_float(label_x, label_y)
        if geometry is None or not geometry.is_valid() or point is None or not self.overlay_renderer.rings_enabled:
            return
        img_w, img_h = self._last_rendered_image_size
        _w, _h, scale, _ox, _oy = self._get_display_mapping()
        pad = 6.0 / max(scale, 1e-6)
        px, py = point
        best = None
        for ring in self.overlay_renderer.compute_ring_layout(img_w, img_h, geometry):
            box = ring.get("label_box")
            if box is None:
                continue
            if box["left"] - pad <= px <= box["right"] + pad and box["top"] - pad <= py <= box["bottom"] + pad:
                dist = (box["cx"] - px) ** 2 + (box["cy"] - py) ** 2
                if best is None or dist < best[0]:
                    best = (dist, ring)
        if best is None:
            self.measurement_status_label.setText("No ring label found here. Click on a ring label.")
            return
        ring = best[1]
        self._ring_label_drag = {"entry": ring["entry"], "grab": (ring["label_box"]["cx"] - px,
                                                                   ring["label_box"]["cy"] - py)}

    def update_ring_label_drag(self, label_x: int, label_y: int):
        drag = self._ring_label_drag
        geometry = self.current_diffraction_geometry()
        point = self._label_to_image_float(label_x, label_y)
        if drag is None or geometry is None or not geometry.is_valid() or point is None:
            return
        entry = drag["entry"]
        radius = geometry.radius_px_for_resolution(float(entry["d"]))
        if radius is None:
            return
        cx, cy = geometry.beam_center_px
        bx = point[0] + drag["grab"][0]
        by = point[1] + drag["grab"][1]
        # Store polar position relative to the ring so the label follows calibration changes.
        entry["label_angle"] = float(np.degrees(np.arctan2(by - cy, bx - cx)))
        entry["label_radial"] = float(np.hypot(bx - cx, by - cy) - radius)
        self.update_display()

    def finish_ring_label_drag(self, label_x: int, label_y: int):
        self.update_ring_label_drag(label_x, label_y)
        self._ring_label_drag = None

    def reset_ring_label_positions(self):
        for entry in self.overlay_renderer.ring_resolutions:
            entry.pop("label_angle", None)
            entry.pop("label_radial", None)
        self.update_display()

    def _update_ring_font_label(self):
        font = self.overlay_renderer._ring_font()
        pt = font.pointSize()
        px = font.pixelSize()
        size_text = f"{pt}pt" if pt > 0 else f"{px}px" if px > 0 else ""
        self.ring_font_label.setText(f"Font: {font.family()}" + (f", {size_text}" if size_text else ""))

    def choose_ring_font(self):
        options = QFontDialog.FontDialogOption.ScalableFonts | QFontDialog.FontDialogOption.DontUseNativeDialog
        font, ok = QFontDialog.getFont(self.overlay_renderer._ring_font(), self, "Choose Ring Label Font", options=options)
        if ok:
            self.overlay_renderer.ring_font = QFont(font)
            self._update_ring_font_label()
            self.update_display()

    def _sync_anchored_measurements(self):
        """Keep the start of centre-anchored measurements on the current beam centre."""
        if self.image_type != "diffraction":
            return
        anchored = [m for m in self.overlay_renderer.measurements if m.get("anchor_center")]
        if not anchored:
            return
        center = self._beam_center_current()
        if center is None:
            return
        for m in anchored:
            m["start"] = (float(center[0]), float(center[1]))

    def _cancel_beam_pick(self):
        if hasattr(self, "pick_beam_center_btn") and self.pick_beam_center_btn.isChecked():
            self.pick_beam_center_btn.blockSignals(True)
            self.pick_beam_center_btn.setChecked(False)
            self.pick_beam_center_btn.blockSignals(False)
        self._beam_pick_active = False

    def on_beam_center_pick_toggled(self, checked: bool):
        self._beam_pick_active = checked
        if checked:
            self._cancel_ring_label_drag()
            for btn_name in ("draw_measurement_btn", "move_line_btn", "move_label_btn", "move_scalebar_btn",
                             "manual_crop_select_btn", "manual_crop_move_btn"):
                btn = getattr(self, btn_name, None)
                if btn is not None and btn.isChecked():
                    btn.setChecked(False)
            self._beam_pick_active = True
            self.measurement_status_label.setText("Pick Beam Centre: click the direct beam / pattern centre on the image.")
        self._refresh_image_interaction_mode()

    def _on_diffraction_section_toggled(self, expanded: bool):
        if not expanded and self.pick_beam_center_btn.isChecked():
            self.pick_beam_center_btn.setChecked(False)

    def handle_beam_center_click(self, label_x: int, label_y: int):
        """Set the beam centre from a click on the image (optionally snapped to the peak)."""
        if self._last_rendered_image_size is None:
            return
        img_w, img_h, scale, offset_x, offset_y = self._get_display_mapping()
        fx = (float(label_x) - offset_x) / scale
        fy = (float(label_y) - offset_y) / scale
        if not (0.0 <= fx <= img_w and 0.0 <= fy <= img_h):
            return
        snapped = False
        if self.snap_beam_center_checkbox.isChecked():
            refined = self.image_processor.refine_peak_centroid(fx, fy)
            if refined is not None:
                fx, fy = refined
                snapped = True
        self._beam_center_loaded = self.image_processor.map_current_to_loaded(fx, fy)
        self.pick_beam_center_btn.setChecked(False)
        self._sync_beam_center_controls()
        self._update_measurement_info_label()
        self.measurement_status_label.setText(
            f"Beam centre set to ({fx:.1f}, {fy:.1f})" + (" (snapped to intensity peak)." if snapped else ".")
        )
        self.update_display()

    def _update_diffraction_info_label(self):
        label = getattr(self, "diffraction_info_label", None)
        if label is None:
            return
        geometry = self.current_diffraction_geometry()
        if geometry is None or not geometry.is_valid():
            label.setText("Load a diffraction pattern to see the reciprocal-space calibration."
                          if not self.image_processor.has_image() else "Calibration incomplete.")
            return
        per_px = geometry.inv_angstrom_per_pixel()
        lines = [f"Reciprocal pixel size: {per_px:.5f} Å⁻¹/px ({per_px * 10.0:.4f} nm⁻¹/px)"]
        h, w = self.image_processor.get_current_image().shape[:2]
        edge, corner = geometry.max_resolution_in_image(w, h)
        edge_text = "-" if not np.isfinite(edge) else f"{edge:.2f} Å"
        lines.append(f"Complete rings to {edge_text}; corners reach {corner:.2f} Å")
        header = self.image_processor.rod_header_info or {}
        try:
            bin_x, bin_y = int(header.get("bin_x") or 1), int(header.get("bin_y") or 1)
        except (TypeError, ValueError):
            bin_x = bin_y = 1
        if (bin_x, bin_y) != (1, 1):
            lines.append(f"Binned image ({bin_x}×{bin_y}): please check the detector pixel size.")
        from core.diffraction import header_tilt_warning
        warning = header_tilt_warning(header)
        if warning:
            lines.append(warning)
        label.setText("\n".join(lines))

    # --- Resolution rings ---

    def _populate_ring_list(self):
        from qtpy.QtWidgets import QListWidgetItem
        self.ring_list.blockSignals(True)
        self.ring_list.clear()
        entries = sorted(self.overlay_renderer.ring_resolutions, key=lambda e: float(e.get("d", 0.0)))
        self.overlay_renderer.ring_resolutions = entries
        for entry in entries:
            d = float(entry.get("d"))
            item = QListWidgetItem(format_resolution_label(d))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if entry.get("enabled", True) else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, d)
            self.ring_list.addItem(item)
        self.ring_list.blockSignals(False)

    def _ring_entries_from_list(self) -> list:
        """Rebuild ring entries from the list widget, keeping existing per-ring extras
        (e.g. manual label positions)."""
        existing = {round(float(e["d"]), 6): e for e in self.overlay_renderer.ring_resolutions}
        entries = []
        for row in range(self.ring_list.count()):
            item = self.ring_list.item(row)
            d = float(item.data(Qt.ItemDataRole.UserRole))
            entry = dict(existing.get(round(d, 6), {}))
            entry["d"] = d
            entry["enabled"] = item.checkState() == Qt.CheckState.Checked
            entries.append(entry)
        return entries

    def on_ring_item_changed(self, _item):
        self.overlay_renderer.ring_resolutions = self._ring_entries_from_list()
        self.update_display()

    def on_rings_toggled(self, state):
        self.overlay_renderer.rings_enabled = (state == Qt.CheckState.Checked.value)
        self.update_display()

    def add_resolution_ring(self):
        d = round(float(self.ring_add_spinbox.value()), 6)
        if d <= 0:
            return
        entries = list(self.overlay_renderer.ring_resolutions)
        for entry in entries:
            if abs(float(entry["d"]) - d) < 1e-6:
                entry["enabled"] = True
                break
        else:
            entries.append({"d": d, "enabled": True})
        self.overlay_renderer.ring_resolutions = entries
        self._populate_ring_list()
        if not self.rings_checkbox.isChecked():
            self.rings_checkbox.setChecked(True)
        geometry = self.current_diffraction_geometry()
        if geometry is not None and geometry.is_valid() and geometry.radius_px_for_resolution(d) is None:
            self.measurement_status_label.setText(
                f"{format_resolution_label(d)} cannot be reached at this wavelength (λ/2d > 1 or 2θ ≥ 90°)."
            )
        self.update_display()

    def remove_selected_resolution_rings(self):
        rows = sorted({self.ring_list.row(item) for item in self.ring_list.selectedItems()}, reverse=True)
        if not rows:
            return
        for row in rows:
            self.ring_list.takeItem(row)
        self.overlay_renderer.ring_resolutions = self._ring_entries_from_list()
        self.update_display()

    def restore_resolution_ring_presets(self):
        self.overlay_renderer.ring_resolutions = [{"d": float(d), "enabled": True} for d in DEFAULT_RING_RESOLUTIONS]
        self._populate_ring_list()
        self.update_display()

    def on_ring_style_changed(self, _value=None):
        self.overlay_renderer.ring_line_width = int(self.ring_width_spinbox.value())
        self.overlay_renderer.ring_show_labels = self.ring_labels_checkbox.isChecked()
        self.overlay_renderer.beam_center_marker_enabled = self.beam_marker_checkbox.isChecked()
        self.update_display()

    def choose_ring_color(self):
        color = QColorDialog.getColor(self.overlay_renderer.ring_color, self, "Choose Resolution Ring Color")
        if color.isValid():
            self.overlay_renderer.ring_color = color
            set_color_button_indicator(self.ring_color_btn, color)
            self.update_display()

    def update_display(self):
        """Update the displayed image."""
        if not self.image_processor.has_image():
            return
        
        # Get current image with overlays
        self._sync_anchored_measurements()
        diffraction = self.current_diffraction_geometry()
        q_image = self.overlay_renderer.render_image_with_overlays(
            self.image_processor.get_current_image(),
            self.nm_per_pixel,
            diffraction,
        )

        if q_image is None:
            return

        too_long = (
            diffraction is not None and diffraction.is_valid()
            and not self.overlay_renderer.scalebar_fits(q_image.width(), q_image.height(), self.nm_per_pixel, diffraction)
        )
        if too_long and not getattr(self, "_scalebar_too_long_reported", False):
            self.measurement_status_label.setText(
                "Scalebar not drawn: the requested length is longer than the image. Choose a shorter length."
            )
        self._scalebar_too_long_reported = too_long

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
                    self.nm_per_pixel,
                    self.current_diffraction_geometry(),
                )
                
                if q_image is None:
                    QMessageBox.warning(self, "Warning", "No image to export.")
                    return
                
                # Convert to RGBA8888 numpy array (works under PyQt6 and PySide6)
                export_rgba = qimage_to_rgba_array(q_image)
                
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
        self.preset_combo.addItem(AUTO_PRESET_LABEL)
        self.preset_combo.addItems(sorted(self.presets.keys()))
        if current and (current in self.presets or current == AUTO_PRESET_LABEL):
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
        # Applies pixel size, unit and scalebar defaults for the active preset (or Auto)
        self.on_preset_changed(self.preset_combo.currentText())
    
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
            image_type=self.image_type,
            diffraction_defaults={
                "camera_length_mm": float(self._diffraction_manual["camera_length_mm"]),
                "wavelength_angstrom": float(self._diffraction_manual["wavelength_angstrom"]),
                "pixel_size_um": float(self._diffraction_manual["pixel_size_um"]),
                "use_header": bool(self.diffraction_use_header_checkbox.isChecked()),
                "intensity_scaling": self._intensity_scaling_by_type[self.image_type],
            },
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
