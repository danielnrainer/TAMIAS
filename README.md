# TAMIAS

Tool for Annotation and Markup of Images from a Synergy-ED

A PyQt6 desktop application for annotating and marking up real space images with calibrated overlays, crop controls, particle measurement tools, and batch processing support. Its main use is for images acquired on a Rigaku XtaLAB Synergy-ED, but can in principle be used for images from other instruments too.


_Disclaimer_\
The code in this project has been written in large parts by Anthropic and OpenAI LLM models.


*Be advised that this software is in constant development and might therefore contain bugs or other unintended behaviour.
If you encounter any issue and would like to report it or have a feature request, please do so via the [Issues](https://github.com/danielnrainer/TAMIAS/issues) section.*

## Features

- **Image Processing**: Load TIF/TIFF/RODHyPix images with automatic brightness/contrast adjustment
- **RODHyPix Support**: Native support for `.rodhypix` detector image files with automatic pixel size extraction
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
- **Imaging Presets**: Store and manage pixel size calibrations for different imaging modes
- **Persistent Settings**: Theme, window size, annotation defaults, preset defaults, and file-dialog folders are retained between sessions
- **Preset Import/Export**: Load preset JSON files from other machines and save current presets back out to file
- **Compact UI**: Laptop-friendly interface with collapsible sections and scrollable controls
- **Multiple Export Formats**: PNG, TIFF, JPEG

## Supported File Formats

- **TIFF** (`.tif`, `.tiff`) - Standard microscopy format
- **RODHyPix** (`.rodhypix`) - Rigaku Oxford Diffraction native format
  - Automatically extracts pixel size from file header
  - Supports Numba acceleration for faster loading (~10x speedup)
  - Pure Python fallback if Numba is not installed
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

3. **(Optional)** Install Numba for faster RODHyPix file loading:
```bash
pip install numba
```
  This provides ~10x speedup when loading `.rodhypix` files. The application works without it using pure Python decompression.

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
- `Select Theme`
- `Open Settings Folder`

**Basic Workflow:**
1. Load an image (Ctrl+O)
2. Select imaging mode preset or enter pixel size manually
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
├── core/                       # Core processing modules
│   ├── crop_geometry.py       # Crop geometry helpers
│   ├── image_processor.py     # Image loading and adjustments
│   └── overlay_renderer.py    # Scalebar, aperture and measurement rendering
├── gui/                       # GUI components
│   ├── batch_processing_dialog.py # Batch processing dialog
│   ├── collapsible_box.py     # Collapsible section widget
│   ├── crop_controller.py     # Crop interaction/controller mixin
│   └── crop_dialog.py         # Top/bottom crop dialog
├── utils/                     # Utility modules
│   ├── app_settings_manager.py # Persistent app settings storage
│   ├── preset_manager.py      # Preset storage and management
│   └── storage_paths.py       # Per-user app-data path helpers
├── TAMIAS.py                  # Main application entry point
├── TAMIAS.spec                # PyInstaller build specification
├── requirements.txt           # Python dependencies
├── pixelsize_presets.json     # Legacy preset fallback data
├── tamias.ico                 # Application icon
└── tamias.png                 # About dialog logo
```

## Requirements

- Python 3.8+
- PyQt6 >= 6.5, < 7
- NumPy >= 1.24, < 3
- Pillow >= 10, < 13
- PyInstaller >= 6.0, < 7 (for building executables)

### Optional Dependencies

- **numba** >= 0.60, < 1 (recommended for `.rodhypix` files)
  - Provides ~10x speedup for RODHyPix decompression
  - Install with: `pip install numba`

## Technical Details

- **Image Processing**: 8-bit grayscale (16-bit images auto-normalized)
- **Cropping**: Top/bottom row crop and interactive manual crop are available before overlay rendering
- **Scalebar Calculation**: Accounts for nm/pixel calibration
- **RODHyPix Support**: 
  - Native reader adapted from [cap-auto](https://github.com/robertbuecker/cap-auto) (BSD 3-Clause)
  - Automatic pixel size extraction from file header
  - Supports TY6 compressed format
  - Optimized with Numba JIT compilation when available
  - Pure Python fallback for compatibility
- **Architecture**: Modular design with separate core, GUI, and utility modules, with crop and batch workflows split into dedicated modules
- **UI**: Collapsible sections and scrollable batch controls for efficient screen space management
- **Particle Measurement**: Click-and-drag lines with auto-computed length labels; per-measurement line/text styles, cap styles, width, and label visibility; label positions stored as per-measurement image-pixel offsets and fully repositionable via drag

## Acknowledgments

- RODHyPix image reader adapted from [cap-auto](https://github.com/robertbuecker/cap-auto) by Robert Bücker (BSD 3-Clause)
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
