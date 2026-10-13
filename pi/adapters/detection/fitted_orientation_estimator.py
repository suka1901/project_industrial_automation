"""Orientation by fitting the shape itself, over several segmentations.

Two measured findings shaped this, both from the labelled photos read at six
known rotations each (tools/orientation_bench.py):

  1. No single segmentation works on every object. Brightness finds a dark
     object, colour finds a coloured one, and only a gradient finds a WHITE
     object on white paper - where object and paper differ by three or four
     grey levels, less than the sensor's noise. Running several and keeping
     the best per object took squares from 49 to 79 per cent usable.

  2. The old gate measured the wrong thing. The harmonic's own strength says
     how N-lobed an outline is, and a speckled mask scores well on that while
     being 25 degrees wrong, so raising that gate filtered almost nothing.
     How well an ideal square or star OVERLAYS the mask does separate them:
     gating on it left a median error of 0.5 deg and a worst case near 2 deg.

So the mask is chosen by shape fit, the angle is read from the whole area of
that mask, and the fit score - not the harmonic strength - is the confidence
the rest of the system gates on.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import math
from typing import Any, List, Optional, Tuple

from domain.models import Detection, Frame, OutlineMeasurement, PixelPoint
from adapters.detection.segmentation import (CANDIDATE_MASKS, covers_whole_crop,
                                             otsu_mask)
from adapters.detection.shape_fit import fit_shape
from ports.interfaces import OrientationEstimator

log = logging.getLogger(__name__)


class FittedOrientationEstimator(OrientationEstimator):
    """Segments several ways, keeps the mask that best fits the shape."""

    def __init__(
        self,
        padding_px: int = 8,
        candidates: Optional[List[str]] = None,
        min_fit: float = 0.60,
        good_enough_fit: float = 0.85,
        step_deg: float = 2.0,
        agreement_deg: float = 4.0,
    ) -> None:
        # Padding keeps a star's thin points inside a tight detection box.
        self._padding = padding_px
        # Tried in order, cheapest first, and the sweep stops early on a good
        # fit - so a plainly visible object costs one segmentation, not four.
        self._candidates = candidates or list(CANDIDATE_MASKS)
        # Below this, no segmentation produced something shaped like the
        # object, so there is no angle to report. Measured: good readings sit
        # above 0.75, wrong ones below 0.6.
        self._min_fit = min_fit
        self._good_enough_fit = good_enough_fit
        self._step_deg = step_deg
        # The two angles are read from the same mask by different means, so
        # they agree closely or something is wrong with the mask.
        self._agreement_deg = agreement_deg

    # --- OrientationEstimator ---------------------------------------------

    def measure(self, frame: Frame, detection: Detection) -> OutlineMeasurement:
        """Report the object's angle, its centre, and how well it fits."""
        fallback = OutlineMeasurement(0.0, detection.centre, 0.0)
        cropped = self._crop(frame, detection)
        if cropped is None:
            return fallback
        crop, origin = cropped

        order = detection.shape.symmetry_order
        if detection.shape.is_rotationally_free:
            # A circle has no angle. It still needs its centre, which is where
            # the cup lands, so segment it the plain way and take the centroid.
            centre = self._centre_of(otsu_mask(crop), origin)
            return OutlineMeasurement(0.0, centre or detection.centre, 0.0)

        best = self._best_fit(crop, order)
        if best is None:
            log.warning("%s: no segmentation produced anything shaped like a "
                        "%s, so it will be placed unrotated. Look at the "
                        "lighting on this object.",
                        detection.shape.value, detection.shape.value.lower())
            centre = self._centre_of(otsu_mask(crop), origin)
            return OutlineMeasurement(0.0, centre or detection.centre, 0.0)

        mask, fitted_angle, fit, name = best
        centre = self._centre_of(mask, origin) or detection.centre
        angle = self._refined_angle(mask, order, fitted_angle)

        log.debug("%s measured at %.2f deg, fit %.2f from the %s mask",
                  detection.shape.value, angle, fit, name)
        return OutlineMeasurement(angle, centre, fit)

    # --- the parts -------------------------------------------------------

    def _crop(self, frame: Frame,
              detection: Detection) -> Optional[Tuple[Any, Tuple[int, int]]]:
        """The padded detection box, with its origin in the full image.

        The origin travels with the crop because every centre measured inside
        it has to be put back where the object really is; dropping it would
        move the pick by the padding, silently.
        """
        if detection.box is None or frame.image is None:
            return None

        height, width = frame.image.shape[:2]
        u_min = max(0, int(detection.box.u_min) - self._padding)
        v_min = max(0, int(detection.box.v_min) - self._padding)
        u_max = min(width, int(detection.box.u_max) + self._padding)
        v_max = min(height, int(detection.box.v_max) + self._padding)

        crop = frame.image[v_min:v_max, u_min:u_max]
        return (crop, (u_min, v_min)) if crop.size else None

    def _best_fit(self, crop: Any,
                  order: int) -> Optional[Tuple[Any, float, float, str]]:
        """Segment every way asked for and keep whichever fits the shape best."""
        import numpy as np

        best: Optional[Tuple[Any, float, float, str]] = None
        for name in self._candidates:
            segmenter = CANDIDATE_MASKS.get(name)
            if segmenter is None:
                log.warning("Unknown segmentation '%s' - skipped", name)
                continue

            mask = segmenter(crop)
            area = float(np.count_nonzero(mask))
            # A mask that fills the crop is the paper, not the object: the box
            # has padding round it, so nothing real reaches the corners.
            if area < 100.0 or covers_whole_crop(area, mask):
                continue

            fitted = fit_shape(mask, order, step_deg=self._step_deg)
            if fitted is None:
                continue

            angle, fit = fitted
            if best is None or fit > best[2]:
                best = (mask, angle, fit, name)
            if fit >= self._good_enough_fit:
                break               # plainly this shape; no need to try more

        if best is None or best[2] < self._min_fit:
            return None
        return best

    def _refined_angle(self, mask: Any, order: int, fitted_angle: float) -> float:
        """The area harmonic's angle, kept only while it agrees with the fit.

        The harmonic reads every pixel and is the more precise of the two -
        0.14 deg against 0.60 on the labelled photos. It is also the one that
        can be confidently wrong, so the fitted angle, which the confidence
        vouches for, is what it has to agree with.
        """
        harmonic = area_harmonic_angle(mask, order)
        if harmonic is None:
            return fitted_angle

        period = 360.0 / order
        difference = (harmonic - fitted_angle + period / 2.0) % period - period / 2.0
        if abs(difference) <= self._agreement_deg:
            return harmonic % period

        log.debug("harmonic %.2f and fit %.2f disagree by %.2f deg; keeping the fit",
                  harmonic, fitted_angle, difference)
        return fitted_angle

    @staticmethod
    def _centre_of(mask: Any, origin: Tuple[int, int]) -> Optional[PixelPoint]:
        """Centre of the object's AREA, in full-image pixels.

        The cup lands here, so this matters as much as the angle: on a star it
        must be the body, not a point.
        """
        import cv2

        moments = cv2.moments(mask, binaryImage=True)
        if moments["m00"] <= 0.0:
            return None
        return PixelPoint(moments["m10"] / moments["m00"] + origin[0],
                          moments["m01"] / moments["m00"] + origin[1])


def area_harmonic_angle(mask: Any, order: int) -> Optional[float]:
    """The N-fold direction of a mask, summed over its whole area.

    The same idea as the radial signature, but every pixel votes instead of
    only the boundary ones, weighted by r^N so the rim decides. A nick in the
    outline moves a handful of pixels here, and the entire signature there.
    """
    import cv2
    import numpy as np

    moments = cv2.moments(mask, binaryImage=True)
    if moments["m00"] <= 0.0 or order <= 0:
        return None

    centre_x = moments["m10"] / moments["m00"]
    centre_y = moments["m01"] / moments["m00"]
    rows, columns = np.nonzero(mask)
    if columns.size < 50:
        return None

    dx = columns - centre_x
    dy = rows - centre_y
    weight = np.hypot(dx, dy) ** order        # the rim, not the middle
    total = float(np.sum(weight))
    if total <= 0.0:
        return None

    phase = order * np.arctan2(dy, dx)
    real = float(np.sum(weight * np.cos(phase)))
    imaginary = float(np.sum(weight * np.sin(phase)))
    if math.hypot(real, imaginary) <= 1e-9:
        return None
    return math.degrees(math.atan2(imaginary, real)) / order
