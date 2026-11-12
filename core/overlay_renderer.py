"""
Overlay rendering module for TEM Image Editor.
Handles drawing scalebar, aperture, and measurement overlays on images.
"""

from typing import Optional
import math
import numpy as np
from qtpy.QtGui import QImage, QPainter, QPen, QBrush, QColor, QFont
from qtpy.QtCore import Qt, QRectF, QPointF

from core.diffraction import (
    D_SPACING_ANGSTROM,
    DEFAULT_RING_RESOLUTIONS,
    RECIPROCAL_ANGSTROM,
    DiffractionGeometry,
    format_reciprocal_value,
    format_resolution_label,
    format_resolution_value,
    inv_angstrom_to_unit,
    reciprocal_to_inv_angstrom,
)


def qimage_to_rgba_array(q_image: QImage) -> np.ndarray:
    """Return a copy of ``q_image`` as an (H, W, 4) uint8 RGBA array.

    Works with both Qt bindings: PyQt6's ``QImage.bits()`` returns a
    ``sip.voidptr`` that must be sized with ``setsize()``, whereas PySide6
    returns an already-sized ``memoryview`` without that method.
    """
    q_rgba = q_image.convertToFormat(QImage.Format.Format_RGBA8888)
    width = q_rgba.width()
    height = q_rgba.height()
    bytes_per_line = q_rgba.bytesPerLine()
    ptr = q_rgba.bits()
    if hasattr(ptr, "setsize"):
        ptr.setsize(height * bytes_per_line)
    buf = np.frombuffer(ptr, np.uint8, count=height * bytes_per_line)
    return buf.reshape((height, bytes_per_line))[:, : width * 4].reshape((height, width, 4)).copy()


class OverlayRenderer:
    """Handles rendering of scalebar, aperture, and measurement overlays."""
    
    def __init__(self):
        # Scalebar parameters
        self.scalebar_enabled = True
        self.scalebar_length_value = 100.0  # numeric value (in selected unit)
        self.scalebar_unit = "nm"
        self.scalebar_thickness = 15
        self.scalebar_position = "bottom-right"
        self.bar_color = QColor(255, 255, 255)
        self.text_color = QColor(255, 255, 255)
        self.scalebar_font = QFont("Arial", 20, QFont.Weight.Black)
        self.scalebar_bg_enabled = True
        self.scalebar_bg_color = QColor(0, 0, 0)
        self.scalebar_bg_opacity = 255
        self.scalebar_offset: tuple[float, float] = (0.0, 0.0)  # image-pixel offset from anchor preset
        # Optional label override (numeric text only, without unit). If set, we'll display it verbatim.
        self.scalebar_label_override: Optional[str] = None
        
        # Reciprocal-space scalebar (diffraction mode); kept separate from the real-space
        # unit/length so switching image type restores each mode's own settings.
        self.recip_scalebar_unit = RECIPROCAL_ANGSTROM
        self.recip_scalebar_length_value = 0.5

        # Resolution rings (diffraction mode). Each entry: {"d": float (Å), "enabled": bool}
        self.rings_enabled = False
        self.ring_resolutions: list = [{"d": float(d), "enabled": True} for d in DEFAULT_RING_RESOLUTIONS]
        self.ring_color = QColor(0, 255, 255)
        self.ring_line_width = 2
        self.ring_show_labels = True
        self.ring_font = QFont("Arial", 14, QFont.Weight.Bold)
        self.beam_center_marker_enabled = False

        # Aperture parameters
        self.aperture_enabled = False
        self.aperture_nominal_size = 100  # diameter in µm
        self.aperture_color = QColor(255, 255, 0)

        # Measurement annotation parameters
        self.measurement_enabled = False
        self.measurements: list = []           # list of {"start": (x,y), "end": (x,y), "label_offset": (dx,dy)}
        self.measurement_preview: Optional[dict] = None  # in-progress drag
        self.measurement_unit = "nm"
        self.recip_measurement_unit = D_SPACING_ANGSTROM  # resolution read-out by default
        self.measurement_line_color= QColor(0, 255, 0)
        self.measurement_text_color = QColor(0, 255, 0)
        self.measurement_show_label = True
        self.measurement_line_width = 4
        self.measurement_start_cap = "head"
        self.measurement_end_cap = "head"
        self.measurement_font = QFont("Arial", 16, QFont.Weight.Bold)
    
    def render_image_with_overlays(self, 
                                   image: np.ndarray, 
                                   nm_per_pixel: float,
                                   diffraction: Optional[DiffractionGeometry] = None) -> Optional[QImage]:
        """
        Render image with scalebar and aperture overlays.

        Args:
            image: The numpy array image to render
            nm_per_pixel: Calibration in nanometers per pixel (real-space images)
            diffraction: If given, the image is a diffraction pattern (reciprocal space):
                scalebar in reciprocal units, resolution rings instead of the aperture,
                measurements in reciprocal space.
            
        Returns:
            QImage with overlays drawn, or None if image is invalid
        """
        if image is None:
            return None
        
        # Prepare RGB image for painting
        if len(image.shape) == 2:
            # Convert grayscale to RGB using NumPy
            rgb = np.stack([image, image, image], axis=-1)
        else:
            # Already RGB/color
            rgb = image
        
        # Ensure contiguous memory layout
        rgb = np.ascontiguousarray(rgb)
        height, width = rgb.shape[:2]
        bytes_per_line = rgb.strides[0]
        
        # Create QImage
        qimg = QImage(rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        qimg = qimg.copy().convertToFormat(QImage.Format.Format_ARGB32)
        
        if diffraction is not None:
            if not diffraction.is_valid():
                return qimg
            if self.rings_enabled:
                self._draw_resolution_rings(qimg, width, height, diffraction)
            if self.beam_center_marker_enabled:
                self._draw_beam_center_marker(qimg, diffraction)
            if self.scalebar_enabled:
                self._draw_scalebar(qimg, width, height, nm_per_pixel, diffraction)
            if self.measurement_enabled:
                self._draw_measurement(qimg, width, height, nm_per_pixel, diffraction)
            return qimg

        # Guard against invalid calibration
        if nm_per_pixel is None or nm_per_pixel <= 0:
            return qimg

        # Draw scalebar
        if self.scalebar_enabled:
            self._draw_scalebar(qimg, width, height, nm_per_pixel)
        
        # Draw aperture if enabled
        if self.aperture_enabled:
            self._draw_aperture(qimg, width, height, nm_per_pixel)

        # Draw particle measurement annotation if enabled
        if self.measurement_enabled:
            self._draw_measurement(qimg, width, height, nm_per_pixel)
        
        return qimg
    
    def _draw_scalebar(self, qimg: QImage, width: int, height: int, nm_per_pixel: float,
                       diffraction: Optional[DiffractionGeometry] = None):
        """Draw scalebar on the image."""
        layout = self._compute_scalebar_layout(width, height, nm_per_pixel, diffraction)
        if layout is None:
            return

        x = layout["bar_x"]
        y = layout["bar_y"]
        scalebar_length_px = layout["bar_length_px"]
        text_x = layout["text_x"]
        text_baseline_y = layout["text_baseline_y"]
        label = layout["label"]
        rect_left = layout["box_left"]
        rect_top = layout["box_top"]
        rect_right = layout["box_right"]
        rect_bottom = layout["box_bottom"]

        # Determine colors
        bar_qcolor = QColor(self.bar_color)
        text_qcolor = QColor(self.text_color)

        # Compute outline color for text contrast
        r, g, b, *_ = text_qcolor.getRgb()
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        outline_qcolor = QColor(0, 0, 0) if luminance > 0.5 else QColor(255, 255, 255)

        # Start painting
        painter = QPainter(qimg)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Font setup
        try:
            if isinstance(self.scalebar_font, QFont):
                painter.setFont(self.scalebar_font)
            else:
                painter.setFont(QFont("Arial", 20))
        except Exception:
            painter.setFont(QFont("Arial", 20))

        # Optional background box
        if self.scalebar_bg_enabled:
            bg = QColor(self.scalebar_bg_color)
            bg.setAlpha(self.scalebar_bg_opacity)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(bg))
            painter.drawRect(
                int(rect_left),
                int(rect_top),
                max(1, int(rect_right - rect_left)),
                max(1, int(rect_bottom - rect_top)),
            )

        # Draw scalebar rectangle
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bar_qcolor))
        painter.drawRect(QRectF(float(x), float(y), float(scalebar_length_px), float(self.scalebar_thickness)))

        # Draw text with outline
        pen = QPen(outline_qcolor)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawText(text_x, text_baseline_y, label)

        # Foreground text
        painter.setPen(QPen(text_qcolor))
        painter.drawText(text_x, text_baseline_y, label)

        painter.end()

    def _compute_scalebar_layout(self, width: int, height: int, nm_per_pixel: float,
                                 diffraction: Optional[DiffractionGeometry] = None) -> Optional[dict]:
        """Compute scalebar geometry (bar, text, and union box) in image pixel coordinates."""
        if width <= 0 or height <= 0:
            return None

        if diffraction is not None:
            # Reciprocal-space scalebar: linear calibration p/(λL) at the beam centre.
            if not diffraction.is_valid():
                return None
            inv_a_per_px = diffraction.inv_angstrom_per_pixel()
            unit_text = self.recip_scalebar_unit
            default_value = float(self.recip_scalebar_length_value)
            length_inv_a = reciprocal_to_inv_angstrom(default_value, unit_text)
            desired_px = length_inv_a / inv_a_per_px
        else:
            if nm_per_pixel is None or nm_per_pixel <= 0:
                return None
            # Compute scalebar length in pixels
            if self.scalebar_unit == "µm":
                length_nm = self.scalebar_length_value * 1000.0
            else:
                length_nm = float(self.scalebar_length_value)
            desired_px = length_nm / nm_per_pixel
            unit_text = "µm" if self.scalebar_unit == "µm" else "nm"
            default_value = length_nm / 1000.0 if self.scalebar_unit == "µm" else length_nm

        # Sub-pixel bar length (rounding to whole pixels would cost up to ±0.5 px of calibration).
        if not math.isfinite(desired_px) or desired_px <= 0:
            return None

        # Keep preset anchors close to image borders while preserving room to draw.
        anchor_margin = 15
        max_px = max(1, width - 2 * anchor_margin)
        if desired_px > max_px and diffraction is not None:
            # A clamped bar would no longer match its label; draw nothing rather than a wrong scale.
            return None
        # Real space keeps the historical behaviour (bar clamped to the image width).
        scalebar_length_px = float(min(desired_px, max_px))
        
        # Determine position
        if "bottom" in self.scalebar_position:
            y = height - anchor_margin - self.scalebar_thickness
        else:
            y = anchor_margin
        
        # Horizontal anchor is resolved after text metrics are known so we can
        # keep a consistent border distance for the wider of (bar, label).
        x = 0
        
        # Build label
        if self.scalebar_label_override is not None and str(self.scalebar_label_override).strip() != "":
            label_value_text = str(self.scalebar_label_override).strip()
        else:
            # Default formatting if no override provided
            value = default_value
            # Show integerif it's effectively an integer; otherwise, show up to 2 decimals without trailing zeros
            if abs(value - round(value)) < 1e-9:
                label_value_text = f"{int(round(value))}"
            else:
                label_value_text = f"{value:.2f}".rstrip('0').rstrip('.')
        label = f"{label_value_text} {unit_text}"

        # Measure text using current scalebar font
        tmp_img = QImage(1, 1, QImage.Format.Format_ARGB32)
        painter = QPainter(tmp_img)
        try:
            if isinstance(self.scalebar_font, QFont):
                painter.setFont(self.scalebar_font)
            else:
                painter.setFont(QFont("Arial", 20))
        except Exception:
            painter.setFont(QFont("Arial", 20))
        fm = painter.fontMetrics()
        text_advance = fm.horizontalAdvance(label)
        # Use tight bounds so layout remains stable across different fonts.
        tight = fm.tightBoundingRect(label)
        text_left_bearing = float(tight.x())
        text_top_offset = float(tight.y())
        text_width = float(tight.width())
        text_height = float(tight.height())
        text_bottom_offset = text_top_offset + text_height
        painter.end()

        # Text position
        text_bar_gap = max(8.0, float(self.scalebar_thickness) * 0.8)
        box_padding = max(6.0, text_bar_gap * 0.6)
        bar_top = float(y)
        bar_bottom = float(y + self.scalebar_thickness)
        if "bottom" in self.scalebar_position:
            # Keep the text block above the bar with a fixed gap.
            text_baseline_y = bar_top - text_bar_gap - text_bottom_offset
        else:
            # Keep the text block below the bar with a fixed gap.
            text_baseline_y = bar_bottom + text_bar_gap - text_top_offset

        text_top = text_baseline_y + text_top_offset
        text_bottom = text_baseline_y + text_bottom_offset

        # Resolve horizontal anchor based on the full content span (bar + label),
        # so defaults stay consistently padded even when text is wider than bar.
        left_rel = min(
            0.0,
            (float(scalebar_length_px) - float(text_advance)) / 2.0 + text_left_bearing,
        )
        right_rel = max(
            float(scalebar_length_px),
            (float(scalebar_length_px) - float(text_advance)) / 2.0 + text_left_bearing + text_width,
        )
        if "right" in self.scalebar_position:
            x = int(round((float(width) - float(anchor_margin) - box_padding) - right_rel))
        else:
            x = int(round((float(anchor_margin) + box_padding) - left_rel))

        # Center label over bar using the final bar anchor.
        text_x = float(x) + (float(scalebar_length_px) - float(text_advance)) / 2.0

        text_left = text_x + text_left_bearing
        text_right = text_left + text_width

        # Union box around bar + label (used for optional background and drag hitbox).
        rect_left = min(float(x), text_left) - box_padding
        rect_right = max(float(x + scalebar_length_px), text_right) + box_padding
        rect_top = min(bar_top, text_top) - box_padding
        rect_bottom = max(bar_bottom, text_bottom) + box_padding

        # Apply user drag offset and keep the whole box inside the image bounds.
        offset_x = float(self.scalebar_offset[0])
        offset_y = float(self.scalebar_offset[1])

        x = int(round(float(x) + offset_x))
        y = int(round(float(y) + offset_y))
        text_x = float(text_x + offset_x)
        text_baseline_y = float(text_baseline_y + offset_y)
        rect_left = float(rect_left + offset_x)
        rect_right = float(rect_right + offset_x)
        rect_top = float(rect_top + offset_y)
        rect_bottom = float(rect_bottom + offset_y)

        shift_x = 0.0
        shift_y = 0.0
        if rect_left < 0:
            shift_x = -rect_left
        elif rect_right > (width - 1):
            shift_x = (width - 1) - rect_right

        if rect_top < 0:
            shift_y = -rect_top
        elif rect_bottom > (height - 1):
            shift_y = (height - 1) - rect_bottom

        x = int(round(x + shift_x))
        y = int(round(y + shift_y))
        text_x = float(text_x + shift_x)
        text_baseline_y = float(text_baseline_y + shift_y)
        rect_left += shift_x
        rect_right += shift_x
        rect_top += shift_y
        rect_bottom += shift_y

        return {
            "bar_x": x,
            "bar_y": y,
            "bar_length_px": float(scalebar_length_px),
            "text_x": int(round(text_x)),
            "text_baseline_y": int(round(text_baseline_y)),
            "label": label,
            "box_left": float(max(0.0, rect_left)),
            "box_top": float(max(0.0, rect_top)),
            "box_right": float(min(float(width - 1), rect_right)),
            "box_bottom": float(min(float(height - 1), rect_bottom)),
        }

    def scalebar_fits(self, width: int, height: int, nm_per_pixel: float,
                      diffraction: Optional[DiffractionGeometry] = None) -> bool:
        """False when the scalebar is enabled but cannot be drawn (e.g. longer than the image)."""
        if not self.scalebar_enabled:
            return True
        return self._compute_scalebar_layout(width, height, nm_per_pixel, diffraction) is not None

    def get_scalebar_box_rect(self, width: int, height: int, nm_per_pixel: float,
                              diffraction: Optional[DiffractionGeometry] = None) -> Optional[tuple[float, float, float, float]]:
        """Return (left, top, right, bottom) of the full scalebar box in image coordinates."""
        layout = self._compute_scalebar_layout(width, height, nm_per_pixel, diffraction)
        if layout is None:
            return None
        return (
            float(layout["box_left"]),
            float(layout["box_top"]),
            float(layout["box_right"]),
            float(layout["box_bottom"]),
        )
    
    def _draw_aperture(self, qimg: QImage, width: int, height: int, nm_per_pixel: float):
        """Draw aperture overlay on the image."""
        if nm_per_pixel is None or nm_per_pixel <= 0:
            return
        
        # Calculate apparent diameter and radius
        apparent_diameter_um = self.aperture_nominal_size / 50.0
        apparent_radius_um = apparent_diameter_um / 2.0
        apparent_radius_nm = apparent_radius_um * 1000.0
        # Target INNER radius in pixels (physical clear aperture)
        target_inner_radius_px = float(apparent_radius_nm) / float(nm_per_pixel)
        
        # Center of image
        center_x = width // 2
        center_y = height // 2
        
        # Draw circle
        painter = QPainter(qimg)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Use a consistent pen width and ensure INNER diameter stays correct.
        # Qt strokes are centered on the ellipse path, so half the pen width
        # is inside the path and half is outside. To keep the INNER diameter
        # equal to the requested apparent diameter, expand the ellipse radius
        # by pen_width/2.
        pen_width_px = 5.0
        pen = QPen(self.aperture_color)
        try:
            pen.setWidthF(pen_width_px)
        except Exception:
            # Fallback for environments without setWidthF
            pen.setWidth(int(round(pen_width_px)))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Adjusted (outer) radius so that inner radius matches target
        adjusted_radius_px = target_inner_radius_px + (pen_width_px / 2.0)
        rect = QRectF(
            center_x - adjusted_radius_px,
            center_y - adjusted_radius_px,
            2.0 * adjusted_radius_px,
            2.0 * adjusted_radius_px,
        )
        painter.drawEllipse(rect)
        
        painter.end()

    def _draw_measurement(self, qimg: QImage, width: int, height: int, nm_per_pixel: float,
                          diffraction: Optional[DiffractionGeometry] = None):
        """Draw all committed measurements and the live drag preview."""
        to_draw = list(self.measurements)
        if self.measurement_preview is not None:
            to_draw.append(self.measurement_preview)
        if not to_draw:
            return

        painter = QPainter(qimg)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            painter.setFont(self.measurement_font if isinstance(self.measurement_font, QFont)
                            else QFont("Arial", 16, QFont.Weight.Bold))
        except Exception:
            painter.setFont(QFont("Arial", 16, QFont.Weight.Bold))

        for m in to_draw:
            x1 = int(max(0, min(width - 1, m["start"][0])))
            y1 = int(max(0, min(height - 1, m["start"][1])))
            x2 = int(max(0, min(width - 1, m["end"][0])))
            y2 = int(max(0, min(height - 1, m["end"][1])))

            dx = float(x2 - x1)
            dy = float(y2 - y1)
            length_px = math.hypot(dx, dy)
            if length_px < 1e-6:
                continue

            ux = dx / length_px
            uy = dy / length_px
            px = -uy
            py = ux
            line_width = max(1, int(m.get("line_width", self.measurement_line_width)))
            cap_len = max(10.0, line_width * 3.0)
            cap_half = max(5.0, line_width * 1.8)
            line_color = QColor(m.get("line_color", self.measurement_line_color))
            text_color = QColor(m.get("text_color", self.measurement_text_color))
            show_label = bool(m.get("show_label", self.measurement_show_label))

            # Main line
            pen = QPen(line_color)
            try:
                pen.setWidthF(float(line_width))
            except Exception:
                pen.setWidth(line_width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(x1, y1, x2, y2)

            start_cap = str(m.get("start_cap", "head")).strip().lower()
            end_cap = str(m.get("end_cap", "head")).strip().lower()
            if start_cap in {"arrow", "block"}:
                start_cap = "head"
            if end_cap in {"arrow", "block"}:
                end_cap = "head"
            self._draw_measurement_cap(
                painter, start_cap, x1, y1, ux, uy, px, py, cap_len, cap_half, line_width, line_color
            )
            self._draw_measurement_cap(
                painter, end_cap, x2, y2, -ux, -uy, px, py, cap_len, cap_half, line_width, line_color
            )

            # Label
            if not show_label:
                continue

            r, g, b, *_ = text_color.getRgb()
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            outline_color = QColor(0, 0, 0) if luminance > 0.5 else QColor(255, 255, 255)

            # Value from the unrounded (sub-pixel) end points; the drawn line uses whole pixels.
            fx1 = max(0.0, min(float(width), float(m["start"][0])))
            fy1 = max(0.0, min(float(height), float(m["start"][1])))
            fx2 = max(0.0, min(float(width), float(m["end"][0])))
            fy2 = max(0.0, min(float(height), float(m["end"][1])))
            label = self.format_measurement_label((fx1, fy1), (fx2, fy2), nm_per_pixel, diffraction)

            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(label)
            ascent = fm.ascent()
            descent = fm.descent()

            mid_x = (x1 + x2) / 2.0
            mid_y = (y1 + y2) / 2.0
            default_offset = max(16.0, line_width * 3.0)
            # Apply stored per-measurement label offset (image-pixel space)
            ldx = float(m.get("label_offset", (0.0, 0.0))[0])
            ldy = float(m.get("label_offset", (0.0, 0.0))[1])
            text_cx = mid_x + px * default_offset + ldx
            text_cy = mid_y + py * default_offset + ldy

            text_x = int(round(text_cx - text_w / 2.0))
            text_baseline_y = int(round(text_cy + (ascent - descent) / 2.0))
            text_x = max(0, min(width - text_w, text_x))
            text_baseline_y = max(ascent, min(height - descent, text_baseline_y))

            outline_pen = QPen(outline_color)
            outline_pen.setWidth(3)
            painter.setPen(outline_pen)
            painter.drawText(text_x, text_baseline_y, label)
            painter.setPen(QPen(text_color))
            painter.drawText(text_x, text_baseline_y, label)

        painter.end()

    def _draw_measurement_cap(
        self,
        painter: QPainter,
        cap_type: str,
        x: int,
        y: int,
        ux: float,
        uy: float,
        px: float,
        py: float,
        cap_len: float,
        cap_half: float,
        line_width: int,
        color: QColor,
    ):
        """Draw a measurement end cap at a point using the requested cap style."""
        cap = cap_type if cap_type in {"head", "tick", "dot", "none"} else "head"
        if cap == "none":
            return

        painter.setPen(QPen(color, max(1, line_width)))

        if cap == "head":
            c1x = x + ux * cap_len + px * cap_half
            c1y = y + uy * cap_len + py * cap_half
            c2x = x + ux * cap_len - px * cap_half
            c2y = y + uy * cap_len - py * cap_half
            painter.drawLine(x, y, int(round(c1x)), int(round(c1y)))
            painter.drawLine(x, y, int(round(c2x)), int(round(c2y)))
            return

        if cap == "tick":
            tick_len = max(6.0, cap_half * 1.2)
            tx1 = x + px * tick_len
            ty1 = y + py * tick_len
            tx2 = x - px * tick_len
            ty2 = y - py * tick_len
            painter.drawLine(int(round(tx1)), int(round(ty1)), int(round(tx2)), int(round(ty2)))
            return

        if cap == "dot":
            radius = max(2.0, line_width * 0.9)
            old_brush = painter.brush()
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QRectF(float(x) - radius, float(y) - radius, 2.0 * radius, 2.0 * radius))
            painter.setBrush(old_brush)

    # --- Diffraction (reciprocal-space) overlays -------------------------------------------

    def measurement_value(self, start, end, nm_per_pixel: float,
                          diffraction: Optional[DiffractionGeometry] = None) -> tuple[float, str]:
        """Return (value, unit_text) for a measurement line in the active unit.

        Real space: length in nm/µm. Diffraction: exact reciprocal distance |s2 - s1| on the
        Ewald sphere in Å⁻¹/nm⁻¹, or the corresponding d-spacing 1/|s2 - s1| in Å.
        """
        if diffraction is not None and diffraction.is_valid():
            recip = diffraction.reciprocal_distance(
                (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))
            )
            unit = self.recip_measurement_unit
            if unit == D_SPACING_ANGSTROM:
                return (1.0 / recip if recip > 0 else math.inf), "Å"
            return inv_angstrom_to_unit(recip, unit), unit

        length_px = math.hypot(float(end[0]) - float(start[0]), float(end[1]) - float(start[1]))
        length_nm = length_px * float(nm_per_pixel or 0.0)
        if self.measurement_unit == "µm":
            return length_nm / 1000.0, "µm"
        return length_nm, "nm"

    def format_measurement_label(self, start, end, nm_per_pixel: float,
                                 diffraction: Optional[DiffractionGeometry] = None) -> str:
        """On-image label text for a measurement line."""
        value, unit = self.measurement_value(start, end, nm_per_pixel, diffraction)
        if diffraction is not None and diffraction.is_valid():
            if self.recip_measurement_unit == D_SPACING_ANGSTROM:
                return format_resolution_value(value)
            return f"{format_reciprocal_value(value)} {unit}"
        return f"{int(round(value))} {unit}"

    def _draw_beam_center_marker(self, qimg: QImage, diffraction: DiffractionGeometry):
        """Draw a small cross at the beam centre (uses the ring colour)."""
        cx, cy = diffraction.beam_center_px
        painter = QPainter(qimg)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(self.ring_color))
        pen.setWidthF(max(1.0, float(self.ring_line_width)))
        painter.setPen(pen)
        arm = max(6.0, 4.0 * float(self.ring_line_width))
        painter.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
        painter.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy + arm))
        painter.end()

    def _draw_resolution_rings(self, qimg: QImage, width: int, height: int,
                               diffraction: DiffractionGeometry):
        """Draw resolution rings (d-spacings in Å) centred on the beam centre.

        Ring radius uses the exact flat-detector geometry R = L·tan(2θ), θ = asin(λ/2d).
        The pen is centred on the ring path, so the line centre marks the resolution.
        Labels are placed just outside each ring at the first candidate angle whose label
        box fits inside the image.
        """
        layout = self.compute_ring_layout(width, height, diffraction)
        if not layout:
            return
        cx, cy = diffraction.beam_center_px
        color = QColor(self.ring_color)
        line_width = max(1.0, float(self.ring_line_width))

        painter = QPainter(qimg)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._ring_font())

        r_, g_, b_, *_ = color.getRgb()
        luminance = (0.299 * r_ + 0.587 * g_ + 0.114 * b_) / 255.0
        outline_color = QColor(0, 0, 0) if luminance > 0.5 else QColor(255, 255, 255)

        for ring in layout:
            pen = QPen(color)
            pen.setWidthF(line_width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), ring["radius"], ring["radius"])

            box = ring.get("label_box")
            if box is None:
                continue
            tx, ty = int(round(box["left"])), int(round(box["baseline"]))
            outline_pen = QPen(outline_color)
            outline_pen.setWidth(3)
            painter.setPen(outline_pen)
            painter.drawText(tx, ty, ring["label"])
            painter.setPen(QPen(color))
            painter.drawText(tx, ty, ring["label"])

        painter.end()

    def _ring_font(self) -> QFont:
        return QFont(self.ring_font) if isinstance(self.ring_font, QFont) else QFont("Arial", 14, QFont.Weight.Bold)

    def compute_ring_layout(self, width: int, height: int, diffraction: DiffractionGeometry) -> list:
        """Ring radii and label boxes (image pixel coordinates) for the enabled rings.

        Returns a list of dicts: {"entry": the ring_resolutions dict, "d", "radius", "label",
        "label_box": None or {"left", "top", "right", "bottom", "baseline", "cx", "cy"}}.

        Label placement: if the entry has "label_angle" (degrees, image y axis down) the label
        box centre sits at that angle, at radius + "label_radial" (px, measured from the ring,
        so the label follows the ring when the calibration or beam centre changes). Otherwise
        it is placed just outside the ring at the first candidate angle where it fits.
        """
        if diffraction is None or not diffraction.is_valid():
            return []
        entries = [r for r in self.ring_resolutions if bool(r.get("enabled", True))]
        if not entries:
            return []
        cx, cy = diffraction.beam_center_px
        line_width = max(1.0, float(self.ring_line_width))
        farthest_corner = max(
            math.hypot(px - cx, py - cy) for px in (0.0, float(width)) for py in (0.0, float(height))
        )

        fm = None
        if self.ring_show_labels:
            tmp_img = QImage(1, 1, QImage.Format.Format_ARGB32)
            tmp_painter = QPainter(tmp_img)
            tmp_painter.setFont(self._ring_font())
            fm = tmp_painter.fontMetrics()
            ascent = float(fm.ascent())
            text_h = ascent + float(fm.descent())

        # Candidate label angles (degrees, image y axis points down): upper-right first.
        candidate_angles = (-45.0, -135.0, 45.0, 135.0, -90.0, 0.0, 180.0, 90.0,
                            -22.5, -67.5, -112.5, -157.5, 22.5, 67.5, 112.5, 157.5)
        gap = line_width / 2.0 + 3.0
        margin = 2.0
        layout = []
        for entry in sorted(entries, key=lambda e: float(e.get("d", 0.0))):
            try:
                d = float(entry.get("d"))
            except (TypeError, ValueError):
                continue
            radius = diffraction.radius_px_for_resolution(d)
            if radius is None or radius <= 0 or radius > farthest_corner + line_width:
                continue  # unreachable, or entirely outside the image
            ring = {"entry": entry, "d": d, "radius": radius, "label": format_resolution_label(d), "label_box": None}
            layout.append(ring)
            if fm is None:
                continue

            text_w = float(fm.horizontalAdvance(ring["label"]))

            def _box(box_cx: float, box_cy: float) -> dict:
                left = box_cx - text_w / 2.0
                top = box_cy - text_h / 2.0
                return {"left": left, "top": top, "right": left + text_w, "bottom": top + text_h,
                        "baseline": top + ascent, "cx": box_cx, "cy": box_cy}

            manual_angle = entry.get("label_angle")
            if manual_angle is not None:
                try:
                    a = math.radians(float(manual_angle))
                    radial = float(entry.get("label_radial", 0.0))
                except (TypeError, ValueError):
                    a, radial = None, 0.0
                if a is not None and math.isfinite(a) and math.isfinite(radial):
                    dist = max(0.0, radius + radial)
                    box_cx = cx + math.cos(a) * dist
                    box_cy = cy + math.sin(a) * dist
                    # Keep a manually placed label inside the image.
                    box_cx = min(max(box_cx, text_w / 2.0), float(width) - text_w / 2.0)
                    box_cy = min(max(box_cy, text_h / 2.0), float(height) - text_h / 2.0)
                    ring["label_box"] = _box(box_cx, box_cy)
                    continue

            for angle_deg in candidate_angles:
                a = math.radians(angle_deg)
                ux, uy = math.cos(a), math.sin(a)
                # Push the label box outward until its nearest corner clears the ring.
                half_extent = abs(ux) * text_w / 2.0 + abs(uy) * text_h / 2.0
                dist = radius + gap + half_extent
                box = _box(cx + ux * dist, cy + uy * dist)
                if (box["left"] >= margin and box["top"] >= margin
                        and box["right"] <= width - margin and box["bottom"] <= height - margin):
                    ring["label_box"] = box
                    break

        if fm is not None:
            tmp_painter.end()
        return layout

    def get_label_centres(self) -> list:
        """Return the image-pixel centre of each committed measurement label.
        Used for hit-testing during label-drag mode.
        Returns list of (cx, cy) floats (or None if degenerate), one per self.measurements.
        """
        results = []
        for m in self.measurements:
            if not bool(m.get("show_label", self.measurement_show_label)):
                results.append(None)
                continue
            x1, y1 = float(m["start"][0]), float(m["start"][1])
            x2, y2 = float(m["end"][0]), float(m["end"][1])
            dx = x2 - x1
            dy = y2 - y1
            length_px = math.hypot(dx, dy)
            if length_px < 1e-6:
                results.append(None)
                continue
            ux, uy = dx / length_px, dy / length_px
            pnx, pny = -uy, ux          # perpendicular unit vector
            mid_x = (x1 + x2) / 2.0
            mid_y = (y1 + y2) / 2.0
            line_width = max(1, int(m.get("line_width", self.measurement_line_width)))
            default_offset = max(16.0, line_width * 3.0)
            ldx = float(m.get("label_offset", (0.0, 0.0))[0])
            ldy = float(m.get("label_offset", (0.0, 0.0))[1])
            cx = mid_x + pnx * default_offset + ldx
            cy = mid_y + pny * default_offset + ldy
            results.append((cx, cy))
        return results
