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
that mask, and the fit score - not the harmonic strength - is the confidence.

Nothing is ever refused. An object whose fit is poor is still placed at the
best angle that can be worked out for it: the candidates rarely fail in the
same direction, so their fit-weighted consensus beats any one of them, and
beats sending a zero. Being 10 degrees out is a worse placement; being
unrotated is a wrong one. The fit still travels with the reading, so the log
says which placements were guesses.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import math
from typing import Any, List, Optional, Sequence, Tuple

from domain.models import Detection, Frame, OutlineMeasurement, PixelPoint
from adapters.detection.segmentation import (CANDIDATE_MASKS, border_fraction,
                                             covers_whole_crop, looks_like_paper,
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
        # Which route the angle takes, not a refusal: at or above this the
        # winning mask is trusted on its own, below it the candidates'
        # consensus is taken instead and the reading is logged as a guess.
        # Measured: trustworthy readings sit above 0.75, and the ones wrong by
        # more than a degree or two below 0.6.
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

        readings = self._candidate_readings(crop, order)
        if not readings:
            # Nothing anywhere in the crop looked like an object at all. This
            # is the only case with no angle to give, and it is a lighting
            # fault rather than a measurement one.
            log.warning("%s: no segmentation found an object in the crop, so "
                        "it will be placed unrotated. Light this object from "
                        "the side; there is nothing here to measure.",
                        detection.shape.value)
            centre = self._centre_of(otsu_mask(crop), origin)
            return OutlineMeasurement(0.0, centre or detection.centre, 0.0)

        mask, fitted_angle, fit, name = max(readings, key=lambda row: row[2])
        centre = self._centre_of(mask, origin) or detection.centre

        if fit >= self._min_fit:
            angle = self._refined_angle(mask, order, fitted_angle)
            log.debug("%s measured at %.2f deg, fit %.2f from the %s mask",
                      detection.shape.value, angle, fit, name)
            return OutlineMeasurement(angle, centre, fit)

        # A poor fit everywhere. Rather than send nothing, take what the
        # candidates agree on: they fail for different reasons - a shadow
        # edge, a clipped tip, a hole in the mask - so the directions they
        # agree on are more likely the object's than any single one of them.
        angle = consensus_angle([(row[1], row[2]) for row in readings], order)
        log.info("%s: best fit only %.2f (%s mask), so the angle is a guess "
                 "from %d segmentation(s): %.1f deg. It is placed turned, not "
                 "left straight.",
                 detection.shape.value, fit, name, len(readings), angle)
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

    def _candidate_readings(self, crop: Any,
                            order: int) -> List[Tuple[Any, float, float, str]]:
        """Every segmentation that produced a measurable object.

        All of them, not just the winner: when the winner is poor they are
        what the consensus is taken over.
        """
        import numpy as np

        readings: List[Tuple[Any, float, float, str]] = []
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
            # The same mistake one size smaller, and the dangerous one: the
            # paper with the object's hole filled in stops short of the
            # corners, so it passes the test above, and then fits an ideal
            # square well enough to be believed. What it measures is the angle
            # of the crop. Dropping it here is what leaves the gradient route,
            # which has no opinion about which side is brighter, to answer.
            if looks_like_paper(mask):
                log.debug("%s found the paper rather than the object "
                          "(border %.2f) - not used", name, border_fraction(mask))
                continue

            fitted = fit_shape(mask, order, step_deg=self._step_deg)
            if fitted is None:
                continue

            angle, fit = fitted
            readings.append((mask, angle, fit, name))
            if fit >= self._good_enough_fit:
                break               # plainly this shape; no need to try more

        return readings

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


def consensus_angle(readings: Sequence[Tuple[float, float]], order: int) -> float:
    """One angle from several weak ones, weighted by how well each fitted.

    Angles of an N-fold shape live on a circle of 360/N degrees, so they are
    averaged as directions rather than as numbers: 1 degree and 89 degrees on
    a square are two degrees apart, not eighty-eight, and averaging them
    arithmetically gives 45 - the one answer that is certainly wrong.
    """
    import math

    period = 360.0 / order
    real = imaginary = 0.0
    for angle, weight in readings:
        phase = 2.0 * math.pi * (angle % period) / period
        real += weight * math.cos(phase)
        imaginary += weight * math.sin(phase)

    if math.hypot(real, imaginary) <= 1e-9:
        # The candidates point in opposite directions and cancel. Fall back to
        # the best-fitting one rather than the meaningless average.
        return max(readings, key=lambda row: row[1])[0] % period

    return (math.degrees(math.atan2(imaginary, real)) / 360.0 * period) % period
