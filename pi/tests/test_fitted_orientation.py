"""Tests for the shape-fitting orientation estimator.

Shapes are drawn on paper-coloured backgrounds and turned by known amounts,
which is the same ground truth the bench uses: an angle that TRACKS the object
is what the robot needs, since any constant offset cancels against the slot
angles, measured with the same estimator.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.enums import Shape
from domain.models import BoundingBox, Detection, Frame
from adapters.detection.fitted_orientation_estimator import (
    FittedOrientationEstimator, area_harmonic_angle)
from adapters.detection.shape_fit import fit_shape, ideal_shape

PAPER = 230
CANVAS = 400
PATCH = 240


def scene(shape: Shape, turn_deg: float, ink: int = 40, noise: int = 0):
    """One object of the given shape, turned by turn_deg, lying on paper."""
    order = shape.symmetry_order or 4
    canvas = np.full((CANVAS, CANVAS, 3), PAPER, np.uint8)
    turned = cv2.warpAffine(
        ideal_shape(order, PATCH),
        cv2.getRotationMatrix2D((PATCH / 2.0, PATCH / 2.0), turn_deg, 1.0),
        (PATCH, PATCH))
    offset = (CANVAS - PATCH) // 2
    patch = canvas[offset:offset + PATCH, offset:offset + PATCH]
    patch[turned > 127] = (ink, ink, ink)
    if noise:
        canvas = cv2.add(canvas, np.random.default_rng(1).integers(
            0, noise, canvas.shape, dtype=np.uint8))
    box = BoundingBox(offset + 30, offset + 30, offset + PATCH - 30, offset + PATCH - 30)
    detection = Detection(shape=shape, colour=None, confidence=1.0,
                          centre=box.centre, angle_deg=0.0, box=box)
    return Frame(image=canvas, sequence=0, captured_at=0.0), detection


def difference(measured, expected, period):
    """Signed difference between two angles of a shape with this period."""
    return (measured - expected + period / 2.0) % period - period / 2.0


class TestTheAngleTracksTheObject(unittest.TestCase):
    """Turning the object by d must move the reading by -d: the image's v axis
    grows downward, so a turn anticlockwise on screen is negative here."""

    def _check(self, shape: Shape, tolerance: float = 1.5):
        estimator = FittedOrientationEstimator()
        period = 360.0 / shape.symmetry_order
        reference = estimator.measure(*scene(shape, 0.0)).angle_deg
        for turn in (7.0, 19.0, 34.0, 61.0):
            with self.subTest(turn=turn):
                measured = estimator.measure(*scene(shape, turn)).angle_deg
                self.assertLess(
                    abs(difference(measured, reference - turn, period)), tolerance,
                    f"{shape.value} turned {turn} deg read {measured:.2f}")

    def test_square(self):
        self._check(Shape.SQUARE)

    def test_star(self):
        self._check(Shape.STAR)

    def test_a_pale_object_is_still_measured(self):
        """The case the old estimator refused: almost no contrast with paper.

        Four grey levels is less than the camera's own noise, so no threshold
        on brightness can find it - the gradient candidate has to.
        """
        estimator = FittedOrientationEstimator()
        period = 90.0
        reference = estimator.measure(*scene(Shape.SQUARE, 0.0, ink=PAPER - 4)).angle_deg
        measured = estimator.measure(*scene(Shape.SQUARE, 23.0, ink=PAPER - 4))
        self.assertGreater(measured.confidence, 0.0)
        self.assertLess(abs(difference(measured.angle_deg, reference - 23.0, period)), 3.0)


class TestWhatItRefuses(unittest.TestCase):
    def test_nothing_shaped_like_the_object_scores_zero(self):
        """Paper alone must not come back as a confident angle."""
        frame, detection = scene(Shape.STAR, 0.0)
        blank = Frame(image=np.full_like(frame.image, PAPER), sequence=0,
                      captured_at=0.0)
        measured = FittedOrientationEstimator().measure(blank, detection)
        self.assertEqual(measured.confidence, 0.0)
        self.assertEqual(measured.angle_deg, 0.0)

    def test_a_square_does_not_pass_as_a_star(self):
        """The fit is what the gate reads, so a wrong shape must score low."""
        frame, square = scene(Shape.SQUARE, 0.0)
        as_star = Detection(shape=Shape.STAR, colour=None, confidence=1.0,
                            centre=square.centre, angle_deg=0.0, box=square.box)
        self.assertLess(FittedOrientationEstimator().measure(frame, as_star).confidence,
                        0.75)

    def test_a_circle_gets_a_centre_but_no_angle(self):
        measured = FittedOrientationEstimator().measure(*scene(Shape.CIRCLE, 0.0))
        self.assertEqual(measured.angle_deg, 0.0)
        self.assertEqual(measured.confidence, 0.0)


class TestTheCentre(unittest.TestCase):
    def test_centre_is_the_object_not_the_crop(self):
        """Measured inside a padded crop, the centre must come back in full
        image coordinates - forgetting the crop's origin moves every pick."""
        frame, detection = scene(Shape.STAR, 0.0)
        centre = FittedOrientationEstimator().measure(frame, detection).centre
        self.assertAlmostEqual(centre.u, CANVAS / 2.0, delta=3.0)
        self.assertAlmostEqual(centre.v, CANVAS / 2.0, delta=3.0)


class TestThePieces(unittest.TestCase):
    def test_fit_scores_the_right_shape_higher(self):
        square = ideal_shape(4, 96)
        self.assertGreater(fit_shape(square, 4)[1], fit_shape(square, 5)[1])

    def test_area_harmonic_needs_enough_pixels(self):
        self.assertIsNone(area_harmonic_angle(np.zeros((40, 40), np.uint8), 4))


if __name__ == "__main__":
    unittest.main()
