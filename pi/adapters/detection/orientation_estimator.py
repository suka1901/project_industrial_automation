"""Measures object orientation from its outline.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import math
from typing import Any, List, Optional, Tuple

from domain.models import Detection, Frame, OutlineMeasurement, PixelPoint
from adapters.detection.segmentation import object_mask
from domain.orientation import harmonic_orientation, resample_radial
from ports.interfaces import OrientationEstimator

log = logging.getLogger(__name__)


class HarmonicOrientationEstimator(OrientationEstimator):
    """Reads the N-th harmonic of the outline, N being the symmetry order.

    cv2.minAreaRect is not used: its angle is unique only modulo 90 degrees,
    which fits a square and no other shape, and it jumps on a star when the
    defining pair of points changes.
    """

    def __init__(
        self,
        padding_px: int = 8,
        binary_threshold: int = 0,
        bins: int = 180,
        min_confidence: float = 0.05,
    ) -> None:
        # Padding keeps a star's thin points inside a tight detection box.
        self._padding = padding_px
        # 0 means Otsu, which adapts to the lighting on its own.
        self._threshold = binary_threshold
        self._bins = bins
        self._min_confidence = min_confidence

    def measure(self, frame: Frame, detection: Detection) -> OutlineMeasurement:
        """Trace the outline once and report angle, centre and confidence."""
        fallback = OutlineMeasurement(0.0, detection.centre, 0.0)

        if detection.box is None or frame.image is None:
            return fallback

        outline = self._largest_contour(frame, detection)
        if outline is None:
            log.debug("No outline found for %s", detection.shape.value)
            return fallback

        centre = self._centroid(outline)
        if centre is None:
            return fallback

        # The cup lands on the centroid, so it matters as much as the angle:
        # on a star it must be the body, not a point.
        if detection.shape.is_rotationally_free:
            return OutlineMeasurement(0.0, centre, 0.0)

        radii = resample_radial(self._radial_samples(outline, centre), bins=self._bins)
        if radii is None:
            log.debug("Outline of %s is too broken to measure", detection.shape.value)
            return OutlineMeasurement(0.0, centre, 0.0)

        angle, confidence = harmonic_orientation(radii, detection.shape.symmetry_order)

        if confidence < self._min_confidence:
            log.warning("%s shows no clear %d-fold structure (%.3f); reporting "
                        "no rotation rather than guessing",
                        detection.shape.value, detection.shape.symmetry_order,
                        confidence)
            return OutlineMeasurement(0.0, centre, confidence)

        return OutlineMeasurement(angle, centre, confidence)

    def _mask(self, frame: Frame, detection: Detection) -> Optional[Tuple[Any, int, int]]:
        """Binary mask of the object, plus the crop's origin in the full image."""
        assert detection.box is not None
        height, width = frame.image.shape[:2]
        u_min = max(0, int(detection.box.u_min) - self._padding)
        v_min = max(0, int(detection.box.v_min) - self._padding)
        u_max = min(width, int(detection.box.u_max) + self._padding)
        v_max = min(height, int(detection.box.v_max) + self._padding)

        crop = frame.image[v_min:v_max, u_min:u_max]
        if crop.size == 0:
            return None

        return object_mask(crop, self._threshold), u_min, v_min

    def _largest_contour(self, frame: Frame, detection: Detection):
        """The object's outline, in full-image coordinates."""
        import cv2

        prepared = self._mask(frame, detection)
        if prepared is None:
            return None
        mask, u_min, v_min = prepared

        # CHAIN_APPROX_NONE keeps every boundary pixel; the approximated form
        # would bias the radial signature towards corners.
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        return [(float(point[0][0]) + u_min, float(point[0][1]) + v_min)
                for point in largest]

    @staticmethod
    def _centroid(outline: List[Tuple[float, float]]) -> Optional[PixelPoint]:
        """Centre of the object's AREA, not of its outline samples.

        The cup lands here, so this is a picking accuracy question before it
        is anything else. Measured on the labelled squares and stars, the two
        differ by a median of 4.5 px and up to 21.5 px - at 3.23 px/mm that is
        1.4 mm typically and 6.7 mm at worst.

        The area centroid is also the right target physically: a vacuum cup
        wants the middle of the material, not the average of the boundary
        points, which drifts wherever the outline is broken or unevenly
        sampled. And because this centre is the origin of the radial
        signature, a steadier one measures a better angle - it took the
        objects falling below the confidence gate from 15 to 9.
        """
        if not outline:
            return None

        import cv2
        import numpy as np

        contour = np.array(outline, dtype="float32").reshape(-1, 1, 2)
        moments = cv2.moments(contour)
        if moments["m00"] > 0.0:
            return PixelPoint(moments["m10"] / moments["m00"],
                              moments["m01"] / moments["m00"])

        # Zero area: a degenerate outline, so fall back to the sample mean
        # rather than refusing a centre altogether.
        count = float(len(outline))
        return PixelPoint(sum(x for x, _ in outline) / count,
                          sum(y for _, y in outline) / count)

    @staticmethod
    def _radial_samples(outline: List[Tuple[float, float]],
                        centre: PixelPoint) -> List[Tuple[float, float]]:
        """Direction and distance from the centre to each outline point.

        Angles use image convention, v growing downward, so a positive angle
        turns clockwise on screen. angle_sign restores the robot's sense later.
        """
        return [(math.atan2(y - centre.v, x - centre.u),
                 math.hypot(x - centre.u, y - centre.v))
                for x, y in outline]
