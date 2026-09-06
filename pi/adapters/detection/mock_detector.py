"""Invents detections, for development without a model.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import random
from typing import Sequence

from domain.enums import Colour, Shape
from domain.models import BoundingBox, Detection, Frame, PixelPoint
from ports.interfaces import ObjectDetector


class MockDetector(ObjectDetector):
    """Returns one fake detection per configured shape, at stable positions."""

    def __init__(self, shapes: Sequence[Shape], seed: int = 7) -> None:
        self._shapes = list(shapes)
        self._random = random.Random(seed)

    def warm_up(self) -> None:
        """Nothing to load."""

    def detect(self, frame: Frame) -> Sequence[Detection]:
        detections = []
        for index, shape in enumerate(self._shapes):
            u = 200.0 + index * 150.0 + self._random.uniform(-4, 4)
            v = 300.0 + self._random.uniform(-4, 4)
            half = 45.0
            detections.append(
                Detection(
                    shape=shape,
                    colour=self._random.choice([Colour.RED, Colour.GREEN, Colour.BLUE]),
                    confidence=self._random.uniform(0.75, 0.98),
                    centre=PixelPoint(u, v),
                    angle_deg=self._random.uniform(0.0, 180.0),
                    box=BoundingBox(u - half, v - half, u + half, v + half),
                )
            )
        return detections
