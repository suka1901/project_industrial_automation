"""Tests for averaging angles that wrap at a shape's symmetry period.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.angles import circular_mean_deg, circular_spread_deg
from domain.enums import Shape

SQUARE = Shape.SQUARE.symmetry_period_deg     # 90
STAR = Shape.STAR.symmetry_period_deg         # 72


class TestCircularMean(unittest.TestCase):
    def test_readings_that_do_not_wrap_average_normally(self):
        self.assertAlmostEqual(circular_mean_deg([10.0, 12.0, 11.0], SQUARE), 11.0, places=2)

    def test_readings_either_side_of_the_period_do_not_average_to_the_middle(self):
        """The reason this module exists: 89 and 1 are the same corner of a
        square, so they must not average to 45."""
        mean = circular_mean_deg([89.0, 1.0], SQUARE)
        self.assertNotAlmostEqual(mean, 45.0, places=1)
        self.assertAlmostEqual(min(mean, SQUARE - mean), 0.0, places=2)

    def test_a_full_period_reads_as_zero_not_as_the_period(self):
        self.assertAlmostEqual(circular_mean_deg([89.0, 1.0, 90.0], SQUARE), 0.0, places=2)

    def test_the_star_wraps_at_its_own_period(self):
        mean = circular_mean_deg([71.0, 1.0], STAR)
        self.assertAlmostEqual(min(mean, STAR - mean), 0.0, places=2)

    def test_a_single_reading_is_itself(self):
        self.assertAlmostEqual(circular_mean_deg([37.5], SQUARE), 37.5, places=2)

    def test_no_readings_is_zero_not_an_error(self):
        self.assertEqual(circular_mean_deg([], SQUARE), 0.0)

    def test_a_shape_with_no_orientation_is_zero(self):
        self.assertEqual(circular_mean_deg([12.0, 30.0], 0.0), 0.0)


class TestCircularSpread(unittest.TestCase):
    """The spread is what says whether one stored slot angle can be trusted."""

    def test_identical_readings_have_no_spread(self):
        self.assertAlmostEqual(circular_spread_deg([20.0] * 5, SQUARE), 0.0, places=3)

    def test_a_tight_slot_reports_a_small_spread(self):
        self.assertLess(circular_spread_deg([20.0, 20.4, 19.7, 20.1], SQUARE), 1.0)

    def test_a_loose_slot_reports_a_large_one(self):
        self.assertGreater(circular_spread_deg([10.0, 22.0, 4.0, 18.0], SQUARE), 5.0)

    def test_wrapping_readings_are_tight_not_scattered(self):
        """89 and 1 are half a degree apart on a square, not 88 degrees."""
        self.assertLess(circular_spread_deg([89.5, 0.5, 90.0, 0.0], SQUARE), 2.0)

    def test_one_reading_cannot_show_any_spread(self):
        self.assertEqual(circular_spread_deg([42.0], SQUARE), 0.0)

    def test_evenly_scattered_readings_saturate(self):
        self.assertAlmostEqual(circular_spread_deg([0.0, 30.0, 60.0], SQUARE),
                               SQUARE / 2.0, places=2)


if __name__ == "__main__":
    unittest.main()
