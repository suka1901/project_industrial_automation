"""Rules deciding which detected object to pick next.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from typing import Sequence

from domain.enums import Colour, Shape
from domain.models import PickRequest
from ports.interfaces import ObjectSelector


class AllowedShapeSelector(ObjectSelector):
    """Keeps only the three shapes."""

    def __init__(self, allowed: Sequence[Shape]) -> None:
        self._allowed = frozenset(allowed)

    def select(self, objects, request: PickRequest):
        return [o for o in objects if o.shape in self._allowed]


class ShapeRequestSelector(ObjectSelector):
    """Keeps only the shape the operator asked for this cycle (if any)."""

    def select(self, objects, request: PickRequest):
        if request.shape is None:
            return list(objects)
        return [o for o in objects if o.shape is request.shape]


class ColourRequestSelector(ObjectSelector):
    """Keeps only the requested colour - the Grade Level II/III colour rule."""

    def select(self, objects, request: PickRequest):
        if request.colour is None:
            return list(objects)
        return [o for o in objects
                if o.colour is request.colour and o.colour is not Colour.UNKNOWN]


class ConfidenceSelector(ObjectSelector):
    """Drops detections the model is not sure about."""

    def __init__(self, minimum: float = 0.5) -> None:
        self._minimum = minimum

    def select(self, objects, request: PickRequest):
        return [o for o in objects if o.detection.confidence >= self._minimum]


class OrientationConfidenceSelector(ObjectSelector):
    """Drops objects whose angle could not be measured well enough to place.

    A weak outline yields an angle indistinguishable from noise, and the
    estimator reports 0 degrees rather than guessing. Placing on that 0 is a
    silent error, so such an object is skipped instead: the operator sees
    nothing found, which is honest, rather than a part seated crooked.

    A circle has no orientation to measure and always passes.
    """

    def __init__(self, minimum: float = 0.10) -> None:
        self._minimum = minimum

    def select(self, objects, request: PickRequest):
        return [o for o in objects
                if o.detection.shape.is_rotationally_free
                or o.detection.angle_confidence >= self._minimum]


class NearestToOriginSorter(ObjectSelector):
    """Orders survivors by distance from the work object origin."""

    def select(self, objects, request: PickRequest):
        return sorted(objects, key=lambda o: (o.pose.x ** 2 + o.pose.y ** 2))


class CompositeSelector(ObjectSelector):
    """Runs a list of selectors in order, feeding each one the previous result."""

    def __init__(self, selectors: Sequence[ObjectSelector]) -> None:
        self._selectors = list(selectors)

    def select(self, objects, request: PickRequest):
        result = list(objects)
        for selector in self._selectors:
            result = list(selector.select(result, request))
            if not result:
                break  # nothing survived, no point running the rest
        return result
