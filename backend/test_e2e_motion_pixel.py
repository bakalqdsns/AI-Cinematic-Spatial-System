"""Pixel-level integration test for segment_person_from_frame.

Builds a synthetic frame with a clearly-bounded circular "character" on a
contrasting (green) background and runs ``segment_person_from_frame`` with
various flag combinations to verify:

  * ``feather_edges=False`` produces a binary-ish alpha;
  * ``feather_edges=True`` produces a softer, *different* alpha (the
    ``refine_mask_edges`` snap actually moves pixels);
  * ``greenscreen=True`` zeroes alpha on the green background regardless of
    the SAM2 mask (chroma key overrides);
  * ``greenscreen=False`` keeps alpha from the SAM2 mask alone;
  * the resulting PNG is well-formed (4-channel uint8, BGRA shape).
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _make_synthetic_frame(path: Path, size: int = 256) -> tuple[int, int, int, int]:
    """Build a synthetic BGR frame: solid green background + central circle."""
    green_bg_bgr = (0, 255, 0)        # BGR pure green
    character_bgr = (180, 100, 80)    # BGR (blueish gray)

    img = np.zeros((size, size, 3), dtype=np.uint8)
    img[:] = green_bg_bgr

    # Draw a filled circle in the center to represent the person
    yy, xx = np.ogrid[:size, :size]
    cy, cx = size // 2, size // 2
    radius = size // 4
    mask_circle = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius ** 2
    img[mask_circle] = character_bgr

    cv2 = _lazy_cv2()
    cv2.imwrite(str(path), img)
    return cy, cx, radius, size


def _lazy_cv2():
    import cv2
    return cv2


class _Sam2Mock:
    """SAM2 mock: returns a near-circular mask covering the person region."""

    def __init__(self, cy: int, cx: int, radius: int, size: int):
        self.cy = cy
        self.cx = cx
        self.radius = radius
        self.size = size

    def predict_automatic_masks(self, image):
        seg = np.zeros((image.shape[0], image.shape[1]), dtype=bool)
        yy, xx = np.ogrid[: self.size, : self.size]
        # Slightly shrunken mask so refine_mask_edges has room to snap outward
        seg[(yy - self.cy) ** 2 + (xx - self.cx) ** 2 <= (self.radius - 4) ** 2] = True
        area = int(seg.sum())
        return [{"segmentation": seg, "area": area}]


def _read_alpha(png_path: Path) -> np.ndarray:
    img = Image.open(str(png_path))
    arr = np.array(img)
    if arr.ndim == 2:  # grayscale → no alpha
        return np.zeros(arr.shape, dtype=np.uint8)
    if arr.shape[2] == 4:
        return arr[:, :, 3]
    return np.zeros(arr.shape[:2], dtype=np.uint8)


def _diff_fraction(a: np.ndarray, b: np.ndarray) -> float:
    return float((a != b).sum()) / float(a.size)


def test_segment_no_feather_no_gs(tmp_path):
    from app.services.motion_extractor import segment_person_from_frame

    frame = tmp_path / "frame.png"
    cy, cx, r, sz = _make_synthetic_frame(frame)
    sam = _Sam2Mock(cy, cx, r, sz)

    out = tmp_path / "no_feather_no_gs.png"
    ok = segment_person_from_frame(
        str(frame), str(out), sam,
        feather_edges=False, greenscreen=False,
    )
    assert ok, "segment_person_from_frame must succeed"
    alpha = _read_alpha(out)
    assert alpha.shape == (sz, sz)
    # Alpha must not be entirely zero (something was segmented)
    assert alpha.sum() > 0
    # Alpha must not be entirely 255 (background was excluded)
    assert (alpha == 255).sum() < alpha.size
    # No greenscreen → green pixels keep SAM2 alpha, which is 0 outside the circle
    # The green region must have alpha == 0
    assert (alpha == 0).sum() > 0


def test_segment_with_feather_changes_alpha(tmp_path):
    from app.services.motion_extractor import segment_person_from_frame

    frame = tmp_path / "frame.png"
    cy, cx, r, sz = _make_synthetic_frame(frame)
    sam = _Sam2Mock(cy, cx, r, sz)

    out_a = tmp_path / "no_feather.png"
    out_b = tmp_path / "with_feather.png"

    ok_a = segment_person_from_frame(
        str(frame), str(out_a), sam,
        feather_edges=False, greenscreen=False,
    )
    ok_b = segment_person_from_frame(
        str(frame), str(out_b), sam,
        feather_edges=True, greenscreen=False,
    )
    assert ok_a and ok_b

    alpha_a = _read_alpha(out_a)
    alpha_b = _read_alpha(out_b)
    diff = _diff_fraction(alpha_a, alpha_b)
    # Feathering must measurably alter at least 0.1% of pixels
    assert diff > 1e-4, f"feather=off vs on produced identical alpha (diff={diff})"


def test_segment_greenscreen_zeros_green_background(tmp_path):
    from app.services.motion_extractor import segment_person_from_frame

    frame = tmp_path / "frame.png"
    cy, cx, r, sz = _make_synthetic_frame(frame)
    sam = _Sam2Mock(cy, cx, r, sz)

    out = tmp_path / "gs.png"
    ok = segment_person_from_frame(
        str(frame), str(out), sam,
        feather_edges=False, greenscreen=True,
    )
    assert ok
    alpha = _read_alpha(out)

    img = np.array(Image.open(str(out)))
    assert img.shape[2] == 4
    bgr = img[:, :, :3]

    # Identify clearly-green pixels (pure BGR 0,255,0 in our synthetic image)
    green_mask = (bgr[:, :, 0] == 0) & (bgr[:, :, 1] == 255) & (bgr[:, :, 2] == 0)
    assert green_mask.sum() > 0, "synthetic frame must contain green pixels"

    # All pure-green pixels must have alpha == 0 (chroma key removes them)
    green_alphas = alpha[green_mask]
    assert (green_alphas == 0).all(), (
        f"chroma key left non-zero alpha on {int((green_alphas != 0).sum())} green pixels"
    )


def test_segment_greenscreen_keeps_non_green(tmp_path):
    from app.services.motion_extractor import segment_person_from_frame

    frame = tmp_path / "frame.png"
    cy, cx, r, sz = _make_synthetic_frame(frame)
    sam = _Sam2Mock(cy, cx, r, sz)

    out = tmp_path / "gs_keep.png"
    ok = segment_person_from_frame(
        str(frame), str(out), sam,
        feather_edges=False, greenscreen=True,
    )
    assert ok
    alpha = _read_alpha(out)
    img = np.array(Image.open(str(out)))
    bgr = img[:, :, :3]

    # The character is BGR (180, 100, 80). After chroma-key threshold=80,
    # distances > 100 from pure green keep alpha == 255.
    yy, xx = np.ogrid[:sz, :sz]
    center_mask = (yy - sz // 2) ** 2 + (xx - sz // 2) ** 2 <= (r // 2) ** 2
    if center_mask.sum() > 0:
        center_alphas = alpha[center_mask]
        # At least some center pixels must remain opaque
        assert (center_alphas == 255).sum() > 0


def test_segment_png_shape_and_dtype(tmp_path):
    from app.services.motion_extractor import segment_person_from_frame

    frame = tmp_path / "frame.png"
    cy, cx, r, sz = _make_synthetic_frame(frame)
    sam = _Sam2Mock(cy, cx, r, sz)
    out = tmp_path / "shape.png"
    segment_person_from_frame(
        str(frame), str(out), sam,
        feather_edges=True, greenscreen=True,
    )
    img = Image.open(str(out))
    assert img.mode == "RGBA"
    arr = np.array(img)
    assert arr.dtype == np.uint8
    assert arr.ndim == 3 and arr.shape[2] == 4


if __name__ == "__main__":
    import tempfile
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
