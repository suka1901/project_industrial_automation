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


class TestHueNoiseCannotNameAnObject(unittest.TestCase):
    """A few stray saturated pixels must not decide a hueless object's colour.

    This is the regression that mattered in the lab: black objects were coming
    out BLUE. The share of the object showing a hue was being divided by the
    pixels that happened to be saturated rather than by the object, so on a
    black object - which correctly rejects nearly all of its pixels as hueless
    - a handful of noisy ones scored a "fraction" near 1.0 and won.
    """

    def _black_object_with_noise(self, noisy_pixels: int) -> Frame:
        """A black object with a few dark, blue-tinted pixels in it.

        The tint has to be DARK to reproduce the real fault. A bright blue
        speck falls outside the object mask and never reaches the hue test at
        all, so it proves nothing. Camera noise on a black object is dark and
        saturated - which is exactly what slips through.
        """
        image = np.full((200, 200, 3), 200, dtype=np.uint8)
        image[85:115, 85:115] = (20, 20, 20)              # the object
        flat = image[85:115, 85:115].reshape(-1, 3)
        flat[:noisy_pixels] = (70, 20, 20)                # dark, saturated, blue
        image[85:115, 85:115] = flat.reshape(30, 30, 3)
        return Frame(image=image, sequence=0, captured_at=0.0)

    def test_a_black_object_with_blue_specks_is_black(self):
        frame = self._black_object_with_noise(noisy_pixels=8)
        self.assertIs(HsvColourClassifier().classify(frame, detection()), Colour.BLACK)

    def test_still_black_when_every_saturated_pixel_is_blue(self):
        """The old code scored this 1.00 and called it BLUE. It is 2% of the
        object, so the fixed denominator puts it far below the 0.10 floor."""
        frame = self._black_object_with_noise(noisy_pixels=20)
        self.assertIs(HsvColourClassifier().classify(frame, detection()), Colour.BLACK)

    def test_a_genuinely_blue_object_is_still_blue(self):
        """The fix must not cost real colours - the other half of the trade."""
        self.assertIs(HsvColourClassifier().classify(frame_with((220, 0, 0)), detection()),
                      Colour.BLUE)

    def test_a_partly_shadowed_colour_survives(self):
        """Only a third of the object is lit enough to show hue, which is well
        above the 10% floor and must still be named."""
        image = np.full((200, 200, 3), 200, dtype=np.uint8)
        image[80:120, 80:120] = (60, 0, 0)       # too dark to pass min_value
        image[80:95, 80:120] = (220, 0, 0)       # the lit third
        frame = Frame(image=image, sequence=0, captured_at=0.0)
        self.assertIs(HsvColourClassifier().classify(frame, detection()), Colour.BLUE)


if __name__ == "__main__":
    unittest.main()


def frame_with_noise(object_bgr, speckles, paper_level: int = 200,
                     seed: int = 0) -> Frame:
    """An object carrying a scatter of strongly coloured, disagreeing pixels.

    This is the shape of the original bug: a handful of saturated pixels on a
    hueless object, each naming a different hue.
    """
    rng = np.random.default_rng(seed)
    image = np.full((200, 200, 3), paper_level, dtype=np.uint8)
    image[80:120, 80:120] = object_bgr
    for _ in range(speckles):
        row = int(rng.integers(82, 118))
        col = int(rng.integers(82, 118))
        image[row, col] = tuple(int(v) for v in rng.integers(0, 256, 3))
    return Frame(image=image, sequence=0, captured_at=0.0)


class TestDarkButRealColours(unittest.TestCase):
    """A dark green circle is still green.

    min_value used to be 50, which discarded almost every pixel of an object
    lying in shadow. Six dark green circles and four blue stars in the
    labelled photos reached no colour at all and came out UNKNOWN.
    """

    # Value 45: below the old gate of 50, above the new one of 35. Picked
    # deliberately - my first attempt used value 70, which passed under the
    # old setting too and so tested nothing at all.
    def test_a_dark_green_object(self):
        self.assertIs(
            HsvColourClassifier().classify(frame_with((0, 45, 0), paper_level=150),
                                           detection()),
            Colour.GREEN)

    def test_a_dark_blue_object(self):
        self.assertIs(
            HsvColourClassifier().classify(frame_with((45, 0, 0), paper_level=150),
                                           detection()),
            Colour.BLUE)

    def test_a_genuinely_black_object_is_still_black(self):
        self.assertIs(
            HsvColourClassifier().classify(frame_with((18, 18, 18), paper_level=150),
                                           detection()),
            Colour.BLACK)


class TestHueHasToAgreeWithItself(unittest.TestCase):
    """Abundance is not enough - it was abundance that named a black square BLUE."""

    def test_plenty_of_in_band_pixels_that_disagree_do_not_name_a_colour(self):
        """The case the fraction test cannot catch on its own.

        Hues spread over a third of the circle: nearly half of them land in
        the green band, so the fraction sails past min_fraction, but they
        agree with each other only weakly. This is the shape of the eight
        dark objects in the labelled photos that a lower value gate alone
        would have called green or blue.
        """
        import cv2

        rng = np.random.default_rng(3)
        hsv = np.full((200, 200, 3), (0, 0, 200), dtype=np.uint8)
        patch = np.zeros((40, 40, 3), dtype=np.uint8)
        patch[:, :, 0] = rng.integers(0, 121, (40, 40))   # hue over 0-120
        patch[:, :, 1] = 200                              # saturated
        patch[:, :, 2] = 120                              # and lit
        hsv[80:120, 80:120] = patch
        image = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        frame = Frame(image=image, sequence=0, captured_at=0.0)

        with_gate = HsvColourClassifier()
        without_gate = HsvColourClassifier(min_hue_agreement=0.0)
        self.assertIs(without_gate.classify(frame, detection()), Colour.GREEN,
                      "test is not exercising the gate")
        self.assertIsNot(with_gate.classify(frame, detection()), Colour.GREEN)

    def test_a_real_colour_still_passes_with_some_noise(self):
        self.assertIs(
            HsvColourClassifier().classify(
                frame_with_noise((0, 200, 0), speckles=25), detection()),
            Colour.GREEN)

    def test_agreement_is_high_for_one_hue_and_low_for_many(self):
        classifier = HsvColourClassifier()
        hue = np.full((40, 40), 60, dtype=np.uint8)
        valid = np.ones((40, 40), dtype=bool)
        self.assertGreater(classifier._hue_agreement(hue, valid, np), 0.99)

        # 1620 is nine whole turns of the 0-179 hue scale, so the spread is
        # even. An odd number leaves a partial cycle, which is itself a bias:
        # my first attempt used 1600 and scored 0.24 instead of ~0.
        wide = np.ones((45, 36), dtype=bool)
        spread = (np.arange(1620, dtype=np.int32) % 180).astype(np.uint8).reshape(45, 36)
        self.assertLess(classifier._hue_agreement(spread, wide, np), 0.05)
