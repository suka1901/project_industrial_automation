"""Keeps the pixel-to-millimetre mapping solved from the table marker.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from domain.marker import marker_world_corners
from domain.models import Frame
from adapters.detection.aruco import ArUco
from adapters.mapping.homography_mapper import MutableHomographyMapper
from ports.interfaces import SceneCalibrator

log = logging.getLogger(__name__)

class ArucoCalibrator(SceneCalibrator):
    """Keeps a MutableHomographyMapper up to date from a fixed table marker."""

    def __init__(
        self,
        mapper: MutableHomographyMapper,
        marker_length_mm: float,
        marker_centre_xy_mm: Tuple[float, float],
        marker_id: Optional[int] = None,
        marker_angle_deg: float = 0.0,
        y_axis_flipped: bool = False,
        dictionary_name: str = "DICT_5X5_100",
        redetect_every_n_frames: int = 1,
        hold_last_good: bool = True,
        scale_tolerance: float = 0.15,
    ) -> None:
        self._mapper = mapper
        self._marker_length_mm = marker_length_mm
        self._marker_centre = marker_centre_xy_mm
        self._marker_id = marker_id
        self._marker_angle_deg = marker_angle_deg
        self._y_axis_flipped = y_axis_flipped
        self._dictionary_name = dictionary_name
        # Re-solving every frame costs only a few milliseconds, but it can be
        # thinned out if the inference budget gets tight.
        self._interval = max(1, redetect_every_n_frames)
        # Keep working from the last good calibration if a hand briefly covers
        # the marker - far better than refusing to pick.
        self._hold_last_good = hold_last_good
        self._scale_tolerance = scale_tolerance

        # Composition, not inheritance: the calibrator HAS a marker detector.
        self._aruco = ArUco(
            dictionary_name=dictionary_name,
            marker_length_mm=marker_length_mm,
        )
        self._frames_seen = 0
        self._ever_calibrated = False

    # --- SceneCalibrator interface ----------------------------------------

    @property
    def is_ready(self) -> bool:
        return self._mapper.is_calibrated()

    def update(self, frame: Frame) -> bool:
        """Find the marker in this frame and refresh the homography."""
        if frame.image is None:
            return False

        self._frames_seen += 1
        if self._frames_seen % self._interval != 0 and self._ever_calibrated:
            return False

        import cv2
        import numpy as np

        corners, ids = self._aruco.detect(frame.image)
        chosen = self._aruco.corners_for_id(corners, ids, self._marker_id)
        if chosen is None:
            if not self._hold_last_good:
                log.debug("Reference marker not visible")
            return False

        image_corners = chosen.reshape(4, 2).astype("float32")

        world_corners = np.array(
            marker_world_corners(
                side_length_mm=self._marker_length_mm,
                centre_xy_mm=self._marker_centre,
                angle_deg=self._marker_angle_deg,
                y_axis_flipped=self._y_axis_flipped,
            ),
            dtype="float32",
        )

        # Four exact point pairs - a perspective transform, not a least squares fit.
        matrix = cv2.getPerspectiveTransform(image_corners, world_corners)

        # Independent check using the course's perimeter method. If the two
        # disagree the marker was misread or marker_length_mm is wrong.
        scale_px_per_mm = self._aruco.pixel_mm_ratio(image_corners)
        if not self._scale_is_plausible(matrix, scale_px_per_mm):
            log.warning("Rejecting calibration: homography and perimeter scale "
                        "disagree by more than %.0f%%", self._scale_tolerance * 100)
            return False

        self._mapper.set_matrix(matrix, scale_px_per_mm=scale_px_per_mm)
        if not self._ever_calibrated:
            log.info("Calibrated from ArUco marker: %.3f px/mm", scale_px_per_mm)
            self._ever_calibrated = True
        return True

    # --- helpers -----------------------------------------------------------

    def _scale_is_plausible(self, matrix, scale_px_per_mm: float) -> bool:
        """Compare the homography's local scale against the perimeter estimate."""
        import cv2
        import numpy as np

        # Map a 100-pixel horizontal step and see how many millimetres it spans.
        probe = np.array([[[0.0, 0.0]], [[100.0, 0.0]]], dtype="float32")
        mapped = cv2.perspectiveTransform(probe, matrix)

        distance_mm = float(np.linalg.norm(mapped[1] - mapped[0]))
        if distance_mm <= 1e-6:
            return False

        homography_scale = 100.0 / distance_mm
        relative_error = abs(homography_scale - scale_px_per_mm) / scale_px_per_mm
        return relative_error <= self._scale_tolerance
