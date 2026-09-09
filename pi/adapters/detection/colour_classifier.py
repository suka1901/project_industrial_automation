"""Classifies object colour from its hue histogram.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from typing import Dict, Tuple

from adapters.detection.segmentation import object_mask
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
    """Picks the colour whose hue range covers most of the object's pixels.

    White and black carry no hue, so a purely hue-based rule can never name
    them. They are judged instead on brightness relative to the paper the
    object is lying on, which keeps the decision valid as the lighting moves.
    """

    def __init__(
        self,
        hue_ranges: Dict[Colour, Tuple[Tuple[int, int], ...]] | None = None,
        min_saturation: int = 80,
        min_value: int = 50,
        min_fraction: float = 0.10,
        achromatic_max_saturation: int = 70,
        white_of_paper: float = 0.80,
        black_of_paper: float = 0.45,
    ) -> None:
        self._ranges = hue_ranges or DEFAULT_HUE_RANGES
        # Below this saturation a pixel carries no usable hue.
        self._min_saturation = min_saturation
        self._min_value = min_value
        # If no colour covers this share of the object, report UNKNOWN.
        # Measured on the labelled photos: real colours cover 20-100% of their
        # object, hue noise on a black one covers under 1.4%. 0.10 sits in the
        # empty gap between, about seven times above the noise.
        self._min_fraction = min_fraction
        self._achromatic_max_saturation = achromatic_max_saturation
        # Fractions of the paper's own brightness, not absolute levels, so the
        # thresholds travel with the exposure.
        self._white_of_paper = white_of_paper
        self._black_of_paper = black_of_paper

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

        # Judge the object's own pixels, not the box. A star fills barely a
        # third of its box, so anything averaged over the box measures paper.
        inside = object_mask(crop) > 0
        if not inside.any():
            return Colour.UNKNOWN

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hue, sat, val = cv2.split(hsv)

        # Only count object pixels that are actually coloured and lit.
        valid = inside & (sat >= self._min_saturation) & (val >= self._min_value)
        if not valid.any():
            # No hue anywhere: the object is white, black or grey.
            return self._achromatic(frame.image, val, inside, np)

        # Divide by the OBJECT's pixels, not by the ones that happen to be
        # saturated. A black object correctly rejects almost all of its pixels
        # as hueless, and dividing by the few left over let six noisy pixels
        # out of 8588 name it BLUE with a "fraction" of 0.75. Measured on the
        # labelled photos, 13% of objects were being coloured on under 5% of
        # their own pixels that way, 28 of them called blue.
        object_pixels = int(np.count_nonzero(inside))

        best_colour, best_fraction = Colour.UNKNOWN, 0.0
        for colour, bands in self._ranges.items():
            mask = np.zeros_like(valid)
            for low, high in bands:
                mask |= (hue >= low) & (hue <= high)
            fraction = int(np.count_nonzero(mask & valid)) / object_pixels
            if fraction > best_fraction:
                best_colour, best_fraction = colour, fraction

        if best_fraction >= self._min_fraction:
            return best_colour
        return self._achromatic(frame.image, val, inside, np)

    def _achromatic(self, image, value, inside, np) -> Colour:
        """Name a hueless object by how bright it is against the paper.

        The paper is the brightest large thing in frame, so its 95th percentile
        is a reference that moves with the light instead of a fixed level.
        """
        import cv2

        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        paper = float(np.percentile(grey, 95))
        if paper <= 0:
            return Colour.UNKNOWN

        brightness = float(np.median(value[inside]))
        if brightness >= self._white_of_paper * paper:
            return Colour.WHITE
        if brightness <= self._black_of_paper * paper:
            return Colour.BLACK
        return Colour.UNKNOWN


class PassthroughColourClassifier(ColourClassifier):
    """Returns whatever colour the detector already assigned."""

    def classify(self, frame: Frame, detection: Detection) -> Colour:
        return detection.colour
