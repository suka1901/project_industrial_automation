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
