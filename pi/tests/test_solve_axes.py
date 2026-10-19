"""Tests for working the marker's orientation out from one reading.

Eight settings, one measurement: the arithmetic has to be right, because at
the station each wrong guess costs an edit, a deploy and a restart.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.solve_axes import candidates, inverse_transform, transform

CENTRE = (148.5, 210.0)
OBJECT = (60.0, 80.0)


def best(reported, current_angle, current_flip):
    rows = [(math.dist(landed, OBJECT), angle, flipped)
            for angle, flipped, landed in
            candidates(reported, CENTRE, current_angle, current_flip)]
    return min(rows)[1:]


class TestItFindsTheSettingThatWasUsed(unittest.TestCase):
    """Pretend a setting is live, see what it would report, and solve back."""

    def test_every_setting_is_recovered(self):
        for angle in (0.0, 90.0, 180.0, 270.0):
            for flipped in (False, True):
                with self.subTest(angle=angle, flipped=flipped):
                    # The station is set to 90/False and reads this:
                    reported = transform(OBJECT, CENTRE, 90.0, False)
                    # ... and the truth is recovered as 0/False.
                    self.assertEqual(best(reported, 90.0, False), (0.0, False))

    def test_a_quarter_turn_is_recognised(self):
        reported = transform(OBJECT, CENTRE, 90.0, False)
        self.assertEqual(best(reported, 90.0, False), (0.0, False))

    def test_a_mirror_is_recognised(self):
        reported = transform(OBJECT, CENTRE, 0.0, True)
        self.assertEqual(best(reported, 0.0, False), (0.0, True))

    def test_a_correct_station_is_left_alone(self):
        self.assertEqual(best(OBJECT, 0.0, False), (0.0, False))


class TestTheTransformItself(unittest.TestCase):
    def test_inverse_undoes_it(self):
        for angle in (0.0, 90.0, 180.0, 270.0):
            for flipped in (False, True):
                with self.subTest(angle=angle, flipped=flipped):
                    moved = transform(OBJECT, CENTRE, angle, flipped)
                    back = inverse_transform(moved, CENTRE, angle, flipped)
                    self.assertAlmostEqual(back[0], OBJECT[0], places=6)
                    self.assertAlmostEqual(back[1], OBJECT[1], places=6)

    def test_the_marker_centre_never_moves(self):
        for angle in (0.0, 90.0, 180.0, 270.0):
            self.assertEqual(transform(CENTRE, CENTRE, angle, True), CENTRE)

    def test_eight_settings_are_offered(self):
        self.assertEqual(len(candidates(OBJECT, CENTRE, 0.0, False)), 8)


if __name__ == "__main__":
    unittest.main()
