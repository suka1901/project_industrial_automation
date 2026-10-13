"""Converts detections into picking work object poses.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from typing import Dict, List, Sequence

from domain.enums import Shape
from domain.geometry import normalise_for_shape, place_rotation_deg
from domain.models import Detection, DetectedObject, WorldPose
from ports.interfaces import CoordinateMapper

log = logging.getLogger(__name__)


class CoordinateService:
    """Turns detections into poses the robot can move to."""

    def __init__(
        self,
        mapper: CoordinateMapper,
        angle_sign: int = 1,
        angle_offset_deg: float = 0.0,
        slot_angles_deg: Dict[Shape, float] | None = None,
        min_angle_confidence: float = 0.05,
    ) -> None:
        self._mapper = mapper
        self._angle_sign = 1 if angle_sign >= 0 else -1
        self._angle_offset_deg = angle_offset_deg
        self._slot_angles = slot_angles_deg or {}
        # Below this the measured angle is wrong by 25-31 degrees, so it is
        # discarded rather than believed. See README for the measurements.
        self._min_angle_confidence = min_angle_confidence
        # Mapping now runs on every frame, not once per cycle, so a missing
        # marker is reported when it goes missing rather than 2-3 times a second.
        self._reported_uncalibrated = False

    def angle_is_trusted(self, detection: Detection) -> bool:
        """Whether the outline showed its symmetry clearly enough to believe.

        A circle has no orientation, so there is nothing to doubt.
        """
        if detection.shape.is_rotationally_free:
            return True
        return detection.angle_confidence >= self._min_angle_confidence

    def to_pose(self, detection: Detection) -> WorldPose:
        """Map one detection into a picking-work-object pose for the robot."""
        x_mm, y_mm = self._mapper.to_world_xy(detection.centre)

        # An untrusted angle is treated as zero rather than acted on. Believing
        # it would seat the object up to a quarter turn out.
        measured = detection.angle_deg if self.angle_is_trusted(detection) else 0.0

        # BOTH terms are camera angles: the object's, and the slot's, which
        # calibration/slot_angles.py measured with this same estimator and
        # stored raw. So subtract them in the camera's sense FIRST, and only
        # then turn the result into the robot's.
        #
        # Applying angle_sign to the object alone computed slot + measured
        # instead of -(slot - measured): the sign flipped one term of a
        # subtraction, which is not a change of sense but a different sum. A
        # square sitting square-on came out 90 degrees round.
        slot_angle = self._slot_angles.get(detection.shape, 0.0)
        turn = place_rotation_deg(measured, detection.shape, slot_angle)
        rz = normalise_for_shape(self._angle_sign * turn + self._angle_offset_deg,
                                 detection.shape, 0.0)

        # Z is always 0: the robot owns the pick height, in PICK_SURFACE_Z_MM.
        # It has to - the camera sees one plane and cannot measure how thick an
        # object is - and the protocol carries no Z for that reason.
        return WorldPose(x=x_mm, y=y_mm, z=0.0, rz=rz)

    def to_objects(self, detections: Sequence[Detection]) -> List[DetectedObject]:
        """Map a batch of detections, skipping any the mapper cannot handle."""
        if not self._mapper.is_calibrated():
            if not self._reported_uncalibrated:
                log.error("Coordinate mapper is not calibrated - is the ArUco "
                          "marker in view? Positions resume once it is seen.")
                self._reported_uncalibrated = True
            return []
        if self._reported_uncalibrated:
            log.info("Coordinate mapper calibrated - positions are available again")
            self._reported_uncalibrated = False
        return [DetectedObject(detection=d, pose=self.to_pose(d),
                              angle_trusted=self.angle_is_trusted(d))
                for d in detections]
