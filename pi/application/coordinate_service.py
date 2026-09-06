"""Converts detections into picking work object poses.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from typing import Dict, List, Sequence

from domain.enums import Shape
from domain.geometry import place_rotation_deg
from domain.models import Detection, DetectedObject, WorldPose
from ports.interfaces import CoordinateMapper

log = logging.getLogger(__name__)


class CoordinateService:
    """Turns detections into poses the robot can move to."""

    def __init__(
        self,
        mapper: CoordinateMapper,
        pick_depth_mm: float,
        angle_sign: int = 1,
        angle_offset_deg: float = 0.0,
        slot_angles_deg: Dict[Shape, float] | None = None,
    ) -> None:
        self._mapper = mapper
        self._pick_depth_mm = pick_depth_mm
        self._angle_sign = 1 if angle_sign >= 0 else -1
        self._angle_offset_deg = angle_offset_deg
        self._slot_angles = slot_angles_deg or {}

    def to_pose(self, detection: Detection) -> WorldPose:
        """Map one detection into a picking-work-object pose for the robot."""
        x_mm, y_mm = self._mapper.to_world_xy(detection.centre)

        # Image rotation into the robot's rotation sense.
        object_angle = self._angle_sign * detection.angle_deg + self._angle_offset_deg

        # Then the wrist correction the vacuum pick makes necessary.
        slot_angle = self._slot_angles.get(detection.shape, 0.0)
        rz = place_rotation_deg(object_angle, detection.shape, slot_angle)

        return WorldPose(x=x_mm, y=y_mm, z=self._pick_depth_mm, rz=rz)

    def to_objects(self, detections: Sequence[Detection]) -> List[DetectedObject]:
        """Map a batch of detections, skipping any the mapper cannot handle."""
        if not self._mapper.is_calibrated():
            log.error("Coordinate mapper is not calibrated - run the calibration script")
            return []
        return [DetectedObject(detection=d, pose=self.to_pose(d)) for d in detections]
