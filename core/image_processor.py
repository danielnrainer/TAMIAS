"""
Image processing module for TEM Image Editor.
Handles image loading, transformations, and brightness/contrast adjustments.
"""

import math
from typing import Optional, Tuple, Dict
import numpy as np
from PIL import Image
from pathlib import Path


class ImageProcessor:
    """Handles all image processing operations."""
    
    def __init__(self):
        self.original_image: Optional[np.ndarray] = None
        self.raw_image: Optional[np.ndarray] = None  # Store raw data before normalization
        self.current_image: Optional[np.ndarray] = None
        self.input_dpi: Optional[Tuple[float, float]] = None
        self.rod_header_info: Optional[Dict] = None  # .rodhypix header metadata
        self.file_pixel_size_nm: Optional[float] = None  # Direct-space pixel size from file header
        self.min_val = 0
        self.max_val = 255
        # Raw -> 8-bit display mapping: "Linear" (min-max), "Square root" or "Logarithmic"
        self.intensity_scaling = "Linear"
        # Affine map from as-loaded pixel coords to current (cropped/flipped) coords:
        # x_cur = sx * x_loaded + tx,  y_cur = sy * y_loaded + ty
        self._geom = (1.0, 0.0, 1.0, 0.0)
        
    def load_image(self, file_path: str) -> Tuple[bool, Optional[str], Optional[Tuple[int, int]]]:
        """
        Load an image from file.

        Returns:
            (success, error_message, (width, height))

        For .rodhypix files the direct-space pixel size is read from the header
        (see get_file_pixel_size_nm). TIFF and other formats carry no such calibration;
        use imaging-mode presets for those.
        """
        # Snapshot so a failed load leaves the image on screen (and its header/geometry) intact
        previous_state = (self.original_image, self.raw_image, self.current_image, self.input_dpi,
                          self.rod_header_info, self.file_pixel_size_nm, self._geom)
        try:
            file_ext = Path(file_path).suffix.lower()
            self.rod_header_info = None
            self.file_pixel_size_nm = None
            self._geom = (1.0, 0.0, 1.0, 0.0)

            # Check if it's a .rodhypix file
            if file_ext == '.rodhypix':
                from rodhypix import RODImageReader

                # Load using RODImageReader (auto backend: native C++/NumPy if available, else pure Python)
                reader = RODImageReader(file_path)
                self.original_image = reader.get_raw_data()
                self.raw_image = self.original_image.copy()

                self.rod_header_info = reader.get_header_info()

                # Direct-space pixel size (rodhypix >= 0.1.2); absent/zero/invalid -> None
                try:
                    size_nm = float(self.rod_header_info.get("direct_space_pixel_size_nm"))
                    if np.isfinite(size_nm) and size_nm > 0:
                        self.file_pixel_size_nm = size_nm
                except (TypeError, ValueError):
                    pass

                print(f"\nLoaded .rodhypix file")
                print(f"Decompression method: {reader.get_decompression_method()}")

                # No DPI information for rodhypix files
                self.input_dpi = None

            else:
                # Load image using PIL for standard formats
                pil_image = Image.open(file_path)
            # else:
            #     # Load image using PIL for standard formats
            #     pil_image = Image.open(file_path)
            
                # Try to capture source DPI metadata
                self.input_dpi = None
                try:
                    dpi = pil_image.info.get('dpi')
                    if dpi and isinstance(dpi, (tuple, list)) and len(dpi) == 2:
                        self.input_dpi = (float(dpi[0]), float(dpi[1]))
                    else:
                        # Some TIFFs store resolution differently
                        res = pil_image.info.get('resolution')
                        unit = pil_image.info.get('resolution_unit', 2)  # 2=inches, 3=cm
                        if res and isinstance(res, (tuple, list)) and len(res) == 2:
                            xres, yres = float(res[0]), float(res[1])
                            if unit == 3:  # cm -> inch
                                xres *= 2.54
                                yres *= 2.54
                            self.input_dpi = (xres, yres)
                        else:
                            # Fallback to TIFF tags if available
                            tag = getattr(pil_image, 'tag_v2', None)
                            if tag is not None:
                                xres = tag.get(282)  # XResolution
                                yres = tag.get(283)  # YResolution
                                unit_tag = tag.get(296)  # ResolutionUnit (2=in, 3=cm)
                                if xres and yres:
                                    xval = float(xres[0] / xres[1]) if isinstance(xres, (tuple, list)) else float(xres)
                                    yval = float(yres[0] / yres[1]) if isinstance(yres, (tuple, list)) else float(yres)
                                    if unit_tag == 3:  # cm
                                        xval *= 2.54
                                        yval *= 2.54
                                    self.input_dpi = (xval, yval)
                except Exception:
                    self.input_dpi = None
            
                # Convert to grayscale if needed
                if pil_image.mode not in ['L', 'I', 'I;16', 'F']:
                    pil_image = pil_image.convert('L')
            
                self.original_image = np.array(pil_image)
                self.raw_image = self.original_image.copy()  # Store raw data before normalization
            
            # Print diagnostic info
            print(f"Loaded image dtype: {self.original_image.dtype}")
            print(f"Image range: min={np.min(self.original_image):.2f}, max={np.max(self.original_image):.2f}")
            print(f"Image mean: {np.mean(self.original_image):.2f}")
            
            self._normalize_from_raw()
            
            print(f"After normalization: dtype={self.original_image.dtype}, range=[{np.min(self.original_image)}, {np.max(self.original_image)}]")
            
            self.current_image = self.original_image.copy()
            
            # Get dimensions
            height, width = self.original_image.shape
            
            return True, None, (width, height)

        except Exception as e:
            (self.original_image, self.raw_image, self.current_image, self.input_dpi,
             self.rod_header_info, self.file_pixel_size_nm, self._geom) = previous_state
            return False, str(e), None
    
    INTENSITY_SCALING_MODES = ("Linear", "Square root", "Logarithmic")

    def _normalize_from_raw(self):
        """(Re)build the 8-bit `original_image` from `raw_image` using `intensity_scaling`.

        Linear keeps the historical behaviour (8-bit data untouched, other dtypes min-max
        stretched). Square root / Logarithmic compress the dynamic range, which diffraction
        patterns need: the direct beam can be ~10^5 counts while reflections are ~10-100.
        """
        raw = self.raw_image
        if raw is None:
            return
        mode = self.intensity_scaling if self.intensity_scaling in self.INTENSITY_SCALING_MODES else "Linear"

        if mode == "Linear":
            if raw.dtype == np.uint8:
                self.original_image = raw.copy()
                return
            img_min = np.min(raw)
            img_max = np.max(raw)
            print(f"{raw.dtype} image detected, normalizing range [{img_min}, {img_max}] to [0, 255]")
            if img_max > img_min:
                normalized = (raw.astype(np.float64) - img_min) / (float(img_max) - float(img_min)) * 255.0
                self.original_image = normalized.astype(np.uint8)
            else:
                self.original_image = np.zeros(raw.shape, dtype=np.uint8)
            return

        data = raw.astype(np.float64)
        data -= np.min(data)  # >= 0 (also lifts masked pixels, e.g. -1 in .rodhypix)
        data = np.sqrt(data) if mode == "Square root" else np.log1p(data)
        top = float(np.max(data))
        if top > 0:
            self.original_image = (data / top * 255.0).astype(np.uint8)
        else:
            self.original_image = np.zeros(raw.shape, dtype=np.uint8)

    def set_intensity_scaling(self, mode: str) -> bool:
        """Change the raw -> display mapping and rebuild the display image.

        Returns True if the image was rebuilt. Brightness/contrast are kept; callers usually
        follow up with auto_adjust_contrast().
        """
        if mode not in self.INTENSITY_SCALING_MODES:
            return False
        self.intensity_scaling = mode
        if self.raw_image is None or self.original_image is None:
            return False
        if self.raw_image.shape != self.original_image.shape:
            return False
        self._normalize_from_raw()
        self.apply_brightness_contrast()
        return True

    # --- Geometry bookkeeping (crop / flip) ---------------------------------------------

    def map_loaded_to_current(self, x: float, y: float) -> Tuple[float, float]:
        """Map pixel-corner coords of the image as loaded to the current (cropped/flipped) image."""
        sx, tx, sy, ty = self._geom
        return (sx * float(x) + tx, sy * float(y) + ty)

    def map_current_to_loaded(self, x: float, y: float) -> Tuple[float, float]:
        """Inverse of map_loaded_to_current."""
        sx, tx, sy, ty = self._geom
        return ((float(x) - tx) / sx, (float(y) - ty) / sy)

    def _geom_translate(self, dx: float, dy: float):
        sx, tx, sy, ty = self._geom
        self._geom = (sx, tx + dx, sy, ty + dy)

    def refine_peak_centroid(self, x: float, y: float, search_radius: int = 15,
                             centroid_radius: int = 6, iterations: int = 3) -> Optional[Tuple[float, float]]:
        """Snap a point to the nearby intensity peak (e.g. the direct beam).

        Finds the brightest pixel of the raw data within `search_radius` of (x, y), then
        computes the background-subtracted intensity-weighted centroid within
        `centroid_radius`, re-centring the box on the previous centroid `iterations` times
        (avoids bias from a box centred on a noisy/saturated maximum). Result is in
        pixel-corner coordinates (pixel centre = index + 0.5). Returns None if there is no
        usable signal.
        """
        if not (math.isfinite(float(x)) and math.isfinite(float(y))):
            return None
        data = self.raw_image if self.raw_image is not None else self.original_image
        if data is None or self.original_image is None or data.shape != self.original_image.shape:
            return None
        h, w = data.shape
        cx, cy = int(math.floor(x)), int(math.floor(y))
        x0, x1 = max(0, cx - search_radius), min(w, cx + search_radius + 1)
        y0, y1 = max(0, cy - search_radius), min(h, cy + search_radius + 1)
        if x1 <= x0 or y1 <= y0:
            return None
        window = data[y0:y1, x0:x1].astype(np.float64)
        background = float(np.median(window))
        iy, ix = np.unravel_index(int(np.argmax(window)), window.shape)
        if window[iy, ix] - background <= 0:
            return None
        centre = (x0 + ix + 0.5, y0 + iy + 0.5)
        for _ in range(max(1, int(iterations))):
            px, py = int(math.floor(centre[0])), int(math.floor(centre[1]))
            a0, a1 = max(0, px - centroid_radius), min(w, px + centroid_radius + 1)
            b0, b1 = max(0, py - centroid_radius), min(h, py + centroid_radius + 1)
            patch = np.clip(data[b0:b1, a0:a1].astype(np.float64) - background, 0.0, None)
            total = float(patch.sum())
            if total <= 0:
                break
            yy, xx = np.mgrid[b0:b1, a0:a1]
            centre = (float((patch * (xx + 0.5)).sum() / total), float((patch * (yy + 0.5)).sum() / total))
        return centre

    def get_header_diffraction_geometry(self) -> Dict:
        """Diffraction calibration values found in the file header (see core.diffraction)."""
        from core.diffraction import resolve_header_geometry
        return resolve_header_geometry(self.rod_header_info)

    def auto_adjust_contrast(self):
        """Automatically adjust brightness/contrast based on image histogram."""
        if self.original_image is None:
            return
        
        # Calculate percentiles for auto-adjustment
        # Use more aggressive percentiles (0.1% and 99.9%) to better handle the normalized 8-bit data
        p_low = np.percentile(self.original_image, 0.1)
        p_high = np.percentile(self.original_image, 99.9)
        
        # Ensure min and max are different
        if p_high <= p_low:
            p_low = np.min(self.original_image)
            p_high = np.max(self.original_image)
        
        # Add some margin if the range is still too narrow
        range_val = p_high - p_low
        if range_val < 10:  # If range is very narrow
            mid = (p_high + p_low) / 2
            p_low = max(0, mid - 25)
            p_high = min(255, mid + 25)
        
        self.min_val = int(p_low)
        self.max_val = int(p_high)
        
        print(f"Auto-adjust: min={self.min_val}, max={self.max_val} (range={self.max_val - self.min_val})")
        
        self.apply_brightness_contrast()
    
    def set_brightness_contrast(self, min_val: int, max_val: int):
        """Set brightness/contrast values and apply."""
        self.min_val = min_val
        self.max_val = max_val
        self.apply_brightness_contrast()
    
    def apply_brightness_contrast(self):
        """Apply brightness/contrast adjustment to the image."""
        if self.original_image is None:
            return
        
        # Apply contrast stretching with proper input->output mapping
        # min_val and max_val define the INPUT range that gets mapped to 0-255 OUTPUT
        img = self.original_image.astype(np.float32)
        
        if self.max_val > self.min_val:
            # Map [min_val, max_val] input range to [0, 255] output range
            # Values below min_val -> black (0)
            # Values above max_val -> white (255)
            img = (img - self.min_val) / (self.max_val - self.min_val) * 255
            img = np.clip(img, 0, 255)
        
        self.current_image = img.astype(np.uint8)
    
    def reset_brightness_contrast(self):
        """Reset brightness/contrast to default."""
        self.min_val = 0
        self.max_val = 255
        if self.original_image is not None:
            self.current_image = self.original_image.copy()
    
    def flip_horizontal(self):
        """Flip the image horizontally (left-right)."""
        if self.original_image is None:
            return
        
        width = self.original_image.shape[1]
        if self.raw_image is not None and self.raw_image.shape == self.original_image.shape:
            self.raw_image = np.fliplr(self.raw_image)
        self.original_image = np.fliplr(self.original_image)
        sx, tx, sy, ty = self._geom
        self._geom = (-sx, float(width) - tx, sy, ty)  # x' = W - x
        self.apply_brightness_contrast()

    def flip_vertical(self):
        """Flip the image vertically (top-bottom)."""
        if self.original_image is None:
            return

        height = self.original_image.shape[0]
        if self.raw_image is not None and self.raw_image.shape == self.original_image.shape:
            self.raw_image = np.flipud(self.raw_image)
        self.original_image = np.flipud(self.original_image)
        sx, tx, sy, ty = self._geom
        self._geom = (sx, tx, -sy, float(height) - ty)  # y' = H - y
        self.apply_brightness_contrast()

    def crop_rows(self, top_rows: int, bottom_rows: int) -> Tuple[bool, Optional[str], Optional[Tuple[int, int]]]:
        """Crop rows from the top and bottom of the loaded image.

        Returns:
            (success, error_message, (width, height))
        """
        if self.original_image is None:
            return False, "No image loaded.", None

        top_rows = int(top_rows)
        bottom_rows = int(bottom_rows)
        if top_rows < 0 or bottom_rows < 0:
            return False, "Crop values must be non-negative.", None

        height, _width = self.original_image.shape
        remaining_height = height - top_rows - bottom_rows
        if remaining_height <= 0:
            return False, "Crop values remove all rows. Reduce top/bottom crop amounts.", None

        if top_rows == 0 and bottom_rows == 0:
            width = int(self.original_image.shape[1])
            return True, None, (width, int(height))

        start = top_rows
        end = height - bottom_rows
        self.original_image = self.original_image[start:end, :].copy()
        if self.raw_image is not None and self.raw_image.shape[0] == height:
            self.raw_image = self.raw_image[start:end, :].copy()
        self._geom_translate(0.0, -float(top_rows))
        self.apply_brightness_contrast()

        new_height, new_width = self.original_image.shape
        return True, None, (int(new_width), int(new_height))

    def crop_rectangle(
        self, left: int, top: int, right: int, bottom: int
    ) -> Tuple[bool, Optional[str], Optional[Tuple[int, int]]]:
        """Crop to a rectangular ROI using exclusive right/bottom bounds.

        Args:
            left: Left column index (inclusive)
            top: Top row index (inclusive)
            right: Right column index (exclusive)
            bottom: Bottom row index (exclusive)

        Returns:
            (success, error_message, (width, height))
        """
        if self.original_image is None:
            return False, "No image loaded.", None

        height, width = self.original_image.shape

        left = max(0, min(int(left), width))
        right = max(0, min(int(right), width))
        top = max(0, min(int(top), height))
        bottom = max(0, min(int(bottom), height))

        if right <= left or bottom <= top:
            return False, "Invalid crop rectangle. Select a non-empty region.", None

        self.original_image = self.original_image[top:bottom, left:right].copy()
        if self.raw_image is not None and self.raw_image.shape == (height, width):
            self.raw_image = self.raw_image[top:bottom, left:right].copy()
        self._geom_translate(-float(left), -float(top))
        self.apply_brightness_contrast()

        new_height, new_width = self.original_image.shape
        return True, None, (int(new_width), int(new_height))
    
    def get_current_image(self) -> Optional[np.ndarray]:
        """Get the current processed image."""
        return self.current_image
    
    def get_original_image(self) -> Optional[np.ndarray]:
        """Get the original image."""
        return self.original_image
    
    def has_image(self) -> bool:
        """Check if an image is loaded."""
        return self.current_image is not None
    
    def get_file_pixel_size_nm(self) -> Optional[float]:
        """Direct-space pixel size (nm/pixel) from the file header, or None if unavailable."""
        return self.file_pixel_size_nm

    def get_dpi(self) -> Optional[Tuple[float, float]]:
        """Get the input DPI if available."""
        return self.input_dpi
