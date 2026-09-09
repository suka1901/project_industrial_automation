"""Tests for fitting the camera frame on screen without breaking the maths.

The display scale is cosmetic, but the mapping back from it is not: a box
drawn on the preview searches the real frame, and getting that wrong points
the search a tenth of the way in from where the operator drew it.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from calibration.view import display_scale, shrink, to_full_resolution


def frame(width: int, height: int = 100):
    return np.zeros((height, width, 3), dtype=np.uint8)


class TestDisplayScale(unittest.TestCase):
    def test_a_frame_that_already_fits_is_not_scaled(self):
        self.assertEqual(display_scale(frame(800), width=1100), 1.0)

    def test_the_basler_frame_is_shrunk_to_the_display_width(self):
        self.assertAlmostEqual(display_scale(frame(2448), width=1100), 1100 / 2448)

    def test_never_enlarges_a_small_frame(self):
        self.assertEqual(display_scale(frame(320), width=1100), 1.0)

    def test_survives_a_missing_frame(self):
        self.assertEqual(display_scale(None), 1.0)


class TestShrink(unittest.TestCase):
    def test_produces_the_requested_width(self):
        small = shrink(frame(2448, 2048), 1100 / 2448)
        self.assertEqual(small.shape[1], 1100)

    def test_returns_a_copy_not_the_original(self):
        original = frame(800)
        self.assertIsNot(shrink(original, 1.0), original)


class TestToFullResolution(unittest.TestCase):
    """The one that matters: what the operator drew must land where they drew it."""

    def test_a_box_maps_back_onto_the_real_frame(self):
        scale = 1100 / 2448
        drawn = (110, 55, 220, 110)          # on the preview
        self.assertEqual(to_full_resolution(drawn, scale),
                         (245, 122, 490, 245))

    def test_the_centre_of_the_preview_is_the_centre_of_the_frame(self):
        scale = 1100 / 2448
        centre_on_preview = 550
        self.assertAlmostEqual(
            to_full_resolution((centre_on_preview, 0, 0, 0), scale)[0], 1224, delta=1)

    def test_an_unscaled_preview_maps_to_itself(self):
        self.assertEqual(to_full_resolution((10, 20, 30, 40), 1.0), (10, 20, 30, 40))

    def test_a_zero_scale_does_not_divide_by_zero(self):
        self.assertEqual(to_full_resolution((10, 20, 30, 40), 0.0), (10, 20, 30, 40))


if __name__ == "__main__":
    unittest.main()
