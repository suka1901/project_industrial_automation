"""Tests for the lighting meter's judgements.

The meter exists to turn "does this look bright enough" into a number, so
what is tested is the boundaries of that number: the band it calls good, and
the contrast below which no segmentation can find an outline at all. Both
come from measurements over the labelled photos, and both are repeated in
LAB.md - a test is what keeps the three in step.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.light_meter import (CONTRAST_GOOD, CONTRAST_POOR, contrast_verdict,
                               crop_of, sheet_brightness, sheet_verdict)
from tools.preflight import SHEET_BRIGHT_MAX, SHEET_BRIGHT_MIN
from domain.models import BoundingBox


class TestWhatItSaysAboutTheSheet(unittest.TestCase):

    def test_the_middle_of_the_band_is_good(self):
        middle = (SHEET_BRIGHT_MIN + SHEET_BRIGHT_MAX) / 2.0
        self.assertEqual(sheet_verdict(middle, 0.0), "good")

    def test_a_dark_sheet_is_told_how_much_more_light_it_needs(self):
        verdict = sheet_verdict(SHEET_BRIGHT_MIN / 2.0, 0.0)
        self.assertIn("TOO DARK", verdict)
        # The factor is the point: a verdict without it is just a complaint.
        self.assertIn("x more light", verdict)

    def test_clipping_outranks_brightness(self):
        # Bright AND clipped: the clipping is the thing to fix, because no
        # exposure change can recover what the sensor has already flattened.
        self.assertIn("CLIPPING", sheet_verdict(SHEET_BRIGHT_MAX - 1.0, 5.0))

    def test_a_blown_out_sheet_is_not_called_good(self):
        self.assertNotEqual(sheet_verdict(SHEET_BRIGHT_MAX + 10.0, 0.0), "good")


class TestWhatItSaysAboutAnObject(unittest.TestCase):

    def test_below_the_floor_there_is_no_edge_to_find(self):
        self.assertEqual(contrast_verdict(CONTRAST_POOR - 1.0), "no edge to find")

    def test_above_the_ceiling_it_is_good(self):
        self.assertEqual(contrast_verdict(CONTRAST_GOOD + 1.0), "good")

    def test_between_them_it_is_marginal(self):
        self.assertEqual(
            contrast_verdict((CONTRAST_POOR + CONTRAST_GOOD) / 2.0), "marginal")


class TestTheCropItMeasures(unittest.TestCase):
    """The same pixels the orientation estimator reads, or the contrast it
    prints would describe a different picture from the fit beside it."""

    def test_the_padding_is_included(self):
        image = np.zeros((200, 200, 3), np.uint8)
        crop = crop_of(image, BoundingBox(50.0, 60.0, 90.0, 100.0))
        self.assertEqual(crop.shape[:2], (48, 48))        # 40 plus 4 each side

    def test_it_stops_at_the_frame_edge(self):
        image = np.zeros((100, 100, 3), np.uint8)
        crop = crop_of(image, BoundingBox(0.0, 0.0, 100.0, 100.0))
        self.assertEqual(crop.shape[:2], (100, 100))

    def test_there_is_nothing_to_measure_without_a_box(self):
        self.assertIsNone(crop_of(np.zeros((10, 10, 3), np.uint8), None))


class TestTheSheetReading(unittest.TestCase):

    def test_it_reads_the_paper_and_not_the_table(self):
        # A dark table with a bright sheet over a quarter of it: the 95th
        # percentile must describe the sheet, which is what the lamp lights.
        image = np.full((100, 100, 3), 20, np.uint8)
        image[:50, :50] = 200
        sheet, clipped = sheet_brightness(image)
        self.assertGreater(sheet, 150.0)
        self.assertEqual(clipped, 0.0)

    def test_it_counts_what_has_clipped(self):
        image = np.full((100, 100, 3), 255, np.uint8)
        _, clipped = sheet_brightness(image)
        self.assertAlmostEqual(clipped, 100.0)


if __name__ == "__main__":
    unittest.main()
