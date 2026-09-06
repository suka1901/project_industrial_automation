"""Tests for the rotation maths.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest

from domain.enums import Shape
from domain.geometry import normalise_for_shape, wrap_deg


class TestWrap(unittest.TestCase):
    def test_wraps_into_period(self):
        self.assertAlmostEqual(wrap_deg(100.0, 90.0), 10.0)
        self.assertAlmostEqual(wrap_deg(-10.0, 90.0), 80.0)

    def test_zero_period_is_free(self):
        self.assertEqual(wrap_deg(123.0, 0.0), 0.0)


class TestNormaliseForShape(unittest.TestCase):
    def test_circle_never_rotates(self):
        self.assertEqual(normalise_for_shape(137.0, Shape.CIRCLE), 0.0)

    def test_square_takes_the_short_way(self):
        # 80 degrees on a square is the same as -10 degrees, which the wrist
        # reaches far more easily.
        self.assertAlmostEqual(normalise_for_shape(80.0, Shape.SQUARE), -10.0)

    def test_square_full_period_is_zero(self):
        self.assertAlmostEqual(normalise_for_shape(90.0, Shape.SQUARE), 0.0)

    def test_star_uses_72_degree_period(self):
        self.assertAlmostEqual(normalise_for_shape(72.0, Shape.STAR), 0.0)
        self.assertAlmostEqual(normalise_for_shape(75.0, Shape.STAR), 3.0)

    def test_triangle_uses_120_degree_period(self):
        self.assertAlmostEqual(normalise_for_shape(121.0, Shape.TRIANGLE), 1.0)

    def test_slot_angle_is_subtracted(self):
        self.assertAlmostEqual(
            normalise_for_shape(50.0, Shape.SQUARE, slot_angle_deg=45.0), 5.0
        )

    def test_result_always_within_half_period(self):
        for angle in range(0, 360, 7):
            value = normalise_for_shape(float(angle), Shape.HEXAGON)
            self.assertLessEqual(abs(value), 30.0 + 1e-9)


if __name__ == "__main__":
    unittest.main()


class TestPlaceRotation(unittest.TestCase):
    """The vacuum gripper picks straight down, so all turning happens at placing."""

    def test_circle_never_needs_rotation(self):
        from domain.geometry import place_rotation_deg
        self.assertEqual(place_rotation_deg(137.0, Shape.CIRCLE), 0.0)

    def test_square_turned_ten_degrees_is_corrected_back(self):
        from domain.geometry import place_rotation_deg
        # Object lying at +10 deg must be turned -10 deg to seat in a slot at 0.
        self.assertAlmostEqual(place_rotation_deg(10.0, Shape.SQUARE), -10.0)

    def test_square_near_the_next_face_takes_the_short_way(self):
        from domain.geometry import place_rotation_deg
        # 80 deg is the same square as -10 deg, so a +10 deg turn is enough.
        self.assertAlmostEqual(place_rotation_deg(80.0, Shape.SQUARE), 10.0)

    def test_slot_angle_is_respected(self):
        from domain.geometry import place_rotation_deg
        # An object already at 0 must turn +45 to meet a slot cut at 45.
        self.assertAlmostEqual(
            place_rotation_deg(0.0, Shape.SQUARE, slot_angle_deg=45.0), 45.0
        )

    def test_rotation_always_seats_the_object(self):
        """The defining property: object + rotation must equal the slot angle,"""
        from domain.geometry import place_rotation_deg, wrap_deg
        for shape in (Shape.SQUARE, Shape.TRIANGLE, Shape.STAR, Shape.HEXAGON):
            period = shape.symmetry_period_deg
            for object_angle in range(0, 360, 11):
                for slot_angle in (0.0, 17.0, 45.0):
                    rotation = place_rotation_deg(
                        float(object_angle), shape, slot_angle
                    )
                    residual = wrap_deg(
                        object_angle + rotation - slot_angle, period
                    )
                    # Either exactly aligned, or one full period away from it.
                    self.assertTrue(
                        min(residual, period - residual) < 1e-6,
                        f"{shape} object={object_angle} slot={slot_angle} "
                        f"rotation={rotation} residual={residual}",
                    )

    def test_rotation_never_exceeds_half_a_period(self):
        from domain.geometry import place_rotation_deg
        for shape in (Shape.SQUARE, Shape.TRIANGLE, Shape.STAR, Shape.HEXAGON):
            limit = shape.symmetry_period_deg / 2.0
            for object_angle in range(0, 360, 7):
                rotation = place_rotation_deg(float(object_angle), shape)
                self.assertLessEqual(abs(rotation), limit + 1e-9)
