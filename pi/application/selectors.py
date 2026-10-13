"""Rules deciding which detected object to pick next.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from typing import Sequence

from domain.area import Rect
from domain.enums import Colour, Shape
from domain.models import PickRequest
from ports.interfaces import ObjectSelector


class AllowedShapeSelector(ObjectSelector):
    """Keeps only the three shapes."""

    def __init__(self, allowed: Sequence[Shape]) -> None:
        self._allowed = frozenset(allowed)

    def select(self, objects, request: PickRequest):
        return [o for o in objects if o.shape in self._allowed]


class PickAreaSelector(ObjectSelector):
    """Keeps only objects lying on the picking sheet.

    The jig is deliberately in the camera frame so the slot angles can be
    measured where the objects lie, which means an object already placed in a
    slot is detected exactly like one waiting to be picked. RAPID refuses an
    off-board position anyway, but a refusal costs the whole cycle: the same
    jig object is nearest again on the retry, and all three attempts go the
    same way. Better never to offer it.
    """

    def __init__(self, area: Rect) -> None:
        self._area = area

    def select(self, objects, request: PickRequest):
        return [o for o in objects if self._area.contains(o.pose.x, o.pose.y)]


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
