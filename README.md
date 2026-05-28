# SynergyED Image Annotate

A PyQt6 desktop application for processing (mainly) Synergy-ED images with calibrated overlays, particle measurement tools, and batch annotation support.

## Features

- **Image Processing**: Load TIF/TIFF/RODHyPix images with automatic brightness/contrast adjustment
- **RODHyPix Support**: Native support for `.rodhypix` detector image files with automatic pixel size extraction
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
- **Batch Processing**: Process multiple images with consistent settings
- **Imaging Presets**: Store and manage pixel size calibrations for different imaging modes
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
git clone https://github.com/danielnrainer/SynergyED-img_annotate.git
cd SynergyED-img_annotate
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
python SynergyED-img_annotate.py
```

**Basic Workflow:**
1. Load an image (Ctrl+O)
2. Select imaging mode preset or enter pixel size manually
3. Adjust brightness/contrast (Auto Adjust recommended)
4. Configure scalebar settings (length, position, colors)
5. Optionally add particle measurements:
  - Enable **Particle Measurement**
  - Click **✏ Draw Measurement** and drag
  - Use **↔ Move Line** to reposition a line
  - Use **☰ Move Label** to reposition labels
  - Select one or more rows in the measurement table to edit selected styles together
6. Export image (Ctrl+S)

**Batch Processing:**
- File → Batch Annotate (Ctrl+B)
- Add images, configure settings, and process all at once

## Project Structure

```
SynergyED-img_annotate/
├── core/                       # Core processing modules
│   ├── image_processor.py     # Image loading and adjustments
│   └── overlay_renderer.py    # Scalebar, aperture and measurement rendering
├── gui/                       # GUI components
│   └── collapsible_box.py    # Collapsible section widget
├── utils/                     # Utility modules
│   └── preset_manager.py     # Preset storage and management
├── SynergyED-img_annotate.py # Main application entry point
├── requirements.txt           # Python dependencies
└── pixelsize_presets.json    # Pixel size presets
```

## Requirements

- Python 3.8+
- PyQt6 >= 6.5, < 7
- NumPy >= 1.24, < 3
- Pillow >= 10, < 13
- PyInstaller >= 6.0 (for building executables)

### Optional Dependencies

- **numba** >= 0.60.0 (recommended for `.rodhypix` files)
  - Provides ~10x speedup for RODHyPix decompression
  - Install with: `pip install numba`

## Technical Details

- **Image Processing**: 8-bit grayscale (16-bit images auto-normalized)
- **Scalebar Calculation**: Accounts for nm/pixel calibration
- **RODHyPix Support**: 
  - Native reader adapted from [cap-auto](https://github.com/robertbuecker/cap-auto) (BSD 3-Clause)
  - Automatic pixel size extraction from file header
  - Supports TY6 compressed format
  - Optimized with Numba JIT compilation when available
  - Pure Python fallback for compatibility
- **Architecture**: Modular design with separate core, GUI, and utility modules
- **UI**: Collapsible sections for efficient screen space management
- **Particle Measurement**: Click-and-drag lines with auto-computed length labels; per-measurement line/text styles, cap styles, width, and label visibility; label positions stored as per-measurement image-pixel offsets and fully repositionable via drag

## Acknowledgments

- RODHyPix image reader adapted from [cap-auto](https://github.com/robertbuecker/cap-auto) by Robert Bücker (BSD 3-Clause)
  - Original dxtbx code by David Waterman & Takanori Nakane
  - Copyright: 2018-2023 United Kingdom Research and Innovation & 2022-2023 Takanori Nakane

## Building Executable

Create a standalone executable with PyInstaller:
```bash
pyinstaller SynergyED-img_annotate.spec
```

## License

BSD 3-Clause License - see [LICENSE](LICENSE) file for details.

## Author

Daniel N. Rainer (ORCID: 0000-0002-3272-3161)

Project Link: [https://github.com/danielnrainer/SynergyED-img_annotate](https://github.com/danielnrainer/SynergyED-img_annotate)
