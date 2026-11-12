"""
Diffraction (reciprocal-space) geometry for TAMIAS.

Conventions
-----------
* Reciprocal lengths follow the crystallographic convention |s| = 1/d = 2 sin(theta) / lambda
  (no factor of 2*pi). Units are reciprocal Angstrom (Å⁻¹) or reciprocal nanometre (nm⁻¹);
  1 Å⁻¹ = 10 nm⁻¹.
* Flat detector perpendicular to the incident beam at distance L (the "camera length" /
  "detector distance") from the sample. A pixel at radial distance R (mm) from the beam
  centre sees scattering angle 2θ = atan(R / L).
* Beam-centre and point coordinates are image-pixel coordinates with the pixel-corner
  convention used by QPainter (and by DIALS for .rodhypix): pixel (i, j) spans
  [i, i+1) x [j, j+1), so the centre of pixel (i, j) is (i + 0.5, j + 0.5).

Everything here is pure Python (no Qt) so it can be unit tested in isolation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

# CODATA 2018 exact / recommended values
_PLANCK_H = 6.62607015e-34          # J s
_ELECTRON_MASS = 9.1093837015e-31   # kg
_ELEMENTARY_CHARGE = 1.602176634e-19  # C
_SPEED_OF_LIGHT = 299792458.0       # m / s

RECIPROCAL_ANGSTROM = "Å⁻¹"
RECIPROCAL_NM = "nm⁻¹"
D_SPACING_ANGSTROM = "Resolution (Å)"

RECIPROCAL_UNITS = (RECIPROCAL_ANGSTROM, RECIPROCAL_NM)
# Measurement read-outs available in diffraction mode (first entry is the default):
# resolution d = 1/|Δs| in Å, or the reciprocal length |Δs| itself.
RECIPROCAL_MEASUREMENT_UNITS = (D_SPACING_ANGSTROM, RECIPROCAL_ANGSTROM, RECIPROCAL_NM)


def format_resolution_value(d_angstrom: float) -> str:
    """Resolution read-out for measurement labels, e.g. '1.23 Å' (2 decimals below 100 Å)."""
    d = float(d_angstrom)
    if math.isfinite(d) and d < 100.0:
        return f"{d:.2f} Å"
    return f"{format_reciprocal_value(d)} Å"

# Default resolution-ring presets (d-spacings in Å)
DEFAULT_RING_RESOLUTIONS = (0.8, 1.0, 1.2, 2.0)

# Typical TEM accelerating voltages offered as wavelength shortcuts (kV)
COMMON_ACCELERATING_VOLTAGES_KV = (80, 120, 200, 300)


def electron_wavelength_angstrom(accelerating_voltage_kv: float) -> float:
    """Relativistic electron wavelength (Å) for an accelerating voltage in kV.

    λ = h / sqrt(2 m0 e V (1 + e V / (2 m0 c²)))
    e.g. 200 kV -> 0.025079 Å, 300 kV -> 0.019687 Å.
    """
    voltage = float(accelerating_voltage_kv) * 1000.0
    if not math.isfinite(voltage) or voltage <= 0:
        raise ValueError("Accelerating voltage must be positive.")
    m0, e, c, h = _ELECTRON_MASS, _ELEMENTARY_CHARGE, _SPEED_OF_LIGHT, _PLANCK_H
    momentum = math.sqrt(2.0 * m0 * e * voltage * (1.0 + e * voltage / (2.0 * m0 * c * c)))
    return h / momentum * 1e10


def reciprocal_to_inv_angstrom(value: float, unit: str) -> float:
    """Convert a reciprocal length in `unit` (Å⁻¹ or nm⁻¹) to Å⁻¹."""
    if unit == RECIPROCAL_NM:
        return float(value) / 10.0
    return float(value)


def inv_angstrom_to_unit(value_inv_a: float, unit: str) -> float:
    """Convert a reciprocal length in Å⁻¹ to `unit` (Å⁻¹ or nm⁻¹)."""
    if unit == RECIPROCAL_NM:
        return float(value_inv_a) * 10.0
    return float(value_inv_a)


def format_resolution_label(d_angstrom: float) -> str:
    """Format a d-spacing for ring labels, keeping at least one decimal (e.g. '1.0 Å')."""
    d = float(d_angstrom)
    text = f"{d:.1f}" if abs(d * 10.0 - round(d * 10.0)) < 1e-9 else f"{d:g}"
    return f"{text} Å"


def format_reciprocal_value(value: float) -> str:
    """Compact numeric formatting: 3 significant figures kept (1.00, 0.500), no exponent >= 100."""
    v = float(value)
    if not math.isfinite(v):
        return "∞"
    if abs(v) >= 100.0:
        return f"{v:.0f}"
    if v == 0.0:
        return "0"
    return f"{v:#.3g}".rstrip(".")


@dataclass(frozen=True)
class DiffractionGeometry:
    """Calibration of a diffraction pattern recorded on a flat detector.

    Attributes:
        camera_length_mm: Sample-to-detector distance L (mm).
        wavelength_angstrom: Radiation wavelength λ (Å).
        pixel_size_mm: Detector pixel size p (mm), square pixels assumed.
        beam_center_px: Direct-beam position (x, y) in current image pixel coordinates.
    """

    camera_length_mm: float
    wavelength_angstrom: float
    pixel_size_mm: float
    beam_center_px: Tuple[float, float]

    def is_valid(self) -> bool:
        values = (self.camera_length_mm, self.wavelength_angstrom, self.pixel_size_mm,
                  self.beam_center_px[0], self.beam_center_px[1])
        if not all(math.isfinite(float(v)) for v in values):
            return False
        return self.camera_length_mm > 0 and self.wavelength_angstrom > 0 and self.pixel_size_mm > 0

    # --- Linear (small-angle) calibration -------------------------------------------------

    def inv_angstrom_per_pixel(self) -> float:
        """Reciprocal length per pixel (Å⁻¹/px) at the beam centre.

        This is the exact derivative d|s|/dR at R = 0, i.e. p / (λ L). It is the calibration
        used for the scalebar. Away from the centre, the linear estimate of |s| = 1/d
        differs from the exact value by ≈ 3/8 (R/L)², which for electrons at typical camera
        lengths is < 0.1 % (e.g. 0.04 % at 0.8 Å for 200 kV).
        """
        return self.pixel_size_mm / (self.wavelength_angstrom * self.camera_length_mm)

    # --- Exact geometry -------------------------------------------------------------------

    def two_theta_at_radius_px(self, radius_px: float) -> float:
        """Scattering angle 2θ (radians) at a radial pixel distance from the beam centre."""
        return math.atan2(float(radius_px) * self.pixel_size_mm, self.camera_length_mm)

    def resolution_at_radius_px(self, radius_px: float) -> float:
        """d-spacing (Å) at a radial pixel distance from the beam centre (inf at the centre)."""
        theta = 0.5 * self.two_theta_at_radius_px(radius_px)
        s = math.sin(theta)
        if s <= 0.0:
            return math.inf
        return self.wavelength_angstrom / (2.0 * s)

    def radius_px_for_resolution(self, d_angstrom: float) -> Optional[float]:
        """Radial pixel distance of the ring for d-spacing `d_angstrom` (Å).

        Bragg: λ = 2 d sin θ  ->  θ = asin(λ / 2d); the ring lies at R = L tan(2θ).
        Returns None when the reflection is not reachable (λ/2d > 1) or scatters at
        2θ >= 90° (it can never hit a flat detector facing the beam).
        """
        d = float(d_angstrom)
        if not math.isfinite(d) or d <= 0:
            return None
        sin_theta = self.wavelength_angstrom / (2.0 * d)
        if sin_theta >= 1.0:
            return None
        two_theta = 2.0 * math.asin(sin_theta)
        if two_theta >= 0.5 * math.pi:
            return None
        return self.camera_length_mm * math.tan(two_theta) / self.pixel_size_mm

    def scattering_vector(self, x_px: float, y_px: float) -> Tuple[float, float, float]:
        """Scattering vector s = k_out - k_in (Å⁻¹) for a detector point, |k| = 1/λ.

        Lab frame: z along the incident beam, x/y along the detector's image axes.
        |s| = 2 sin θ / λ = 1/d.
        """
        dx = (float(x_px) - self.beam_center_px[0]) * self.pixel_size_mm
        dy = (float(y_px) - self.beam_center_px[1]) * self.pixel_size_mm
        dz = self.camera_length_mm
        norm = math.sqrt(dx * dx + dy * dy + dz * dz)
        k = 1.0 / self.wavelength_angstrom
        return (k * dx / norm, k * dy / norm, k * (dz / norm - 1.0))

    def reciprocal_distance(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """Exact reciprocal-space distance |s2 - s1| (Å⁻¹) between two detector points.

        For a centre-to-spot line this is 1/d of that reflection; for a spot-to-spot line it
        is the length of the difference vector g2 - g1.
        """
        s1 = self.scattering_vector(*p1)
        s2 = self.scattering_vector(*p2)
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(s1, s2)))

    def max_resolution_in_image(self, width: int, height: int) -> Tuple[float, float]:
        """Return (edge, corner) d-spacings (Å).

        `edge`: highest resolution with complete rings inside the image (nearest image edge).
        `corner`: highest resolution recorded anywhere (farthest image corner).
        """
        cx, cy = self.beam_center_px
        nearest_edge = max(0.0, min(cx, cy, float(width) - cx, float(height) - cy))
        farthest_corner = max(
            math.hypot(x - cx, y - cy) for x in (0.0, float(width)) for y in (0.0, float(height))
        )
        return self.resolution_at_radius_px(nearest_edge), self.resolution_at_radius_px(farthest_corner)


def resolve_header_geometry(header: Optional[dict]) -> dict:
    """Extract diffraction calibration values from a .rodhypix header dict.

    Returns a dict with any of: 'camera_length_mm', 'wavelength_angstrom', 'pixel_size_mm',
    'beam_center_px' (as loaded, before any crop/flip). Invalid/absent values are omitted.

    Conventions follow DIALS' FormatROD: the pixel size is used as stored (already the image
    pixel size), the beam origin is divided by the binning factor.
    """
    out: dict = {}
    if not isinstance(header, dict):
        return out

    def _positive(key: str) -> Optional[float]:
        try:
            value = float(header.get(key))
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value > 0 else None

    distance = _positive("distance_mm")
    if distance is not None:
        out["camera_length_mm"] = distance

    # DIALS (dxtbx FormatROD) uses the weighted alpha1/alpha2 wavelength; identical for electrons.
    wavelength = _positive("alpha12_wavelength") or _positive("alpha1_wavelength")
    if wavelength is not None:
        out["wavelength_angstrom"] = wavelength

    px = _positive("real_px_size_x")
    py = _positive("real_px_size_y")
    if px is not None and py is not None:
        out["pixel_size_mm"] = 0.5 * (px + py) if abs(px - py) > 1e-12 else px
    elif px is not None or py is not None:
        out["pixel_size_mm"] = px if px is not None else py

    ox, oy = header.get("origin_px_x"), header.get("origin_px_y")
    try:
        bin_x = float(header.get("bin_x") or 1) or 1.0
        bin_y = float(header.get("bin_y") or 1) or 1.0
        ox_f, oy_f = float(ox) / bin_x, float(oy) / bin_y
        if math.isfinite(ox_f) and math.isfinite(oy_f):
            out["beam_center_px"] = (ox_f, oy_f)
    except (TypeError, ValueError, ZeroDivisionError):
        pass

    return out


def header_tilt_warning(header: Optional[dict], tolerance_deg: float = 0.05) -> Optional[str]:
    """Return a warning if the header describes a tilted detector or beam.

    TAMIAS models the detector as flat and perpendicular to the beam. In CrysAlisPro's frame
    e1 is the beam direction, so detector rotation about e1 (detector_rotns[0]) is an in-plane
    rotation that does not change radial distances; rotations about e2/e3 (detector tilt) and
    beam rotations about e2/e3 would distort rings, which are not modelled.
    """
    if not isinstance(header, dict):
        return None
    tilts = []
    try:
        rotns = header.get("detector_rotns") or (0.0, 0.0, 0.0)
        tilts.extend(float(v) for v in tuple(rotns)[1:3])
    except (TypeError, ValueError):
        pass
    for key in ("beam_rotn_around_e2", "beam_rotn_around_e3"):
        try:
            tilts.append(float(header.get(key) or 0.0))
        except (TypeError, ValueError):
            pass
    worst = max((abs(t) for t in tilts if math.isfinite(t)), default=0.0)
    if worst > tolerance_deg:
        return (f"Header reports a detector/beam tilt of up to {worst:.2f}°; TAMIAS assumes a "
                "detector perpendicular to the beam, so rings and reciprocal values are approximate.")
    return None


def looks_like_diffraction_header(header: Optional[dict]) -> bool:
    """Heuristic: .rodhypix diffraction frames carry no direct-space pixel size.

    Real-space snapshots written by CrysAlisPro store a positive direct-space pixel size;
    diffraction frames store 0. (Some post-experiment real-space images also lack it, so
    this is only used as a hint, never to switch modes automatically.)
    """
    if not isinstance(header, dict):
        return False
    try:
        direct = float(header.get("direct_space_pixel_size_um") or 0.0)
    except (TypeError, ValueError):
        direct = 0.0
    geometry = resolve_header_geometry(header)
    return direct <= 0 and "camera_length_mm" in geometry and "wavelength_angstrom" in geometry
