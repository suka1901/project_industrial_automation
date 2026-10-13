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
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.detection.segmentation import contrast_levels

SIZE = 140


def scene(paper: int, ink: int) -> np.ndarray:
    """A square object of one grey on paper of another."""
    image = np.full((SIZE, SIZE, 3), paper, np.uint8)
    cv2.rectangle(image, (40, 40), (100, 100), (ink,) * 3, -1)
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

    def test_the_gate_sits_in_the_empty_band(self):
        """Nothing measured between 26 and 36, so 30 separates with margin."""
        for paper, ink, expected in ((150, 30, True), (136, 140, False),
                                     (150, 108, True), (150, 145, False)):
            with self.subTest(paper=paper, ink=ink):
                self.assertEqual(contrast_levels(scene(paper, ink)) >= 30.0,
                                 expected)


class TestTheEstimatorRefusesRatherThanInventing(unittest.TestCase):

    def test_a_low_contrast_object_yields_no_angle(self):
        from adapters.detection.orientation_estimator import (
            HarmonicOrientationEstimator)
        from domain.enums import Colour, Shape
        from domain.models import BoundingBox, Detection, Frame, PixelPoint

        image = scene(paper=136, ink=140)
        frame = Frame(image=image, sequence=1, captured_at=0.0)
        box = BoundingBox(u_min=35.0, v_min=35.0, u_max=105.0, v_max=105.0)
        detection = Detection(shape=Shape.SQUARE, colour=Colour.WHITE,
                              confidence=0.9, centre=PixelPoint(70.0, 70.0),
                              angle_deg=0.0, angle_confidence=0.0, box=box)

        result = HarmonicOrientationEstimator().measure(frame, detection)
        self.assertEqual(result.angle_deg, 0.0)
        self.assertEqual(result.confidence, 0.0)

    def test_a_high_contrast_object_still_measures(self):
        from adapters.detection.orientation_estimator import (
            HarmonicOrientationEstimator)
        from domain.enums import Colour, Shape
        from domain.models import BoundingBox, Detection, Frame, PixelPoint

        frame = Frame(image=scene(paper=150, ink=30), sequence=1,
                      captured_at=0.0)
        box = BoundingBox(u_min=35.0, v_min=35.0, u_max=105.0, v_max=105.0)
        detection = Detection(shape=Shape.SQUARE, colour=Colour.BLACK,
                              confidence=0.9, centre=PixelPoint(70.0, 70.0),
                              angle_deg=0.0, angle_confidence=0.0, box=box)

        result = HarmonicOrientationEstimator().measure(frame, detection)
        self.assertGreater(result.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
