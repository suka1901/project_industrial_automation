"""Tests for the guard that catches an unpasted slot-angle measurement.

calibration/slot_angles.py writes a block for pasting into config.yaml, and
nothing reads that file at run time. Forgetting the paste is silent: every
object is then placed unrotated, which looks like a calibration fault rather
than a missed step, and it would only show up at the rehearsal.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.preflight import FAIL, PASS, SKIP, judge_slot_angles

GOOD = {"SQUARE": {"seatings": 4, "play_deg": 0.61},
        "STAR": {"seatings": 5, "play_deg": 0.44}}


class TestJudgeSlotAngles(unittest.TestCase):

    def test_measured_but_not_pasted_fails(self):
        status, detail = judge_slot_angles(
            {"SQUARE": 0.0, "STAR": 0.0}, {"SQUARE": 49.32}, GOOD)
        self.assertEqual(status, FAIL)
        self.assertIn("NOT PASTED", detail)
        self.assertIn("49.32", detail)

    def test_pasted_and_well_measured_passes(self):
        status, detail = judge_slot_angles(
            {"CIRCLE": 0.0, "SQUARE": 49.32, "STAR": 12.0},
            {"CIRCLE": 0.0, "SQUARE": 49.32, "STAR": 12.0}, GOOD)
        self.assertEqual(status, PASS)
        self.assertIn("0.61", detail)

    def test_a_shape_that_was_never_measured_fails(self):
        status, detail = judge_slot_angles(
            {"SQUARE": 49.32, "STAR": 0.0}, {"SQUARE": 49.32},
            {"SQUARE": {"seatings": 4}})
        self.assertEqual(status, FAIL)
        self.assertIn("STAR", detail)
        self.assertIn("unrotated", detail)

    def test_too_few_seatings_is_flagged_but_not_fatal(self):
        status, detail = judge_slot_angles(
            {"SQUARE": 49.32, "STAR": 12.0},
            {"SQUARE": 49.32, "STAR": 12.0},
            {"SQUARE": {"seatings": 1}, "STAR": {"seatings": 5}})
        self.assertEqual(status, SKIP)
        self.assertIn("SQUARE", detail)
        self.assertNotIn("STAR", detail)

    def test_the_circle_is_never_complained_about(self):
        """A circle is legitimately 0.0 with one seating - it has no angle."""
        status, _ = judge_slot_angles(
            {"CIRCLE": 0.0, "SQUARE": 49.32}, {"CIRCLE": 0.0, "SQUARE": 49.32},
            {"CIRCLE": {"seatings": 1}, "SQUARE": {"seatings": 4}})
        self.assertEqual(status, PASS)

    def test_a_small_rounding_difference_is_not_a_missed_paste(self):
        status, _ = judge_slot_angles(
            {"SQUARE": 49.32}, {"SQUARE": 49.325}, {"SQUARE": {"seatings": 4}})
        self.assertEqual(status, PASS)

    def test_a_real_difference_is(self):
        status, detail = judge_slot_angles(
            {"SQUARE": 49.32}, {"SQUARE": 51.00}, {"SQUARE": {"seatings": 4}})
        self.assertEqual(status, FAIL)
        self.assertIn("NOT PASTED", detail)


if __name__ == "__main__":
    unittest.main()
