# TAMIAS

Tool for Annotation and Markup of Images from a Synergy-ED

A PyQt6 desktop application for annotating and marking up real space images with calibrated overlays, crop controls, particle measurement tools, and batch processing support. Its main use is for images acquired on a Rigaku XtaLAB Synergy-ED, but can in principle be used for images from other instruments too.


_Disclaimer_\
The code in this project has been written in large parts by Anthropic and OpenAI LLM models.


*Be advised that this software is in constant development and might therefore contain bugs or other unintended behaviour.
If you encounter any issue and would like to report it or have a feature request, please do so via the [Issues](https://github.com/danielnrainer/TAMIAS/issues) section.*

## Features

- **Image Processing**: Load TIF/TIFF/RODHyPix images with automatic brightness/contrast adjustment
- **RODHyPix Support**: Native support for `.rodhypix` image files, including automatic direct-space pixel size calibration read from the file header where available (recommended over TIFF)
- **Cropping Tools**: Batch top/bottom row crop plus interactive manual crop with square/aspect controls and drag/move support
- **Smart Scalebars**: Calibrated scalebars with customizable appearance (length, thickness, position, colors, font, background box)
- **Aperture Overlay**: Visualize SAED aperture sizes on images
- **Particle Measurement**: Draw and annotate dimensions directly on the image with per-measurement style control
  - Draw measurement lines
  - Move full lines
  - Move labels independently
  - Configure per-measurement line width, start/end cap style, label visibility, line color, and text color
  - Multi-select rows and edit selected measurements in one action
  - Apply current style to selected rows or to all rows
- **Measurement Property Table**: Measurements are listed in a multi-column table (length, style, caps, colors, labels)
- **Clickable Color Swatches**: Color swatches are shown in measurement rows and beside color-picker buttons for quick visual feedback
- **Theme Support**: Light, dark, and auto (system) theme modes
- **Resizable Workspace**: Adjustable splitter between image pane and control pane
- **Batch Processing**: Dedicated dialog with scrollable collapsible sections, applied/not-applied status markers, and crop/overlay/export settings
- **Imaging Presets**: Store and manage pixel size calibrations for different imaging modes (fallback for files without a header pixel size, e.g. TIFF)
- **Persistent Settings**: Theme, window size, annotation defaults, preset defaults, and file-dialog folders are retained between sessions
- **Preset Import/Export**: Load preset JSON files from other machines and save current presets back out to file
- **Compact UI**: Laptop-friendly interface with collapsible sections and scrollable controls
- **Multiple Export Formats**: PNG, TIFF, JPEG

## Supported File Formats

- **RODHyPix** (`.rodhypix`) - Rigaku Oxford Diffraction native format
  - Direct-space pixel size is read from the file header, so no preset is needed for images that contain it
  - *Not every image carries it*: with CrysAlisPro v45.96 (and earlier), post-experiment images might not store a pixel size, so an imaging preset must be selected for those (see below)
  - Read via the [rodhypix](https://pypi.org/project/rodhypix/) package, using its native C++/NumPy backend when available (falls back to pure Python)
- **TIFF** (`.tif`, `.tiff`) - Standard image format; might not carry pixel size calibration, so preset is required
- **PNG** (`.png`)
- **JPEG** (`.jpg`, `.jpeg`)
- **BMP** (`.bmp`)

## Quick Start

### Installation

1. Clone the repository:
```bash
git clone https://github.com/danielnrainer/TAMIAS.git
cd TAMIAS
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```
  This includes [rodhypix](https://pypi.org/project/rodhypix/), which provides `.rodhypix` file support with a native C++/NumPy backend on supported platforms and a pure Python fallback elsewhere.

### Usage

Run the application:
```bash
python TAMIAS.py
```

### App Data and Settings

TAMIAS stores user-specific data in `%APPDATA%/TAMIAS` on Windows.

- `settings.json` stores theme mode, window geometry, splitter sizes, annotation defaults, and remembered folders.
- `presets.json` stores imaging presets and default top/bottom crop values.

You can access these from the application via `Settings`:

- `Manage Presets...`
- `Load Presets from File...`
- `Save Presets to File...`
- `Restore Presets to TAMIAS Defaults`
- `Restore App Settings to TAMIAS Defaults`
- `Select Theme`
- `Open Settings Folder`

Shipped defaults are defined in repository JSON resources:

- `presets_defaults.json` for preset/crop defaults
- `settings_defaults.json` for app settings defaults

At runtime, user-specific files in `%APPDATA%/TAMIAS` override these shipped defaults.

**Basic Workflow:**
1. Load an image (Ctrl+O)
2. Leave the imaging mode on **Auto (from file)** to use the pixel size stored in `.rodhypix` files. If the file has none (TIFF and other formats, and `.rodhypix` post-experiment images), TAMIAS switches to the `Standard` preset - **check that this matches the imaging mode used and select the correct preset or enter a pixel size via Custom if not**
3. Adjust brightness/contrast (Auto Adjust recommended)
4. Optionally crop away top/bottom rows or use the manual crop tool for a custom selection
5. Configure scalebar settings (length, position, colors)
6. Add overlay of selected-area aperture (calibrated sizes)
7. Optionally add particle measurements:
  - Enable **Particle Measurement**
  - Click **✏ Draw Measurement** and drag
  - Use **↔ Move Line** to reposition a line
  - Use **☰ Move Label** to reposition labels
  - Select one or more rows in the measurement table to edit selected styles together
8. Export image (Ctrl+S)

**Batch Processing:**
- File → Batch Processing (Ctrl+B)
- Add images, configure crop/overlay/export settings, and process all at once

## Project Structure

```
TAMIAS/
├── core/                           # Core processing modules
│   ├── crop_geometry.py            # Crop geometry helpers
│   ├── image_processor.py          # Image loading and adjustments
│   └── overlay_renderer.py         # Scalebar, aperture and measurement rendering
├── gui/                            # GUI components
│   ├── app_state_manager.py        # Main-window UI state orchestration
│   ├── batch_processing_dialog.py  # Batch processing dialog
│   ├── collapsible_box.py          # Collapsible section widget
│   ├── custom_widgets.py           # Shared custom widgets and UI helpers
│   ├── crop_controller.py          # Crop interaction/controller mixin
│   ├── crop_dialog.py              # Top/bottom crop dialog
│   ├── measurement_interaction.py  # Measurement draw/drag interaction controller
│   ├── theme_manager.py            # Theme application and OS sync
│   └── ui_sections.py              # Extracted setup-section builders for main UI
├── utils/                          # Utility modules
│   ├── app_settings_manager.py     # Persistent app settings storage
│   ├── imaging_mode_defaults.py    # Defaults for unit and scalebar length for each image mode
│   ├── preset_manager.py           # Preset storage and management
│   └── storage_paths.py            # Per-user app-data path helpers
├── TAMIAS.py                       # Main application entry point
├── TAMIAS.spec                     # PyInstaller build specification
├── requirements.txt                # Python dependencies
├── presets_defaults.json           # Shipped preset/crop defaults
├── settings_defaults.json          # Shipped app settings defaults
├── tamias.ico                      # Application icon
└── tamias.png                      # About dialog logo
```

## Requirements

- Python 3.8+
- PyQt6 >= 6.5, < 7
- NumPy >= 1.24, < 3
- Pillow >= 10, < 13
- PyInstaller >= 6.0, < 7 (for building executables)
- rodhypix >= 0.1.3, < 0.2 (for `.rodhypix` file support)

## Technical Details

- **Image Processing**: 8-bit grayscale (16-bit images auto-normalized)
- **Cropping**: Top/bottom row crop and interactive manual crop are available before overlay rendering
- **Scalebar Calculation**: Accounts for nm/pixel calibration
- **RODHyPix Support**:
  - Read via the [rodhypix](https://pypi.org/project/rodhypix/) package (BSD 3-Clause)
  - Direct-space pixel size (`direct_space_pixel_size_nm`) read from the file header; used by the **Auto (from file)** imaging mode. If a file has no valid value (stored as 0), the imaging mode switches to the `Standard` preset automatically (and back to Auto when the next file has a header value, unless a preset was chosen manually)
  - Known limitation: as of CrysAlisPro v45.96, post-experiment images do not contain the direct-space pixel size (the header field is 0), so they always use the preset fallback; the preset may differ from the actual imaging mode, so select it manually
  - In batch mode, Auto uses each file's own header pixel size; files without one use the batch dialog's **Fallback preset** (default Standard). The pixel size field is only editable when the selected (or fallback) preset is Custom
- **Architecture**: Modular design with separate core, GUI, and utility modules, with crop and batch workflows split into dedicated modules
- **UI**: Collapsible sections and scrollable batch controls for efficient screen space management
- **Particle Measurement**: Click-and-drag lines with auto-computed length labels; per-measurement line/text styles, cap styles, width, and label visibility; label positions stored as per-measurement image-pixel offsets and fully repositionable via drag

## Acknowledgments

- RODHyPix file support provided by the [rodhypix](https://pypi.org/project/rodhypix/) package by Robert Bücker (BSD 3-Clause)
  - Original dxtbx code by David Waterman & Takanori Nakane
  - Copyright: 2018-2023 United Kingdom Research and Innovation & 2022-2023 Takanori Nakane



## Building Executable

Create a standalone executable with PyInstaller:
```bash
pyinstaller TAMIAS.spec
```


## License

BSD 3-Clause License - see [LICENSE](LICENSE) file for details.

## Author

Daniel N. Rainer (ORCID: [0000-0002-3272-3161](https://orcid.org/0000-0002-3272-3161))

## Citation

If TAMIAS contributes to your work, please cite it via Zenodo:

- Zenodo DOI: [https://doi.org/10.5281/zenodo.20403971](https://doi.org/10.5281/zenodo.20403971)
- Project Repository: [https://github.com/danielnrainer/TAMIAS](https://github.com/danielnrainer/TAMIAS)
