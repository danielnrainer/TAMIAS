"""Measurement draw/drag interaction controller for TAMIAS."""

from __future__ import annotations

from typing import Any

import numpy as np
from PyQt6.QtGui import QColor


class MeasurementInteractionController:
    """Owns measurement-related mouse interaction logic for the editor."""

    def __init__(self, editor: Any):
        self.editor = editor

    def on_draw_press(self, x: int, y: int):
        """Mouse press handler for draw/drag measurement interactions."""
        e = self.editor
        if not e.image_processor.has_image():
            return
        if e.crop_handle_mouse_press(x, y):
            return
        if e._scalebar_drag_active:
            self.start_scalebar_drag(x, y)
            return
        if e._line_drag_active:
            self.start_line_drag(x, y)
            return
        if e._label_drag_active:
            self.start_label_drag(x, y)
            return

        mapped = e._map_label_to_image_coords(x, y)
        if mapped is None:
            return
        e._draw_preview_start = mapped
        e.overlay_renderer.measurement_preview = {"start": mapped, "end": mapped}
        e.update_display()

    def on_draw_move(self, x: int, y: int):
        """Mouse move handler for live preview and drag updates."""
        e = self.editor
        if e.crop_handle_mouse_move(x, y):
            return
        if e._scalebar_drag_active:
            self.update_scalebar_drag(x, y)
            return
        if e._line_drag_active:
            self.update_line_drag(x, y)
            return
        if e._label_drag_active:
            self.update_label_drag(x, y)
            return
        if e._draw_preview_start is None:
            return
        mapped = e._map_label_to_image_coords(x, y)
        if mapped is None:
            return
        e.overlay_renderer.measurement_preview = {
            "start": e._draw_preview_start,
            "end": mapped,
        }
        e.update_display()

    def on_draw_release(self, x: int, y: int):
        """Mouse release handler for committing draws and finishing drags."""
        e = self.editor
        if e.crop_handle_mouse_release(x, y):
            return
        if e._scalebar_drag_active:
            self.finish_scalebar_drag(x, y)
            return
        if e._line_drag_active:
            self.finish_line_drag(x, y)
            return
        if e._label_drag_active:
            self.finish_label_drag(x, y)
            return
        if e._draw_preview_start is None:
            return

        mapped = e._map_label_to_image_coords(x, y)
        if mapped is None:
            mapped = e._draw_preview_start
        start = e._draw_preview_start
        end = mapped
        e._draw_preview_start = None
        e.overlay_renderer.measurement_preview = None
        if np.hypot(float(end[0] - start[0]), float(end[1] - start[1])) > 3:
            e.overlay_renderer.measurements.append(
                {
                    "start": start,
                    "end": end,
                    "start_cap": e.measurement_start_end_combo.currentText(),
                    "end_cap": e.measurement_end_end_combo.currentText(),
                    "show_label": bool(e.overlay_renderer.measurement_show_label),
                    "line_color": QColor(e.overlay_renderer.measurement_line_color),
                    "text_color": QColor(e.overlay_renderer.measurement_text_color),
                    "line_width": int(e.overlay_renderer.measurement_line_width),
                }
            )
            e._refresh_measurements_list()
            e.measurement_table.selectRow(len(e.overlay_renderer.measurements) - 1)
        e.update_display()

    def start_scalebar_drag(self, label_x: int, label_y: int):
        e = self.editor
        e._scalebar_drag_origin_img = None
        if not e.overlay_renderer.scalebar_enabled or e._last_rendered_image_size is None:
            return

        mapped = e._map_label_to_image_coords(label_x, label_y)
        if mapped is None:
            return
        img_x, img_y = float(mapped[0]), float(mapped[1])

        img_w, img_h = e._last_rendered_image_size
        rect = e.overlay_renderer.get_scalebar_box_rect(img_w, img_h, e.nm_per_pixel)
        if rect is None:
            return

        hit_pad = 8.0
        left, top, right, bottom = rect
        if not (left - hit_pad <= img_x <= right + hit_pad and top - hit_pad <= img_y <= bottom + hit_pad):
            e.measurement_status_label.setText("Click on the scalebar box to move it.")
            return

        e._scalebar_drag_origin_img = (img_x, img_y)
        e._scalebar_drag_offset_start = tuple(e.overlay_renderer.scalebar_offset)
        if e.position_combo.currentText() != "custom":
            e.position_combo.blockSignals(True)
            e.position_combo.setCurrentText("custom")
            e.position_combo.blockSignals(False)

    def update_scalebar_drag(self, label_x: int, label_y: int):
        e = self.editor
        if e._scalebar_drag_origin_img is None:
            return
        mapped = e._map_label_to_image_coords(label_x, label_y)
        if mapped is None:
            return
        ddx = float(mapped[0]) - float(e._scalebar_drag_origin_img[0])
        ddy = float(mapped[1]) - float(e._scalebar_drag_origin_img[1])
        e.overlay_renderer.scalebar_offset = (
            float(e._scalebar_drag_offset_start[0]) + ddx,
            float(e._scalebar_drag_offset_start[1]) + ddy,
        )
        e.update_display()

    def finish_scalebar_drag(self, label_x: int, label_y: int):
        self.update_scalebar_drag(label_x, label_y)
        self.editor._scalebar_drag_origin_img = None

    def start_line_drag(self, label_x: int, label_y: int):
        e = self.editor
        e._line_drag_index = None
        if not e.overlay_renderer.measurements:
            e.measurement_status_label.setText("No measurements available to move.")
            return

        mapped = e._map_label_to_image_coords(label_x, label_y)
        if mapped is None:
            return

        _img_w, _img_h, scale, offset_x, offset_y = e._get_display_mapping()
        if scale <= 0:
            return

        best_idx = None
        best_dist = 18.0
        px = float(label_x)
        py = float(label_y)
        for idx, m in enumerate(e.overlay_renderer.measurements):
            sx1 = float(m["start"][0]) * scale + offset_x
            sy1 = float(m["start"][1]) * scale + offset_y
            sx2 = float(m["end"][0]) * scale + offset_x
            sy2 = float(m["end"][1]) * scale + offset_y
            dist = e._point_to_segment_distance(px, py, sx1, sy1, sx2, sy2)
            if dist < best_dist:
                best_dist = dist
                best_idx = idx

        if best_idx is None:
            e.measurement_status_label.setText("No line found nearby. Click closer to a measurement line.")
            return

        e._line_drag_index = best_idx
        e._line_drag_origin_img = (float(mapped[0]), float(mapped[1]))
        m = e.overlay_renderer.measurements[best_idx]
        e._line_drag_start_start = (float(m["start"][0]), float(m["start"][1]))
        e._line_drag_start_end = (float(m["end"][0]), float(m["end"][1]))

    def update_line_drag(self, label_x: int, label_y: int):
        e = self.editor
        if e._line_drag_index is None or e._line_drag_origin_img is None:
            return
        mapped = e._map_label_to_image_coords(label_x, label_y)
        if mapped is None or e._last_rendered_image_size is None:
            return

        ddx = float(mapped[0]) - float(e._line_drag_origin_img[0])
        ddy = float(mapped[1]) - float(e._line_drag_origin_img[1])

        x1 = e._line_drag_start_start[0] + ddx
        y1 = e._line_drag_start_start[1] + ddy
        x2 = e._line_drag_start_end[0] + ddx
        y2 = e._line_drag_start_end[1] + ddy

        img_w, img_h = e._last_rendered_image_size
        min_x = min(x1, x2)
        max_x = max(x1, x2)
        min_y = min(y1, y2)
        max_y = max(y1, y2)
        shift_x = 0.0
        shift_y = 0.0
        if min_x < 0:
            shift_x = -min_x
        elif max_x > (img_w - 1):
            shift_x = (img_w - 1) - max_x
        if min_y < 0:
            shift_y = -min_y
        elif max_y > (img_h - 1):
            shift_y = (img_h - 1) - max_y

        x1 += shift_x
        y1 += shift_y
        x2 += shift_x
        y2 += shift_y

        e.overlay_renderer.measurements[e._line_drag_index]["start"] = (int(round(x1)), int(round(y1)))
        e.overlay_renderer.measurements[e._line_drag_index]["end"] = (int(round(x2)), int(round(y2)))
        e._refresh_measurements_list()
        e.update_display()

    def finish_line_drag(self, label_x: int, label_y: int):
        self.update_line_drag(label_x, label_y)
        e = self.editor
        e._line_drag_index = None
        e._line_drag_origin_img = None

    def start_label_drag(self, label_x: int, label_y: int):
        e = self.editor
        e._label_drag_index = None
        if not e.image_processor.has_image() or e._last_rendered_image_size is None:
            return
        _img_w, _img_h, scale, offset_x, offset_y = e._get_display_mapping()

        centres = e.overlay_renderer.get_label_centres()
        hit_radius_screen = 40.0
        best_dist = hit_radius_screen
        best_idx = None
        for i, c in enumerate(centres):
            if c is None:
                continue
            sx = c[0] * scale + offset_x
            sy = c[1] * scale + offset_y
            dist = np.hypot(label_x - sx, label_y - sy)
            if dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx is None:
            e.measurement_status_label.setText("No label found nearby. Click closer to a label.")
            return

        e._label_drag_index = best_idx
        mapped = e._map_label_to_image_coords(label_x, label_y)
        e._label_drag_origin_img = mapped if mapped is not None else (0.0, 0.0)
        m = e.overlay_renderer.measurements[best_idx]
        e._label_drag_offset_start = tuple(m.get("label_offset", (0.0, 0.0)))

    def update_label_drag(self, label_x: int, label_y: int):
        e = self.editor
        if e._label_drag_index is None or e._label_drag_origin_img is None:
            return
        mapped = e._map_label_to_image_coords(label_x, label_y)
        if mapped is None:
            return
        ddx = float(mapped[0]) - float(e._label_drag_origin_img[0])
        ddy = float(mapped[1]) - float(e._label_drag_origin_img[1])
        new_offset = (
            float(e._label_drag_offset_start[0]) + ddx,
            float(e._label_drag_offset_start[1]) + ddy,
        )
        e.overlay_renderer.measurements[e._label_drag_index]["label_offset"] = new_offset
        e.update_display()

    def finish_label_drag(self, label_x: int, label_y: int):
        self.update_label_drag(label_x, label_y)
        e = self.editor
        e._label_drag_index = None
        e._label_drag_origin_img = None
