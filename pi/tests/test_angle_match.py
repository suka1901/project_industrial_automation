"""Tests for matching the camera's rotation sense to the robot's.

The arithmetic decides angle_sign, so it is worth more than the camera work
around it. Two cycles, two unknowns: a single reading cannot separate the sign
from the fixed wrist offset, and the script has to say so rather than pick one.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calibration.angle_match import Row, commands_in, fit, fold

SQUARE = 90.0
STAR = 72.0


def cycle(picked, rz, sign, offset, period):
    """What the camera would see if the cell behaved with this sign."""
    return Row(picked=picked, placed=fold(picked + sign * rz + offset, period),
               rz=rz)


class TestFolding(unittest.TestCase):

    def test_inside_the_period_is_unchanged(self):
        self.assertAlmostEqual(fold(20.0, SQUARE), 20.0)

    def test_past_half_the_period_comes_back_negative(self):
        self.assertAlmostEqual(fold(80.0, SQUARE), -10.0)

    def test_a_whole_period_is_zero(self):
        self.assertAlmostEqual(fold(90.0, SQUARE), 0.0)

    def test_a_star_folds_at_seventy_two(self):
        self.assertAlmostEqual(fold(70.0, STAR), -2.0)


class TestReadingRzFromTheLog(unittest.TestCase):

    def test_it_reads_the_line_the_commander_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ina700.log"
            path.write_text(
                "15:00:01 WARNING [cycle] adapters.comms.robot_commander: "
                "-> move square 112.40 308.10 19.3#\n"
                "15:00:09 WARNING [cycle] adapters.comms.robot_commander: "
                "<- DONE: square#\n"
                "15:01:02 WARNING [cycle] adapters.comms.robot_commander: "
                "-> move star 88.10 210.40 -7.5#\n", encoding="utf-8")
            self.assertEqual(commands_in(path),
                             [("square", 19.3), ("star", -7.5)])

    def test_a_missing_log_is_empty_rather_than_an_error(self):
        self.assertEqual(commands_in(Path("/no/such/log")), [])


class TestFittingTheSign(unittest.TestCase):

    def test_it_recovers_a_positive_sign(self):
        rows = [cycle(0.0, 20.0, +1, 1.5, SQUARE),
                cycle(30.0, -15.0, +1, 1.5, SQUARE)]
        outcome = fit(rows, SQUARE)
        self.assertEqual(outcome["verdict"], "ok")
        self.assertEqual(outcome["angle_sign"], 1)
        self.assertAlmostEqual(outcome["offset"], 1.5, places=4)

    def test_it_recovers_a_negative_sign(self):
        rows = [cycle(0.0, 20.0, -1, 1.5, SQUARE),
                cycle(30.0, -15.0, -1, 1.5, SQUARE)]
        outcome = fit(rows, SQUARE)
        self.assertEqual(outcome["verdict"], "ok")
        self.assertEqual(outcome["angle_sign"], -1)

    def test_one_cycle_is_refused(self):
        """One equation, two unknowns - the honest answer is 'not yet'."""
        outcome = fit([cycle(0.0, 20.0, +1, 1.5, SQUARE)], SQUARE)
        self.assertIn("two cycles", outcome["verdict"])

    def test_two_similar_rz_values_cannot_decide(self):
        rows = [cycle(0.0, 20.0, +1, 1.5, SQUARE),
                cycle(5.0, 22.0, +1, 1.5, SQUARE)]
        self.assertIn("almost the same rz", fit(rows, SQUARE)["verdict"])

    def test_a_wrist_that_never_turns_is_named(self):
        """The failure actually seen: rz varies, the object does not move."""
        rows = [Row(picked=0.0, placed=1.5, rz=20.0),
                Row(picked=30.0, placed=31.5, rz=-15.0)]
        verdict = fit(rows, SQUARE)["verdict"]
        self.assertIn("NOT TURNING", verdict)
        self.assertNotIn("angle_sign", fit(rows, SQUARE))

    def test_noisy_readings_still_agree(self):
        rows = [Row(picked=0.0, placed=fold(0.0 + 20.0 + 1.5 + 0.3, SQUARE), rz=20.0),
                Row(picked=30.0, placed=fold(30.0 - 15.0 + 1.5 - 0.4, SQUARE), rz=-15.0),
                Row(picked=-12.0, placed=fold(-12.0 + 25.0 + 1.5 + 0.2, SQUARE), rz=25.0)]
        outcome = fit(rows, SQUARE)
        self.assertEqual(outcome["verdict"], "ok")
        self.assertEqual(outcome["angle_sign"], 1)
        self.assertLess(outcome["spread"], 1.0)

    def test_the_wrong_sign_is_clearly_worse(self):
        rows = [cycle(0.0, 20.0, +1, 1.5, SQUARE),
                cycle(30.0, -15.0, +1, 1.5, SQUARE)]
        outcome = fit(rows, SQUARE)
        self.assertGreater(outcome["margin"], 10.0)

    def test_a_star_is_fitted_on_its_own_period(self):
        rows = [cycle(0.0, 18.0, -1, 1.5, STAR),
                cycle(25.0, -12.0, -1, 1.5, STAR)]
        outcome = fit(rows, STAR)
        self.assertEqual(outcome["verdict"], "ok")
        self.assertEqual(outcome["angle_sign"], -1)


if __name__ == "__main__":
    unittest.main()
