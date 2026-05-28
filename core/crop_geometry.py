"""Geometry helpers for manual crop selection and movement."""

from __future__ import annotations

from typing import Tuple

Rect = Tuple[int, int, int, int]  # inclusive: x1, y1, x2, y2
Point = Tuple[int, int]


def normalize_rect(start: Point, end: Point) -> Rect:
    """Return normalized inclusive rectangle from two corner points."""
    x1 = min(int(start[0]), int(end[0]))
    y1 = min(int(start[1]), int(end[1]))
    x2 = max(int(start[0]), int(end[0]))
    y2 = max(int(start[1]), int(end[1]))
    return (x1, y1, x2, y2)


def rect_size(rect: Rect) -> Tuple[int, int]:
    """Return inclusive rectangle size as (width, height)."""
    x1, y1, x2, y2 = rect
    return (x2 - x1 + 1, y2 - y1 + 1)


def point_in_rect(point: Point, rect: Rect) -> bool:
    """Return True if point lies inside inclusive rectangle."""
    x, y = int(point[0]), int(point[1])
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


def clamp_point_to_image(point: Point, img_w: int, img_h: int) -> Point:
    """Clamp point to image bounds."""
    x = max(0, min(img_w - 1, int(point[0])))
    y = max(0, min(img_h - 1, int(point[1])))
    return (x, y)


def constrain_endpoint(
    start: Point,
    candidate: Point,
    mode: str,
    aspect_ratio: float,
    img_w: int,
    img_h: int,
) -> Point:
    """Constrain endpoint to free/square/aspect-locked rectangle within bounds."""
    sx, sy = clamp_point_to_image(start, img_w, img_h)
    cx, cy = clamp_point_to_image(candidate, img_w, img_h)

    if mode == "Free":
        return (cx, cy)

    dx = cx - sx
    dy = cy - sy
    sign_x = 1 if dx >= 0 else -1
    sign_y = 1 if dy >= 0 else -1
    abs_dx = abs(dx)
    abs_dy = abs(dy)

    max_w = float((img_w - 1 - sx) if sign_x > 0 else sx)
    max_h = float((img_h - 1 - sy) if sign_y > 0 else sy)
    if max_w < 1 or max_h < 1:
        return (sx, sy)

    if mode == "Square":
        side = float(max(abs_dx, abs_dy, 1))
        side = min(side, max_w, max_h)
        w = h = side
    else:
        ratio = max(1e-6, float(aspect_ratio))
        desired_w = float(max(abs_dx, 1))
        desired_h = float(max(abs_dy, 1))
        if desired_h == 0:
            desired_h = desired_w / ratio
        if desired_w / max(desired_h, 1e-6) >= ratio:
            w = desired_w
            h = desired_w / ratio
        else:
            h = desired_h
            w = desired_h * ratio
        scale = min(1.0, max_w / w if w > 0 else 1.0, max_h / h if h > 0 else 1.0)
        w *= scale
        h *= scale
        w = max(1.0, w)
        h = max(1.0, h)

    end_x = sx + sign_x * int(round(w))
    end_y = sy + sign_y * int(round(h))
    return clamp_point_to_image((end_x, end_y), img_w, img_h)


def move_rect_within_bounds(rect: Rect, dx: int, dy: int, img_w: int, img_h: int) -> Rect:
    """Move rectangle by dx/dy while keeping it inside image bounds."""
    x1, y1, x2, y2 = rect
    nx1 = x1 + int(dx)
    ny1 = y1 + int(dy)
    nx2 = x2 + int(dx)
    ny2 = y2 + int(dy)

    if nx1 < 0:
        shift = -nx1
        nx1 += shift
        nx2 += shift
    if ny1 < 0:
        shift = -ny1
        ny1 += shift
        ny2 += shift
    if nx2 > img_w - 1:
        shift = nx2 - (img_w - 1)
        nx1 -= shift
        nx2 -= shift
    if ny2 > img_h - 1:
        shift = ny2 - (img_h - 1)
        ny1 -= shift
        ny2 -= shift

    return (
        max(0, min(img_w - 1, nx1)),
        max(0, min(img_h - 1, ny1)),
        max(0, min(img_w - 1, nx2)),
        max(0, min(img_h - 1, ny2)),
    )


def center_rect(rect: Rect, img_w: int, img_h: int) -> Rect:
    """Center rectangle in the image while preserving size, clamped to bounds."""
    width, height = rect_size(rect)
    cx = (img_w - 1) / 2.0
    cy = (img_h - 1) / 2.0

    x1 = int(round(cx - (width - 1) / 2.0))
    y1 = int(round(cy - (height - 1) / 2.0))
    x2 = x1 + width - 1
    y2 = y1 + height - 1

    if x1 < 0:
        x2 += -x1
        x1 = 0
    if y1 < 0:
        y2 += -y1
        y1 = 0
    if x2 > img_w - 1:
        shift = x2 - (img_w - 1)
        x1 -= shift
        x2 -= shift
    if y2 > img_h - 1:
        shift = y2 - (img_h - 1)
        y1 -= shift
        y2 -= shift

    return (
        max(0, min(img_w - 1, x1)),
        max(0, min(img_h - 1, y1)),
        max(0, min(img_w - 1, x2)),
        max(0, min(img_h - 1, y2)),
    )
