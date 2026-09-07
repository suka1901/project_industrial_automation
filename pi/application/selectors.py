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
    """Decides what to do with an object whose angle cannot be trusted.

    Two defensible answers, so it is a setting rather than a rule:

    `pick`  - pick it anyway and place it unrotated. The assignment requires
              every object to be picked in each cycle, and allows one of six
              to be placed wrongly, so a doubtful angle costs less than a
              refused pick. `CoordinateService` has already zeroed the
              rotation and cleared `angle_trusted`, and the GUI says so.

    `skip`  - leave it on the board rather than place it crooked. Right when
              placement accuracy matters more than throughput.

    A circle has no orientation to doubt and always passes either way.
    """

    PICK = "pick"
    SKIP = "skip"

    def __init__(self, policy: str = PICK) -> None:
        self._policy = policy.lower()

    def select(self, objects, request: PickRequest):
        if self._policy != self.SKIP:
            return list(objects)
        return [o for o in objects if o.angle_trusted]


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
