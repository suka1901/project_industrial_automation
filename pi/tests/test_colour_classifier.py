"""Tests for naming an object's colour, including the hueless ones.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from domain.enums import Colour, Shape
from domain.models import BoundingBox, Detection, Frame, PixelPoint
from adapters.detection.colour_classifier import HsvColourClassifier


def frame_with(object_bgr, paper_level: int = 200) -> Frame:
    """A square object on a uniform sheet, as the camera would see it."""
    image = np.full((200, 200, 3), paper_level, dtype=np.uint8)
    image[80:120, 80:120] = object_bgr
    return Frame(image=image, sequence=0, captured_at=0.0)


def detection() -> Detection:
    return Detection(shape=Shape.SQUARE, colour=Colour.UNKNOWN, confidence=0.9,
                     centre=PixelPoint(100.0, 100.0), angle_deg=0.0,
                     box=BoundingBox(80.0, 80.0, 120.0, 120.0))


class TestColouredObjects(unittest.TestCase):
    """A hue that covers most of the object names it."""

    def test_red(self):
        self.assertIs(HsvColourClassifier().classify(frame_with((0, 0, 220)), detection()),
                      Colour.RED)

    def test_green(self):
        self.assertIs(HsvColourClassifier().classify(frame_with((0, 200, 0)), detection()),
                      Colour.GREEN)

    def test_blue(self):
        self.assertIs(HsvColourClassifier().classify(frame_with((220, 0, 0)), detection()),
                      Colour.BLUE)


class TestAchromaticObjects(unittest.TestCase):
    """White and black carry no hue, so brightness against the paper decides."""

    def test_white(self):
        self.assertIs(HsvColourClassifier().classify(frame_with((235, 235, 235)), detection()),
                      Colour.WHITE)

    def test_black(self):
        self.assertIs(HsvColourClassifier().classify(frame_with((25, 25, 25)), detection()),
                      Colour.BLACK)

    def test_thresholds_follow_the_lighting(self):
        """The same white object under dimmer light is still white.

        This is why the thresholds are fractions of the paper rather than
        absolute levels: the sheet ranged 67-162 across shooting sessions.
        """
        classifier = HsvColourClassifier()
        for image, paper in ((235, 200), (94, 80)):
            with self.subTest(paper=paper):
                self.assertIs(
                    classifier.classify(frame_with((image,) * 3, paper), detection()),
                    Colour.WHITE)

    def test_mid_grey_is_neither(self):
        """Halfway between paper and black is not a colour we can name."""
        self.assertIs(HsvColourClassifier().classify(frame_with((125, 125, 125)), detection()),
                      Colour.UNKNOWN)


class TestColourUsesTheObjectNotTheBox(unittest.TestCase):
    """A star fills barely a third of its box; the rest is paper."""

    def _star_on_paper(self, object_level: int, paper_level: int = 200) -> Frame:
        """A small object inside a much larger box, as a star's bounds are."""
        image = np.full((200, 200, 3), paper_level, dtype=np.uint8)
        image[92:108, 92:108] = object_level      # 16x16 object in a 40x40 box
        return Frame(image=image, sequence=0, captured_at=0.0)

    def test_a_dark_object_is_not_called_white_by_its_surrounding_paper(self):
        """The regression: box median is paper, so black objects read WHITE."""
        frame = self._star_on_paper(20)
        self.assertIs(HsvColourClassifier().classify(frame, detection()), Colour.BLACK)

    def test_a_pale_object_is_still_white(self):
        frame = self._star_on_paper(235)
        self.assertIs(HsvColourClassifier().classify(frame, detection()), Colour.WHITE)


if __name__ == "__main__":
    unittest.main()
