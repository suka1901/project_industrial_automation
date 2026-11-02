"""How well does a mask look like the shape it claims to be?

The harmonic estimator answers "how N-lobed is this outline", and a badly
segmented blob can score well on that question - a speckled mask of a white
square on white paper reported four-fold structure of 0.4 while being 25
degrees wrong. The question a gate should ask is the other one: IS this a
square at all? Laying an ideal square or star over the mask and measuring the
overlap answers it, and the same sweep hands back the angle for free.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

# Fraction of its outer radius at which a five-pointed star's valleys sit.
# Measured off the printed objects; the overlap peak is broad in this
# parameter, so a per cent either way does not move the angle.
STAR_INNER_RATIO = 0.42

# The window every mask is scaled into before matching. Big enough that a
# degree of rotation moves the rim by more than a pixel, small enough that a
# whole sweep is a few milliseconds.
WINDOW_PX = 96

_TEMPLATES: Dict[Tuple[int, int], Any] = {}


def ideal_shape(order: int, size: int = WINDOW_PX) -> Any:
    """A filled square or N-pointed star, drawn once and kept."""
    import cv2
    import numpy as np

    key = (order, size)
    if key in _TEMPLATES:
        return _TEMPLATES[key]

    radius = size * 0.45
    centre = size / 2.0
    corners = []
    if order == 4:
        for step in range(4):
            angle = math.radians(45.0 + 90.0 * step)
            corners.append((centre + radius * math.cos(angle),
                            centre + radius * math.sin(angle)))
    else:
        for step in range(order):
            tip = math.radians(360.0 * step / order)
            valley = math.radians(360.0 * (step + 0.5) / order)
            corners.append((centre + radius * math.cos(tip),
                            centre + radius * math.sin(tip)))
            corners.append((centre + radius * STAR_INNER_RATIO * math.cos(valley),
                            centre + radius * STAR_INNER_RATIO * math.sin(valley)))

    canvas: Any = np.zeros((size, size), np.uint8)
    cv2.fillPoly(canvas, [np.array(corners, np.int32)], 255)
    _TEMPLATES[key] = canvas
    return canvas



def fit_shape(mask: Any, order: int, size: int = WINDOW_PX,
              step_deg: float = 1.0) -> Optional[Tuple[float, float]]:
    """Best angle and overlap for an ideal shape laid over the mask.

    The angle is in image convention (v downward, so positive turns clockwise)
    and means nothing beyond one symmetry period, which is all the robot needs.
    The overlap is an intersection-over-union, 0 to 1: about 0.9 for a clean
    silhouette, and well under 0.6 when the mask is not this shape.
    """
    import cv2
    import numpy as np

    template = ideal_shape(order, size)
    area = float(np.count_nonzero(mask))
    if area < 100.0:
        return None

    moments = cv2.moments(mask, binaryImage=True)
    if moments["m00"] <= 0.0:
        return None
    centre_x = moments["m10"] / moments["m00"]
    centre_y = moments["m01"] / moments["m00"]
    scale = math.sqrt(float(np.count_nonzero(template)) / area)

    window = cv2.warpAffine(
        mask,
        np.array([[scale, 0.0, size / 2.0 - scale * centre_x],
                  [0.0, scale, size / 2.0 - scale * centre_y]], np.float64),
        (size, size), flags=cv2.INTER_NEAREST)
    window = (window > 127).astype(np.uint8)

    middle = (size / 2.0, size / 2.0)

    def overlap(angle_deg: float) -> float:
        turned = cv2.warpAffine(
            template, cv2.getRotationMatrix2D(middle, angle_deg, 1.0),
            (size, size), flags=cv2.INTER_NEAREST)
        turned = (turned > 127).astype(np.uint8)
        union = int(np.count_nonzero(turned | window))
        if union == 0:
            return 0.0
        return float(np.count_nonzero(turned & window)) / float(union)

    period = 360.0 / order
    angles = np.arange(0.0, period, step_deg)
    scores = [overlap(float(angle)) for angle in angles]
    best = int(np.argmax(scores))
    coarse = float(angles[best])

    # Refine with a parabola through three points rather than a finer sweep:
    # same accuracy for three more overlaps instead of ten times as many.
    half = step_deg / 2.0
    left, middle_score, right = (overlap((coarse - half) % period),
                                 scores[best],
                                 overlap((coarse + half) % period))
    peak = coarse
    curvature = left - 2.0 * middle_score + right
    if curvature < 0.0:
        # A nearly flat trio divides by nearly nothing and would throw the
        # answer across the period, so the refinement may only ever move the
        # answer within the step it is refining.
        offset = half * (left - right) / curvature
        peak += max(-half, min(half, offset))

    # The template is turned anticlockwise to meet the object, so the object
    # itself sits at the negative of that turn.
    return (-peak) % period, max(middle_score, left, right)
