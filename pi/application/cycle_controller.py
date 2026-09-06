"""Runs one pick-and-place cycle, and retries it.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import math
from typing import Callable, Optional

from domain.enums import CycleOutcome
from domain.models import CycleReport, DetectedObject, InferenceResult, PickRequest
from application.coordinate_service import CoordinateService
from application.shared_state import SharedState
from ports.interfaces import ObjectSelector

log = logging.getLogger(__name__)

# A function the controller calls to obtain a fresh analysed frame.
InferenceProvider = Callable[[], Optional[InferenceResult]]

# Asks the robot to pick and place one object, and reports what happened.
CommandRobot = Callable[[DetectedObject], CycleOutcome]


class CycleController:
    """Drives an unlimited number of operator-triggered picking cycles."""

    def __init__(
        self,
        get_inference: InferenceProvider,
        coordinates: CoordinateService,
        selector: ObjectSelector,
        commander: CommandRobot,
        state: SharedState,
        max_attempts: int = 3,   # first try plus the two retries the course allows
        verify_tolerance_mm: float = 0.0,
    ) -> None:
        self._get_inference = get_inference
        self._coordinates = coordinates
        self._selector = selector
        self._commander = commander
        self._state = state
        self._max_attempts = max_attempts
        # 0 disables the check. Above 0, the board is re-examined after the
        # robot reports success: an object still lying at the commanded spot
        # means the cup never lifted it.
        self._verify_tolerance_mm = verify_tolerance_mm
        self._cycle_index = 0

    def _object_was_lifted(self, target: DetectedObject) -> bool:
        """True if the object has gone from where the robot was sent."""
        if self._verify_tolerance_mm <= 0.0:
            return True

        result = self._get_inference()
        if result is None:
            return True

        for candidate in self._coordinates.to_objects(result.detections):
            if candidate.shape is not target.shape:
                continue
            distance = math.hypot(candidate.pose.x - target.pose.x,
                                  candidate.pose.y - target.pose.y)
            if distance <= self._verify_tolerance_mm:
                return False
        return True

    def run_cycle(self, request: PickRequest) -> CycleReport:
        """Execute one full cycle for the operator's request."""
        self._cycle_index += 1
        attempts = 0
        last_message = ""

        while attempts < self._max_attempts:
            attempts += 1
            self._state.set_status(
                f"cycle {self._cycle_index}: looking for objects "
                f"(attempt {attempts}/{self._max_attempts})"
            )

            result = self._get_inference()
            if result is None:
                last_message = "no frame available from the camera"
                continue

            self._state.set_inference_time(result.elapsed_ms)

            objects = self._coordinates.to_objects(result.detections)
            self._state.set_detections(objects)

            candidates = self._selector.select(objects, request)
            if not candidates:
                last_message = "no object matched the request"
                continue

            target = candidates[0]
            self._state.set_status(
                f"cycle {self._cycle_index}: picking {target.shape.value} "
                f"({target.colour.value}) at "
                f"x={target.pose.x:.1f} y={target.pose.y:.1f} rz={target.pose.rz:.1f}"
            )

            outcome = self._commander(target)
            if outcome is CycleOutcome.SUCCESS and not self._object_was_lifted(target):
                last_message = "the object is still on the board"
                log.warning("Attempt %d: %s", attempts, last_message)
                continue

            if outcome is CycleOutcome.SUCCESS:
                report = CycleReport(
                    cycle_index=self._cycle_index,
                    request=request,
                    target=target,
                    outcome=outcome,
                    attempts=attempts,
                    message="placed successfully",
                )
                self._state.record_cycle(report)
                return report

            last_message = f"robot reported {outcome.value}"
            log.warning("Attempt %d failed: %s", attempts, last_message)

        # Every attempt used up.
        report = CycleReport(
            cycle_index=self._cycle_index,
            request=request,
            target=None,
            outcome=CycleOutcome.FAILED,
            attempts=attempts,
            message=last_message or "giving up after maximum attempts",
        )
        self._state.record_cycle(report)
        return report
