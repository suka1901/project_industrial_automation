"""Tests for the ArUco marker geometry.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import math
import unittest

from domain.marker import marker_world_corners, pixel_mm_ratio_from_perimeter


class TestMarkerWorldCorners(unittest.TestCase):
    def test_axis_aligned_marker_at_origin(self):
        corners = marker_world_corners(100.0, (0.0, 0.0))
        # OpenCV order: top-left, top-right, bottom-right, bottom-left.
        self.assertEqual(corners, [(-50.0, 50.0), (50.0, 50.0),
                                   (50.0, -50.0), (-50.0, -50.0)])

    def test_translation_moves_every_corner(self):
        corners = marker_world_corners(100.0, (200.0, -80.0))
        for (x, y), (base_x, base_y) in zip(
            corners, marker_world_corners(100.0, (0.0, 0.0))
        ):
            self.assertAlmostEqual(x, base_x + 200.0)
            self.assertAlmostEqual(y, base_y - 80.0)

    def test_ninety_degree_rotation(self):
        corners = marker_world_corners(100.0, (0.0, 0.0), angle_deg=90.0)
        # Top-left (-50, 50) rotated 90 deg CCW becomes (-50, -50).
        self.assertAlmostEqual(corners[0][0], -50.0, places=6)
        self.assertAlmostEqual(corners[0][1], -50.0, places=6)

    def test_y_axis_flip_mirrors_vertically(self):
        normal = marker_world_corners(100.0, (0.0, 0.0))
        flipped = marker_world_corners(100.0, (0.0, 0.0), y_axis_flipped=True)
        for (_, y_n), (_, y_f) in zip(normal, flipped):
            self.assertAlmostEqual(y_n, -y_f)

    def test_side_length_is_preserved_under_rotation(self):
        corners = marker_world_corners(80.0, (10.0, 20.0), angle_deg=37.0)
        edge = math.dist(corners[0], corners[1])
        self.assertAlmostEqual(edge, 80.0, places=6)

    def test_rejects_non_positive_length(self):
        with self.assertRaises(ValueError):
            marker_world_corners(0.0, (0.0, 0.0))


class TestPixelRatio(unittest.TestCase):
    def test_matches_the_course_formula(self):
        # A 100 mm marker whose perimeter measures 800 px is 2 px per mm.
        self.assertAlmostEqual(pixel_mm_ratio_from_perimeter(800.0, 100.0), 2.0)

    def test_rejects_non_positive_length(self):
        with self.assertRaises(ValueError):
            pixel_mm_ratio_from_perimeter(800.0, 0.0)


if __name__ == "__main__":
    unittest.main()
