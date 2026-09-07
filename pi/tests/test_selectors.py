"""Tests for the object selection rules.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest

from domain.enums import Colour, Shape
from domain.models import Detection, DetectedObject, PickRequest, PixelPoint, WorldPose
from application.selectors import (
    AllowedShapeSelector,
    ColourRequestSelector,
    CompositeSelector,
    ConfidenceSelector,
    OrientationConfidenceSelector,
    NearestToOriginSorter,
    ShapeRequestSelector,
)


def make(shape, colour=Colour.RED, confidence=0.9, x=0.0, y=0.0):
    detection = Detection(shape=shape, colour=colour, confidence=confidence,
                          centre=PixelPoint(0.0, 0.0), angle_deg=0.0)
    return DetectedObject(detection=detection, pose=WorldPose(x, y, 0.0, 0.0))


ANY = PickRequest()


class TestSelectors(unittest.TestCase):
    def test_forbidden_shapes_are_removed(self):
        selector = AllowedShapeSelector([Shape.CIRCLE, Shape.SQUARE, Shape.STAR])
        objects = [make(Shape.CIRCLE), make(Shape.TRIANGLE), make(Shape.HEXAGON)]
        result = selector.select(objects, ANY)
        self.assertEqual([o.shape for o in result], [Shape.CIRCLE])

    def test_shape_request_filters(self):
        objects = [make(Shape.CIRCLE), make(Shape.SQUARE)]
        result = ShapeRequestSelector().select(objects, PickRequest(shape=Shape.SQUARE))
        self.assertEqual([o.shape for o in result], [Shape.SQUARE])

    def test_colour_request_filters_and_rejects_unknown(self):
        objects = [make(Shape.CIRCLE, Colour.RED),
                   make(Shape.SQUARE, Colour.BLUE),
                   make(Shape.STAR, Colour.UNKNOWN)]
        result = ColourRequestSelector().select(objects, PickRequest(colour=Colour.BLUE))
        self.assertEqual([o.shape for o in result], [Shape.SQUARE])

    def test_confidence_threshold(self):
        objects = [make(Shape.CIRCLE, confidence=0.9),
                   make(Shape.SQUARE, confidence=0.2)]
        result = ConfidenceSelector(0.5).select(objects, ANY)
        self.assertEqual(len(result), 1)

    def test_nearest_first(self):
        objects = [make(Shape.CIRCLE, x=300.0), make(Shape.SQUARE, x=50.0)]
        result = NearestToOriginSorter().select(objects, ANY)
        self.assertEqual([o.shape for o in result], [Shape.SQUARE, Shape.CIRCLE])

    def test_composite_chains_rules(self):
        selector = CompositeSelector([
            AllowedShapeSelector([Shape.CIRCLE, Shape.SQUARE, Shape.STAR]),
            ConfidenceSelector(0.5),
            ColourRequestSelector(),
        ])
        objects = [
            make(Shape.TRIANGLE, Colour.RED),          # forbidden shape
            make(Shape.CIRCLE, Colour.RED, 0.2),        # too uncertain
            make(Shape.SQUARE, Colour.BLUE),            # wrong colour
            make(Shape.STAR, Colour.RED),               # the winner
        ]
        result = selector.select(objects, PickRequest(colour=Colour.RED))
        self.assertEqual([o.shape for o in result], [Shape.STAR])


if __name__ == "__main__":
    unittest.main()


class TestOrientationConfidenceSelector(unittest.TestCase):
    """Two defensible policies for an angle that cannot be trusted."""

    def _object(self, shape, angle_trusted):
        detection = Detection(shape=shape, colour=Colour.RED, confidence=0.9,
                              centre=PixelPoint(0.0, 0.0), angle_deg=0.0,
                              angle_confidence=0.20 if angle_trusted else 0.02)
        return DetectedObject(detection=detection,
                              pose=WorldPose(0.0, 0.0, 0.0, 0.0),
                              angle_trusted=angle_trusted)

    def test_pick_policy_keeps_a_doubtful_object(self):
        """A refused pick fails the assignment; a wrong angle costs one of six."""
        selector = OrientationConfidenceSelector("pick")
        objects = [self._object(Shape.STAR, angle_trusted=False)]
        self.assertEqual(len(selector.select(objects, PickRequest(Shape.STAR, None))), 1)

    def test_skip_policy_drops_a_doubtful_object(self):
        selector = OrientationConfidenceSelector("skip")
        objects = [self._object(Shape.STAR, angle_trusted=False)]
        self.assertEqual(selector.select(objects, PickRequest(Shape.STAR, None)), [])

    def test_skip_policy_keeps_a_trusted_object(self):
        selector = OrientationConfidenceSelector("skip")
        objects = [self._object(Shape.STAR, angle_trusted=True)]
        self.assertEqual(len(selector.select(objects, PickRequest(Shape.STAR, None))), 1)

    def test_a_circle_is_always_trusted_so_survives_either_policy(self):
        for policy in ("pick", "skip"):
            with self.subTest(policy=policy):
                selector = OrientationConfidenceSelector(policy)
                objects = [self._object(Shape.CIRCLE, angle_trusted=True)]
                self.assertEqual(
                    len(selector.select(objects, PickRequest(Shape.CIRCLE, None))), 1)
