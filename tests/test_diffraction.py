"""Unit tests for core.diffraction (pure-Python reciprocal-space geometry).

Run with:  python -m pytest tests
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.diffraction import (  # noqa: E402
    DiffractionGeometry,
    electron_wavelength_angstrom,
    format_resolution_label,
    inv_angstrom_to_unit,
    looks_like_diffraction_header,
    reciprocal_to_inv_angstrom,
    resolve_header_geometry,
)

# Synergy-ED / HyPix-ED values as stored in real .rodhypix headers (and CrysAlisPro .par)
SYNERGY = DiffractionGeometry(
    camera_length_mm=650.4, wavelength_angstrom=0.0251, pixel_size_mm=0.1, beam_center_px=(387.5, 192.5)
)


def test_electron_wavelength_reference_values():
    # Standard relativistic values (e.g. Williams & Carter, Table 1.1)
    assert electron_wavelength_angstrom(100) == pytest.approx(0.03701, abs=2e-5)
    assert electron_wavelength_angstrom(120) == pytest.approx(0.03349, abs=2e-5)
    assert electron_wavelength_angstrom(200) == pytest.approx(0.02508, abs=2e-5)
    assert electron_wavelength_angstrom(300) == pytest.approx(0.01969, abs=2e-5)
    with pytest.raises(ValueError):
        electron_wavelength_angstrom(0)


def test_unit_conversion():
    assert reciprocal_to_inv_angstrom(10.0, "nm⁻¹") == pytest.approx(1.0)
    assert reciprocal_to_inv_angstrom(0.5, "Å⁻¹") == pytest.approx(0.5)
    assert inv_angstrom_to_unit(0.5, "nm⁻¹") == pytest.approx(5.0)


def test_linear_calibration():
    # p / (λ L) = 0.1 / (0.0251 * 650.4)
    assert SYNERGY.inv_angstrom_per_pixel() == pytest.approx(0.1 / (0.0251 * 650.4), rel=1e-12)
    assert SYNERGY.inv_angstrom_per_pixel() == pytest.approx(6.1256e-3, rel=1e-4)


def test_ring_radius_matches_bragg_and_inverts():
    for d in (0.5, 0.8, 1.0, 1.2, 2.0, 5.0):
        r = SYNERGY.radius_px_for_resolution(d)
        # Independent derivation: 2θ from Bragg's law, R = L tan 2θ
        two_theta = 2 * math.asin(0.0251 / (2 * d))
        assert r == pytest.approx(650.4 * math.tan(two_theta) / 0.1, rel=1e-12)
        # Round trip radius -> resolution
        assert SYNERGY.resolution_at_radius_px(r) == pytest.approx(d, rel=1e-12)


def test_ring_radius_numbers_for_synergy():
    # 1.0 Å at 200 kV, L = 650.4 mm, p = 0.1 mm -> ~163.3 px; 0.8 Å -> ~204.1 px
    assert SYNERGY.radius_px_for_resolution(1.0) == pytest.approx(163.27, abs=0.05)
    assert SYNERGY.radius_px_for_resolution(0.8) == pytest.approx(204.09, abs=0.05)
    assert SYNERGY.radius_px_for_resolution(2.0) == pytest.approx(81.63, abs=0.05)


def test_small_angle_linear_vs_exact_is_tiny_for_electrons():
    # 1/d from the linear calibration vs the exact ring radius differ by ≈ 3/8 (R/L)^2
    for d in (0.5, 0.8, 1.0, 2.0):
        r = SYNERGY.radius_px_for_resolution(d)
        linear_recip = r * SYNERGY.inv_angstrom_per_pixel()
        rel = linear_recip / (1.0 / d) - 1.0
        x = r * 0.1 / 650.4
        assert rel == pytest.approx(3.0 / 8.0 * x * x, rel=0.02)
        assert abs(rel) < 1e-3


def test_unreachable_and_invalid_resolutions():
    assert SYNERGY.radius_px_for_resolution(0.01) is None  # λ/2d > 1
    assert SYNERGY.radius_px_for_resolution(0.0) is None
    assert SYNERGY.radius_px_for_resolution(-1.0) is None
    xray = DiffractionGeometry(50.0, 1.5406, 0.1, (0.0, 0.0))
    # 2θ >= 90° never reaches a flat detector facing the beam (d = λ/√2 is exactly 90°)
    assert xray.radius_px_for_resolution(1.5406 / math.sqrt(2) * 0.999) is None
    assert xray.radius_px_for_resolution(2.0) is not None


def test_resolution_at_centre_is_infinite():
    assert math.isinf(SYNERGY.resolution_at_radius_px(0.0))


def test_reciprocal_distance_centre_to_ring_is_one_over_d():
    for d in (0.8, 1.0, 2.0):
        r = SYNERGY.radius_px_for_resolution(d)
        cx, cy = SYNERGY.beam_center_px
        for ang in (0.0, 0.7, 2.0, 4.0):
            p = (cx + r * math.cos(ang), cy + r * math.sin(ang))
            assert SYNERGY.reciprocal_distance((cx, cy), p) == pytest.approx(1.0 / d, rel=1e-12)


def test_scattering_vector_on_ewald_sphere():
    # |k_in + s| = |k_out| = 1/λ for every detector point
    k = 1.0 / 0.0251
    for p in ((0.0, 0.0), (775.0, 385.0), (500.3, 12.7)):
        sx, sy, sz = SYNERGY.scattering_vector(*p)
        assert math.sqrt(sx ** 2 + sy ** 2 + (sz + k) ** 2) == pytest.approx(k, rel=1e-12)


def test_friedel_pair_spacing():
    # Spots at ±r through the centre: |s2 - s1| ≈ 2/d (exactly 2·sinθ·cosθ... check symmetry)
    r = SYNERGY.radius_px_for_resolution(1.0)
    cx, cy = SYNERGY.beam_center_px
    dist = SYNERGY.reciprocal_distance((cx - r, cy), (cx + r, cy))
    # In-plane components are equal and opposite, z components equal -> 2 * |s_xy|
    s = SYNERGY.scattering_vector(cx + r, cy)
    assert dist == pytest.approx(2.0 * math.hypot(s[0], s[1]), rel=1e-12)
    assert dist == pytest.approx(2.0, rel=1e-3)


def test_max_resolution_in_image():
    edge, corner = SYNERGY.max_resolution_in_image(775, 385)
    assert edge == pytest.approx(SYNERGY.resolution_at_radius_px(192.5), rel=1e-12)
    assert corner == pytest.approx(SYNERGY.resolution_at_radius_px(math.hypot(387.5, 192.5)), rel=1e-12)
    assert corner < edge


def test_resolve_header_geometry_with_binning():
    header = {
        "distance_mm": 643.9, "alpha1_wavelength": 0.0251, "real_px_size_x": 0.1,
        "real_px_size_y": 0.1, "origin_px_x": 387.5, "origin_px_y": 192.5, "bin_x": 1, "bin_y": 1,
        "direct_space_pixel_size_um": 0.0,
    }
    geo = resolve_header_geometry(header)
    assert geo == {"camera_length_mm": 643.9, "wavelength_angstrom": 0.0251,
                   "pixel_size_mm": 0.1, "beam_center_px": (387.5, 192.5)}
    assert looks_like_diffraction_header(header)
    binned = dict(header, bin_x=2, bin_y=2)
    assert resolve_header_geometry(binned)["beam_center_px"] == (193.75, 96.25)
    real_space = dict(header, direct_space_pixel_size_um=0.0356)
    assert not looks_like_diffraction_header(real_space)
    assert resolve_header_geometry({"distance_mm": 0.0}) == {}
    assert resolve_header_geometry(None) == {}


def test_format_resolution_label():
    assert format_resolution_label(1.0) == "1.0 Å"
    assert format_resolution_label(0.8) == "0.8 Å"
    assert format_resolution_label(2) == "2.0 Å"
    assert format_resolution_label(0.85) == "0.85 Å"


def test_format_reciprocal_value_keeps_significant_zeros():
    from core.diffraction import format_reciprocal_value
    assert format_reciprocal_value(1.0) == "1.00"
    assert format_reciprocal_value(0.5) == "0.500"
    assert format_reciprocal_value(10.0) == "10.0"
    assert format_reciprocal_value(1234.4) == "1234"
    assert format_reciprocal_value(float("inf")) == "\u221e"


def test_header_tilt_warning():
    from core.diffraction import header_tilt_warning
    # Rotation about the beam (e1) is in-plane and harmless
    assert header_tilt_warning({"detector_rotns": (2.9, 0.0, 0.0)}) is None
    assert header_tilt_warning({"detector_rotns": (0.0, 1.0, 0.0)}) is not None
    assert header_tilt_warning({"beam_rotn_around_e3": 0.5}) is not None


def test_image_processor_tracks_crop_and_flip():
    import numpy as np
    from core.image_processor import ImageProcessor
    rng = np.random.default_rng(0)
    for _ in range(50):
        h, w = 40, 60
        raw = np.zeros((h, w), dtype=np.uint16)
        j, i = int(rng.integers(5, h - 5)), int(rng.integers(5, w - 5))
        raw[j, i] = 1000
        p = ImageProcessor()
        p.raw_image = raw.copy()
        p._normalize_from_raw()
        p.apply_brightness_contrast()
        for _step in range(4):
            op = int(rng.integers(0, 4))
            if op == 0:
                p.flip_horizontal()
            elif op == 1:
                p.flip_vertical()
            elif op == 2:
                p.crop_rows(1, 1)
            else:
                p.crop_rectangle(1, 1, p.original_image.shape[1] - 1, p.original_image.shape[0] - 1)
        x, y = p.map_loaded_to_current(i + 0.5, j + 0.5)
        jj, ii = np.unravel_index(int(np.argmax(p.raw_image)), p.raw_image.shape)
        assert (x, y) == (ii + 0.5, jj + 0.5)
        assert np.argmax(p.original_image) == np.argmax(p.raw_image)
        assert p.map_current_to_loaded(x, y) == pytest.approx((i + 0.5, j + 0.5))


def test_log_scaling_reveals_weak_signal():
    import numpy as np
    from core.image_processor import ImageProcessor
    raw = np.zeros((10, 10), dtype=np.int32)
    raw[0, 0] = 100000  # direct beam
    raw[5, 5] = 50      # weak reflection
    p = ImageProcessor()
    p.raw_image = raw
    p.intensity_scaling = "Linear"
    p._normalize_from_raw()
    assert p.original_image[5, 5] == 0
    p.intensity_scaling = "Logarithmic"
    p._normalize_from_raw()
    assert p.original_image[5, 5] > 80
