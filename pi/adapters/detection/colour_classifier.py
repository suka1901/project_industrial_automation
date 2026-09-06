"""Classifies object colour from its hue histogram.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from typing import Dict, Tuple

from domain.enums import Colour
from domain.models import Detection, Frame
from ports.interfaces import ColourClassifier

# Hue ranges in OpenCV's 0-179 scale. Red wraps around zero, so it gets two.
DEFAULT_HUE_RANGES: Dict[Colour, Tuple[Tuple[int, int], ...]] = {
    Colour.RED: ((0, 10), (170, 179)),
    Colour.GREEN: ((36, 89),),
    Colour.BLUE: ((90, 130),),
}


class HsvColourClassifier(ColourClassifier):
    """Picks the colour whose hue range covers most of the object's pixels."""

    def __init__(
        self,
        hue_ranges: Dict[Colour, Tuple[Tuple[int, int], ...]] | None = None,
        min_saturation: int = 80,
        min_value: int = 50,
        min_fraction: float = 0.25,
    ) -> None:
        self._ranges = hue_ranges or DEFAULT_HUE_RANGES
        # Low saturation means grey/white - the table, not an object.
        self._min_saturation = min_saturation
        self._min_value = min_value
        # If no colour covers this share of the object, report UNKNOWN.
        self._min_fraction = min_fraction

    def classify(self, frame: Frame, detection: Detection) -> Colour:
        """Return the dominant colour of the detected object."""
        # Checked before importing OpenCV so the mock profile runs anywhere.
        if detection.box is None or frame.image is None:
            return Colour.UNKNOWN

        import cv2
        import numpy as np

        height, width = frame.image.shape[:2]
        u_min = max(0, int(detection.box.u_min))
        v_min = max(0, int(detection.box.v_min))
        u_max = min(width, int(detection.box.u_max))
        v_max = min(height, int(detection.box.v_max))

        crop = frame.image[v_min:v_max, u_min:u_max]
        if crop.size == 0:
            return Colour.UNKNOWN

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hue, sat, val = cv2.split(hsv)

        # Only count pixels that are actually coloured and lit.
        valid = (sat >= self._min_saturation) & (val >= self._min_value)
        total = int(np.count_nonzero(valid))
        if total == 0:
            return Colour.UNKNOWN

        best_colour, best_fraction = Colour.UNKNOWN, 0.0
        for colour, bands in self._ranges.items():
            mask = np.zeros_like(valid)
            for low, high in bands:
                mask |= (hue >= low) & (hue <= high)
            fraction = int(np.count_nonzero(mask & valid)) / total
            if fraction > best_fraction:
                best_colour, best_fraction = colour, fraction

        return best_colour if best_fraction >= self._min_fraction else Colour.UNKNOWN


class PassthroughColourClassifier(ColourClassifier):
    """Returns whatever colour the detector already assigned."""

    def classify(self, frame: Frame, detection: Detection) -> Colour:
        return detection.colour
