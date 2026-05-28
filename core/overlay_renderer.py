"""
Overlay rendering module for TEM Image Editor.
Handles drawing scalebar, aperture, and measurement overlays on images.
"""

from typing import Optional
import math
import numpy as np
from PyQt6.QtGui import QImage, QPainter, QPen, QBrush, QColor, QFont
from PyQt6.QtCore import Qt, QRectF


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
        
        # Aperture parameters
        self.aperture_enabled = False
        self.aperture_nominal_size = 100  # diameter in µm
        self.aperture_color = QColor(255, 255, 0)

        # Particle measurement annotation parameters
        self.measurement_enabled = False
        self.measurements: list = []           # list of {"start": (x,y), "end": (x,y), "label_offset": (dx,dy)}
        self.measurement_preview: Optional[dict] = None  # in-progress drag
        self.measurement_unit = "nm"
        self.measurement_line_color = QColor(0, 255, 0)
        self.measurement_text_color = QColor(0, 255, 0)
        self.measurement_show_label = True
        self.measurement_line_width = 4
        self.measurement_font = QFont("Arial", 16, QFont.Weight.Bold)
    
    def render_image_with_overlays(self, 
                                   image: np.ndarray, 
                                   nm_per_pixel: float) -> Optional[QImage]:
        """
        Render image with scalebar and aperture overlays.
        
        Args:
            image: The numpy array image to render
            nm_per_pixel: Calibration in nanometers per pixel
            
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
    
    def _draw_scalebar(self, qimg: QImage, width: int, height: int, nm_per_pixel: float):
        """Draw scalebar on the image."""
        layout = self._compute_scalebar_layout(width, height, nm_per_pixel)
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
        painter.drawRect(x, y, scalebar_length_px, self.scalebar_thickness)

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

    def _compute_scalebar_layout(self, width: int, height: int, nm_per_pixel: float) -> Optional[dict]:
        """Compute scalebar geometry (bar, text, and union box) in image pixel coordinates."""
        if nm_per_pixel is None or nm_per_pixel <= 0 or width <= 0 or height <= 0:
            return None

        # Compute scalebar length in pixels
        if self.scalebar_unit == "µm":
            length_nm = self.scalebar_length_value * 1000.0
        else:
            length_nm = float(self.scalebar_length_value)
        
        desired_px = int(round(length_nm / nm_per_pixel))
        
        # Cap scalebar length to fit within margins
        margin = 30
        max_px = max(1, width - 2 * margin)
        scalebar_length_px = min(desired_px, max_px)
        
        # Determine position
        if "bottom" in self.scalebar_position:
            y = height - margin - self.scalebar_thickness
        else:
            y = margin
        
        if "right" in self.scalebar_position:
            x = width - margin - scalebar_length_px
        else:
            x = margin
        
        # Build label
        if self.scalebar_label_override is not None and str(self.scalebar_label_override).strip() != "":
            label_value_text = str(self.scalebar_label_override).strip()
        else:
            # Default formatting if no override provided
            if self.scalebar_unit == "µm":
                value = length_nm / 1000.0
            else:
                value = length_nm
            # Show integer if it's effectively an integer; otherwise, show up to 2 decimals without trailing zeros
            if abs(value - round(value)) < 1e-9:
                label_value_text = f"{int(round(value))}"
            else:
                label_value_text = f"{value:.2f}".rstrip('0').rstrip('.')
        unit_text = "µm" if self.scalebar_unit == "µm" else "nm"
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
        text_width = fm.horizontalAdvance(label)
        ascent = fm.ascent()
        descent = fm.descent()
        painter.end()

        # Text position
        text_bar_gap = 12  # gap between bar and text
        if "bottom" in self.scalebar_position:
            text_baseline_y = y - text_bar_gap
            text_top = text_baseline_y - ascent
            text_bottom = text_baseline_y + descent
        else:
            text_baseline_y = y + self.scalebar_thickness + ascent + text_bar_gap
            text_top = y + self.scalebar_thickness + text_bar_gap
            text_bottom = text_baseline_y + descent
        
        # Center label horizontally over the bar
        text_x = x + (scalebar_length_px - text_width) // 2
        text_x = max(0, min(text_x, width - text_width))

        # Union box around bar + label (used for optional background and drag hitbox)
        pad = text_bar_gap / 2
        rect_left = min(x, text_x) - pad
        rect_right = max(x + scalebar_length_px, text_x + text_width) + pad
        rect_top = min(y, text_top)
        rect_bottom = max(y + self.scalebar_thickness, text_bottom) + pad

        # Apply user drag offset and keep the whole box inside the image bounds.
        offset_x = float(self.scalebar_offset[0])
        offset_y = float(self.scalebar_offset[1])

        x = int(round(x + offset_x))
        y = int(round(y + offset_y))
        text_x = int(round(text_x + offset_x))
        text_baseline_y = int(round(text_baseline_y + offset_y))
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
        text_x = int(round(text_x + shift_x))
        text_baseline_y = int(round(text_baseline_y + shift_y))
        rect_left += shift_x
        rect_right += shift_x
        rect_top += shift_y
        rect_bottom += shift_y

        return {
            "bar_x": x,
            "bar_y": y,
            "bar_length_px": int(scalebar_length_px),
            "text_x": int(text_x),
            "text_baseline_y": int(text_baseline_y),
            "label": label,
            "box_left": float(max(0.0, rect_left)),
            "box_top": float(max(0.0, rect_top)),
            "box_right": float(min(float(width - 1), rect_right)),
            "box_bottom": float(min(float(height - 1), rect_bottom)),
        }

    def get_scalebar_box_rect(self, width: int, height: int, nm_per_pixel: float) -> Optional[tuple[float, float, float, float]]:
        """Return (left, top, right, bottom) of the full scalebar box in image coordinates."""
        layout = self._compute_scalebar_layout(width, height, nm_per_pixel)
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

    def _draw_measurement(self, qimg: QImage, width: int, height: int, nm_per_pixel: float):
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

            length_nm = length_px * float(nm_per_pixel)
            if self.measurement_unit == "µm":
                value = length_nm / 1000.0
                unit_text = "µm"
            else:
                value = length_nm
                unit_text = "nm"
            value_text = str(int(round(value)))
            label = f"{value_text} {unit_text}"

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
