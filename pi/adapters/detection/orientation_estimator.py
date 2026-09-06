"""Measures object orientation from its outline.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import math
from typing import Any, List, Optional, Tuple

from domain.models import Detection, Frame, OutlineMeasurement, PixelPoint
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
        import cv2

        assert detection.box is not None
        height, width = frame.image.shape[:2]
        u_min = max(0, int(detection.box.u_min) - self._padding)
        v_min = max(0, int(detection.box.v_min) - self._padding)
        u_max = min(width, int(detection.box.u_max) + self._padding)
        v_max = min(height, int(detection.box.v_max) + self._padding)

        crop = frame.image[v_min:v_max, u_min:u_max]
        if crop.size == 0:
            return None

        grey = cv2.GaussianBlur(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (5, 5), 0)

        if self._threshold > 0:
            _, mask = cv2.threshold(grey, self._threshold, 255, cv2.THRESH_BINARY)
        else:
            _, mask = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Objects may be lighter or darker than the board; take the polarity
        # that fills the middle of the crop.
        if mask[mask.shape[0] // 2, mask.shape[1] // 2] == 0:
            mask = cv2.bitwise_not(mask)

        return mask, u_min, v_min

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
        """Centre of the outline, averaged over every boundary point."""
        if not outline:
            return None
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
