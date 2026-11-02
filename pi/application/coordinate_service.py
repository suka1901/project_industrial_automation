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
    ) -> None:
        self._mapper = mapper
        self._angle_sign = 1 if angle_sign >= 0 else -1
        self._angle_offset_deg = angle_offset_deg
        self._slot_angles = slot_angles_deg or {}
        # Mapping now runs on every frame, not once per cycle, so a missing
        # marker is reported when it goes missing rather than 2-3 times a second.
        self._reported_uncalibrated = False

    def to_pose(self, detection: Detection) -> WorldPose:
        """Map one detection into a picking-work-object pose for the robot."""
        x_mm, y_mm = self._mapper.to_world_xy(detection.centre)
        measured = detection.angle_deg
        slot_angle = self._slot_angles.get(detection.shape, 0.0)
        turn = place_rotation_deg(measured, detection.shape, slot_angle)
        rz = normalise_for_shape(self._angle_sign * turn + self._angle_offset_deg,
                                 detection.shape, 0.0)
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
        return [DetectedObject(detection=d, pose=self.to_pose(d))
                for d in detections]
