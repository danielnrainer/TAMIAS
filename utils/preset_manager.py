"""
Preset management module for TEM Image Editor.
Handles preset storage, loading, and the preset management dialog.
"""

import json
from pathlib import Path
from typing import Dict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialogButtonBox, QFileDialog, QMessageBox, QLabel
)

from utils.storage_paths import ensure_app_storage_dir


DEFAULT_PIXEL_PRESETS = {
    "Standard": 35.6,
    "Local Map": 80.5,
    "Reference": 16.0,
    "In focus": 32.9,
    "High Res": 5.3,
    "Custom": 1.0,
}

DEFAULT_CROP_DEFAULTS = {
    "top_rows": 10,
    "bottom_rows": 9,
}


class PresetManager(QDialog):
    """Dialog for managing imaging mode presets."""
    
    def __init__(self, presets: Dict[str, float], parent=None, preset_file: Path | None = None, crop_defaults: dict | None = None):
        super().__init__(parent)
        self.presets = presets.copy()
        self.current_file = Path(preset_file) if preset_file else PresetStorage.get_preset_file()
        self.crop_defaults = PresetStorage._normalize_crop_defaults(crop_defaults or {})
        self.setWindowTitle("Manage Presets")
        self.setModal(True)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()

        self.file_label = QLabel(self._current_file_text())
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        file_button_layout = QHBoxLayout()
        load_file_btn = QPushButton("Load from File...")
        load_file_btn.clicked.connect(self.load_from_file)
        save_file_btn = QPushButton("Save")
        save_file_btn.clicked.connect(self.save_to_current_file)
        save_as_btn = QPushButton("Save As...")
        save_as_btn.clicked.connect(self.save_as_file)

        file_button_layout.addWidget(load_file_btn)
        file_button_layout.addWidget(save_file_btn)
        file_button_layout.addWidget(save_as_btn)
        layout.addLayout(file_button_layout)
        
        # Table for presets
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Mode Name", "nm per pixel"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        self.populate_table()
        
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        add_btn = QPushButton("Add Preset")
        add_btn.clicked.connect(self.add_preset)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_preset)
        
        button_layout.addWidget(add_btn)
        button_layout.addWidget(remove_btn)
        layout.addLayout(button_layout)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        self.resize(400, 300)

    def _current_file_text(self) -> str:
        if self.current_file:
            return f"File: {self.current_file}"
        return "File: <not selected>"

    def _sync_payload_from_table(self) -> dict:
        return {
            "pixel_size_presets": self.get_presets(),
            "crop_defaults": dict(self.crop_defaults),
        }

    def _reload_from_payload(self, payload: dict, file_path: Path | None = None):
        presets = PresetStorage._extract_pixel_presets(payload.get("pixel_size_presets", {}))
        if "Custom" not in presets:
            presets["Custom"] = 1.0
        self.presets = presets
        self.crop_defaults = PresetStorage._normalize_crop_defaults(payload.get("crop_defaults", {}))
        if file_path is not None:
            self.current_file = Path(file_path)
        self.populate_table()
        self.file_label.setText(self._current_file_text())

    def load_from_file(self):
        start_dir = str(self.current_file.parent) if self.current_file else str(ensure_app_storage_dir())
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
            QMessageBox.critical(self, "Preset Import", f"Failed to load presets:\n{e}")
            return
        self._reload_from_payload(payload, Path(file_path))

    def save_to_current_file(self):
        if self.current_file is None:
            return self.save_as_file()

        payload = self._sync_payload_from_table()
        try:
            PresetStorage.save_preset_payload_to_file(payload, self.current_file)
        except Exception as e:
            QMessageBox.critical(self, "Preset Save", f"Failed to save presets:\n{e}")
            return False
        self.file_label.setText(self._current_file_text())
        return True

    def save_as_file(self):
        start_dir = str(self.current_file.parent) if self.current_file else str(PresetStorage.get_preset_file().parent)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Presets to JSON",
            start_dir,
            "JSON Files (*.json);;All Files (*.*)",
        )
        if not file_path:
            return
        payload = self._sync_payload_from_table()
        try:
            PresetStorage.save_preset_payload_to_file(payload, Path(file_path))
        except Exception as e:
            QMessageBox.critical(self, "Preset Save", f"Failed to save presets:\n{e}")
            return False
        self.current_file = Path(file_path)
        self.file_label.setText(self._current_file_text())
        return True
        
    def populate_table(self):
        self.table.setRowCount(len(self.presets))
        for row, (name, value) in enumerate(sorted(self.presets.items())):
            name_item = QTableWidgetItem(name)
            value_item = QTableWidgetItem(str(value))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, value_item)
            
    def add_preset(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem("New Mode"))
        self.table.setItem(row, 1, QTableWidgetItem("1.0"))
        
    def remove_preset(self):
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)
            
    def get_presets(self) -> Dict[str, float]:
        """Get the updated presets from the table."""
        presets = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            if name_item and value_item:
                try:
                    name = name_item.text().strip()
                    value = float(value_item.text())
                    if name and value > 0:
                        presets[name] = value
                except ValueError:
                    pass
        return presets

    def accept(self):
        self.presets = self.get_presets()
        if self.save_to_current_file():
            super().accept()


class PresetStorage:
    """Handles loading and saving presets to disk."""

    @staticmethod
    def _legacy_preset_files() -> list[Path]:
        project_root = Path(__file__).resolve().parent.parent
        return [
            Path(__file__).resolve().parent / "tem_presets.json",
            project_root / "pixelsize_presets.json",
        ]

    @staticmethod
    def _normalize_crop_defaults(raw: object) -> dict:
        crop = dict(DEFAULT_CROP_DEFAULTS)
        if isinstance(raw, dict):
            for key in ("top_rows", "bottom_rows"):
                value = raw.get(key)
                try:
                    crop[key] = max(0, int(value))
                except Exception:
                    pass
        return crop

    @staticmethod
    def _extract_pixel_presets(raw: object) -> Dict[str, float]:
        extracted: Dict[str, float] = {}
        if not isinstance(raw, dict):
            return extracted
        for name, value in raw.items():
            try:
                preset_name = str(name).strip()
                numeric_value = float(value)
                if preset_name and numeric_value > 0:
                    extracted[preset_name] = numeric_value
            except Exception:
                continue
        return extracted
    
    @staticmethod
    def get_preset_file() -> Path:
        """Get the path to the preset file."""
        return ensure_app_storage_dir() / "presets.json"

    @staticmethod
    def load_preset_payload_from_file(file_path: Path) -> dict:
        """Load preset payload from an arbitrary JSON file path."""
        payload = {
            "pixel_size_presets": dict(DEFAULT_PIXEL_PRESETS),
            "crop_defaults": dict(DEFAULT_CROP_DEFAULTS),
        }

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                loaded_raw = json.load(f)
        except Exception as e:
            raise ValueError(f"Could not read preset file: {e}") from e

        if isinstance(loaded_raw, dict) and "pixel_size_presets" in loaded_raw:
            pixel_presets = PresetStorage._extract_pixel_presets(loaded_raw.get("pixel_size_presets"))
            crop_defaults = PresetStorage._normalize_crop_defaults(loaded_raw.get("crop_defaults"))
        else:
            # Backward-compatible format: plain dict of preset_name -> nm_per_pixel
            pixel_presets = PresetStorage._extract_pixel_presets(loaded_raw)
            crop_defaults = dict(DEFAULT_CROP_DEFAULTS)

        payload["pixel_size_presets"].update(pixel_presets)
        payload["crop_defaults"] = crop_defaults
        return payload

    @staticmethod
    def load_preset_payload() -> dict:
        """Load full preset payload including crop defaults."""
        payload = {
            "pixel_size_presets": dict(DEFAULT_PIXEL_PRESETS),
            "crop_defaults": dict(DEFAULT_CROP_DEFAULTS),
        }

        preset_file = PresetStorage.get_preset_file()
        candidate_files: list[Path] = [preset_file]
        if not preset_file.exists():
            candidate_files.extend(PresetStorage._legacy_preset_files())

        loaded_raw = None
        for candidate in candidate_files:
            if not candidate.exists():
                continue
            try:
                loaded_raw = PresetStorage.load_preset_payload_from_file(candidate)
                break
            except Exception as e:
                print(f"Error loading presets from {candidate}: {e}")

        if loaded_raw is None:
            return payload

        payload["pixel_size_presets"].update(
            PresetStorage._extract_pixel_presets(loaded_raw.get("pixel_size_presets", {}))
        )
        payload["crop_defaults"] = PresetStorage._normalize_crop_defaults(loaded_raw.get("crop_defaults", {}))
        return payload

    @staticmethod
    def import_presets_from_file(file_path: Path) -> dict:
        """Import presets from an external file and persist them as active payload."""
        payload = PresetStorage.load_preset_payload_from_file(file_path)
        PresetStorage.save_preset_payload(payload)
        return payload

    @staticmethod
    def save_preset_payload(payload: dict) -> None:
        """Save full preset payload to disk."""
        preset_file = PresetStorage.get_preset_file()
        PresetStorage.save_preset_payload_to_file(payload, preset_file)

    @staticmethod
    def save_preset_payload_to_file(payload: dict, file_path: Path) -> None:
        """Save full preset payload to an explicit file path."""
        data = {
            "pixel_size_presets": dict(DEFAULT_PIXEL_PRESETS),
            "crop_defaults": dict(DEFAULT_CROP_DEFAULTS),
        }
        data["pixel_size_presets"].update(
            PresetStorage._extract_pixel_presets(payload.get("pixel_size_presets", {}))
        )
        data["crop_defaults"] = PresetStorage._normalize_crop_defaults(payload.get("crop_defaults", {}))
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving presets: {e}")
            raise
    
    @staticmethod
    def load_presets() -> Dict[str, float]:
        """Load presets from JSON file."""
        payload = PresetStorage.load_preset_payload()
        presets = dict(DEFAULT_PIXEL_PRESETS)
        presets.update(PresetStorage._extract_pixel_presets(payload.get("pixel_size_presets", {})))
        return presets
    
    @staticmethod
    def save_presets(presets: Dict[str, float]):
        """Save presets to JSON file."""
        payload = PresetStorage.load_preset_payload()
        payload["pixel_size_presets"] = PresetStorage._extract_pixel_presets(presets)
        PresetStorage.save_preset_payload(payload)

    @staticmethod
    def load_crop_defaults() -> dict:
        """Load default top/bottom crop rows from preset payload."""
        payload = PresetStorage.load_preset_payload()
        return PresetStorage._normalize_crop_defaults(payload.get("crop_defaults", {}))

    @staticmethod
    def save_crop_defaults(top_rows: int, bottom_rows: int) -> None:
        """Persist default top/bottom crop rows into preset payload."""
        payload = PresetStorage.load_preset_payload()
        payload["crop_defaults"] = {
            "top_rows": max(0, int(top_rows)),
            "bottom_rows": max(0, int(bottom_rows)),
        }
        PresetStorage.save_preset_payload(payload)
