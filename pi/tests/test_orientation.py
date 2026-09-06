"""Tests for harmonic orientation, on shapes built on paper.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import math
import sys
import unittest
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.enums import Shape
from domain.orientation import harmonic_orientation, resample_radial


def polygon(vertices: List[Tuple[float, float]], per_edge: int = 60):
    """Densely sample the edges of a polygon, as a contour tracer would."""
    points = []
    count = len(vertices)
    for index in range(count):
        x0, y0 = vertices[index]
        x1, y1 = vertices[(index + 1) % count]
        for step in range(per_edge):
            weight = step / per_edge
            points.append((x0 + (x1 - x0) * weight, y0 + (y1 - y0) * weight))
    return points


def star_outline(rotation_deg: float, points: int = 5,
                 outer: float = 50.0, inner: float = 21.0):
    """A five-pointed star, rotated by rotation_deg about its centre."""
    offset = math.radians(rotation_deg)
    vertices = []
    for index in range(points * 2):
        radius = outer if index % 2 == 0 else inner
        angle = offset + index * math.pi / points
        vertices.append((radius * math.cos(angle), radius * math.sin(angle)))
    return polygon(vertices)


def regular_outline(sides: int, rotation_deg: float, radius: float = 50.0):
    """A regular polygon - square, triangle, hexagon - rotated by rotation_deg."""
    offset = math.radians(rotation_deg)
    vertices = [
        (radius * math.cos(offset + index * 2 * math.pi / sides),
         radius * math.sin(offset + index * 2 * math.pi / sides))
        for index in range(sides)
    ]
    return polygon(vertices)


def circle_outline(radius: float = 50.0, samples: int = 600):
    return [(radius * math.cos(2 * math.pi * i / samples),
             radius * math.sin(2 * math.pi * i / samples))
            for i in range(samples)]


def measure(points, order: int):
    """Run the full pipeline on an outline centred on the origin."""
    samples = [(math.atan2(y, x), math.hypot(x, y)) for x, y in points]
    radii = resample_radial(samples)
    assert radii is not None
    return harmonic_orientation(radii, order)


def rotation_between(before: float, after: float, period: float) -> float:
    """Smallest signed change from one folded angle to another."""
    delta = (after - before) % period
    if delta > period / 2:
        delta -= period
    return delta


class TestStar(unittest.TestCase):
    """The star is the hard case: 72 degree symmetry, and thin points."""

    def test_recovers_a_known_rotation(self):
        period = Shape.STAR.symmetry_period_deg
        base, _ = measure(star_outline(0.0), Shape.STAR.symmetry_order)
        for applied in (5.0, 12.0, 20.0, 33.0):
            turned, _ = measure(star_outline(applied), Shape.STAR.symmetry_order)
            self.assertAlmostEqual(
                rotation_between(base, turned, period), applied, places=1,
                msg=f"failed to recover a {applied} degree rotation",
            )

    def test_a_full_symmetry_period_looks_identical(self):
        # Turning a star by 72 degrees produces the same star, so the estimator
        # must report the same angle - this is what makes the wrist correction
        # small instead of nearly a full turn.
        first, _ = measure(star_outline(14.0), Shape.STAR.symmetry_order)
        second, _ = measure(star_outline(14.0 + 72.0), Shape.STAR.symmetry_order)
        self.assertAlmostEqual(
            rotation_between(first, second, 72.0), 0.0, places=2
        )

    def test_answer_is_always_inside_the_symmetry_period(self):
        limit = Shape.STAR.symmetry_period_deg / 2.0
        for applied in range(0, 360, 7):
            angle, _ = measure(star_outline(float(applied)),
                               Shape.STAR.symmetry_order)
            self.assertLessEqual(abs(angle), limit + 1e-6)

    def test_confidence_is_high(self):
        _, confidence = measure(star_outline(0.0), Shape.STAR.symmetry_order)
        self.assertGreater(confidence, 0.15)


class TestOtherShapes(unittest.TestCase):
    def test_square_triangle_and_hexagon_recover_their_rotation(self):
        cases = [(Shape.SQUARE, 4), (Shape.TRIANGLE, 3), (Shape.HEXAGON, 6)]
        for shape, sides in cases:
            period = shape.symmetry_period_deg
            base, _ = measure(regular_outline(sides, 0.0), shape.symmetry_order)
            turned, _ = measure(regular_outline(sides, 11.0), shape.symmetry_order)
            self.assertAlmostEqual(
                rotation_between(base, turned, period), 11.0, places=1,
                msg=f"{shape.value} lost its rotation",
            )

    def test_a_circle_has_almost_no_orientation_signal(self):
        # Every shape is measured against its own harmonic; a circle has none,
        # so the confidence collapses and the caller knows not to rotate.
        for order in (3, 4, 5, 6):
            _, confidence = measure(circle_outline(), order)
            self.assertLess(confidence, 0.05,
                            f"a circle should not look {order}-fold symmetric")


class TestResampling(unittest.TestCase):
    def test_refuses_a_signature_with_too_many_gaps(self):
        # A handful of points spread over a few directions is not an outline.
        samples = [(0.1, 10.0), (0.2, 10.0), (0.3, 10.0)]
        self.assertIsNone(resample_radial(samples))

    def test_fills_small_gaps_by_interpolation(self):
        samples = [(2 * math.pi * i / 200, 40.0) for i in range(200)]
        radii = resample_radial(samples, bins=180)
        self.assertIsNotNone(radii)
        assert radii is not None
        self.assertEqual(len(radii), 180)
        for value in radii:
            self.assertAlmostEqual(value, 40.0, places=6)


if __name__ == "__main__":
    unittest.main()
