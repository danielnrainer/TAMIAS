# SynergyED Image Annotate

A PyQt6-based desktop application for processing (mainly) Synergy-ED images with scalebars, aperture overlays, and batch processing capabilities.
A PyQt6-based desktop application for processing (mainly) Synergy-ED images with scalebars, aperture overlays, particle measurements, and batch processing capabilities.

## Features

- **Image Processing**: Load TIF/TIFF/RODHyPix images with automatic brightness/contrast adjustment
- **RODHyPix Support**: Native support for `.rodhypix` detector image files with automatic pixel size extraction
- **Smart Scalebars**: Calibrated scalebars with customizable appearance (length, thickness, position, colors, font)
- **Aperture Overlay**: Visualize SAED aperture sizes on images
- **Particle Measurement**: Draw and annotate dimension measurements directly on the image — supports multiple measurements, drag-to-draw, movable labels, and configurable arrow/text styling
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
5. Optionally add particle measurements: enable **Particle Measurement**, click **✏ Draw Measurement** and drag; use **☰ Move Label** to reposition labels
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
- PyQt6 >= 6.10.0
- NumPy >= 2.3.4
- Pillow >= 12.0.0

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
- **Particle Measurement**: Click-and-drag double-headed arrows with auto-computed length labels; multiple annotations supported simultaneously; label positions stored as per-measurement image-pixel offsets and fully repositionable via drag

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
