"""Tests for refusing to measure an object the lighting cannot show.

Measured on the labelled photos: every object with 37 or more grey levels of
contrast against the paper measured to better than 0.5 degrees, and the two
below 26 came out 2.8 and 9.1 degrees wrong. Both of those were WHITE objects
on white paper - three or four grey levels apart, under the sensor's own
noise. The estimator cannot tell, so the gate has to.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from typing import Any
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.detection.segmentation import contrast_levels

SIZE = 140


def scene(paper: int, ink: int) -> np.ndarray:
    """A square object of one grey on paper of another."""
    image: Any = np.full((SIZE, SIZE, 3), paper, np.uint8)
    cv2.rectangle(image, (40, 40), (100, 100), (ink, ink, ink), -1)
    return image


class TestContrastIsMeasuredHonestly(unittest.TestCase):

    def test_a_dark_object_on_light_paper(self):
        self.assertGreater(contrast_levels(scene(paper=150, ink=30)), 100)

    def test_a_light_object_on_dark_paper(self):
        """Sign does not matter - only how far apart they are."""
        self.assertGreater(contrast_levels(scene(paper=30, ink=150)), 100)

    def test_white_on_white_reads_near_zero(self):
        """The real failure: 140 on 136, which is what the photos showed."""
        self.assertLess(contrast_levels(scene(paper=136, ink=140)), 30)

    def test_a_blank_crop_has_no_contrast(self):
        self.assertLess(contrast_levels(np.full((SIZE, SIZE, 3), 180, np.uint8)), 30)

    def test_the_two_cases_are_far_apart(self):
        """Nothing measured between 26 and 36. The separation is the point:
        the light meter calls anything under 20 'no edge to find' and
        anything over 40 good, and those bands exist because the measurement
        leaves a gap this wide between an object that can be segmented and
        one that cannot."""
        for paper, ink, expected in ((150, 30, True), (136, 140, False),
                                     (150, 108, True), (150, 145, False)):
            with self.subTest(paper=paper, ink=ink):
                self.assertEqual(contrast_levels(scene(paper, ink)) >= 30.0,
                                 expected)



if __name__ == "__main__":
    unittest.main()
