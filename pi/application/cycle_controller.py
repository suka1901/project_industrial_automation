"""Runs one pick-and-place cycle, and retries it.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import math
import time
from typing import Callable, Optional, Tuple

from domain.enums import CycleOutcome
from domain.models import CycleReport, DetectedObject, MappedScene, PickRequest
from application.shared_state import SharedState
from ports.interfaces import ObjectSelector

log = logging.getLogger(__name__)

# Returns the freshest scene, already in work object coordinates. The
# translation itself happens on its own thread, before the cycle sees it.
SceneProvider = Callable[[], Optional[MappedScene]]

# Asks the robot to pick and place one object, and reports what happened.
CommandRobot = Callable[[DetectedObject], CycleOutcome]

# Pauses for up to the given seconds. Returns True when the system is shutting
# down, so a cycle never holds the application open. threading.Event.wait has
# exactly this shape, which is what main.py passes in.
Wait = Callable[[float], bool]

# How often the robot connection is re-checked while a cycle waits for it.
ROBOT_POLL_S = 0.5


def sleep_without_shutdown(seconds: float) -> bool:
    """Default Wait for callers with no shutdown signal: sleep, never abort."""
    time.sleep(max(0.0, seconds))
    return False


class CycleController:
    """Drives an unlimited number of operator-triggered picking cycles."""

    def __init__(
        self,
        get_scene: SceneProvider,
        selector: ObjectSelector,
        commander: CommandRobot,
        state: SharedState,
        max_attempts: int = 3,   # first try plus the two retries the course allows
        verify_tolerance_mm: float = 0.0,
        robot_ready: Callable[[], bool] = lambda: True,
        wait: Wait = sleep_without_shutdown,
        retry_delay_s: float = 0.0,
        connect_wait_s: float = 0.0,
    ) -> None:
        self._get_scene = get_scene
        self._selector = selector
        self._commander = commander
        self._state = state
        self._max_attempts = max_attempts
        # 0 disables the check. Above 0, the board is re-examined after the
        # robot reports success: an object still lying at the commanded spot
        # means the cup never lifted it.
        self._verify_tolerance_mm = verify_tolerance_mm
        # An attempt made while the robot is away cannot succeed, so it must
        # not be spent. Without this check all three attempts failed within
        # one second of each other, and the operator had to ask again.
        self._robot_ready = robot_ready
        self._wait = wait
        # A retry straight after a failure reads the same stale scene and
        # fails the same way. The pause lets a new frame arrive first.
        self._retry_delay_s = retry_delay_s
        self._connect_polls = max(0, math.ceil(connect_wait_s / ROBOT_POLL_S))
        self._cycle_index = 0

    # --- the cycle ---------------------------------------------------------

    def run_cycle(self, request: PickRequest) -> CycleReport:
        """Execute one full cycle for the operator's request."""
        self._cycle_index += 1
        attempts = 0
        last_message = ""

        while attempts < self._max_attempts:
            if attempts > 0 and self._wait(self._retry_delay_s):
                last_message = "stopped - the system is shutting down"
                break
            if not self._robot_is_ready():
                last_message = "the robot is not connected - nothing was attempted"
                break

            attempts += 1
            target, last_message = self._attempt(request, attempts)
            if target is not None:
                return self._finish(request, target, CycleOutcome.SUCCESS,
                                    attempts, last_message)
            log.warning("Attempt %d failed: %s", attempts, last_message)

        return self._finish(request, None, CycleOutcome.FAILED, attempts,
                            last_message or "giving up after maximum attempts")

    def _attempt(self, request: PickRequest,
                 attempt: int) -> Tuple[Optional[DetectedObject], str]:
        """One try. Returns the placed object, or None and the reason why not."""
        self._state.set_status(
            f"cycle {self._cycle_index}: looking for objects "
            f"(attempt {attempt}/{self._max_attempts})"
        )

        scene = self._get_scene()
        if scene is None:
            return None, "no frame available from the camera"
        self._state.set_inference_time(scene.elapsed_ms)

        candidates = self._selector.select(scene.objects, request)
        if not candidates:
            return None, "no object matched the request"

        target = candidates[0]
        # Said BEFORE the command goes out, because the next thing that happens
        # is a wait of up to five minutes on a person. The robot has the
        # position and is sitting at the pendant waiting for the yellow button,
        # and a status line claiming to be "picking" through all of that is how
        # an operator comes to believe the system has hung.
        self._state.set_status(
            f"cycle {self._cycle_index}: sent {target.shape.value.lower()} "
            f"({target.colour.value.lower()}) at x={target.pose.x:.1f} "
            f"y={target.pose.y:.1f} rz={target.pose.rz:.1f}  -  "
            f"PRESS THE YELLOW BUTTON"
        )

        outcome = self._commander(target)
        self._state.set_status(
            f"cycle {self._cycle_index}: the robot is placing the "
            f"{target.shape.value.lower()}"
        )
        if outcome is not CycleOutcome.SUCCESS:
            return None, f"robot reported {outcome.value}"
        if not self._object_was_lifted(target):
            return None, "the object is still on the board"
        return target, "placed successfully"

    def _finish(self, request: PickRequest, target: Optional[DetectedObject],
                outcome: CycleOutcome, attempts: int, message: str) -> CycleReport:
        """Record the cycle's result where the GUI can see it, and return it."""
        report = CycleReport(
            cycle_index=self._cycle_index,
            request=request,
            target=target,
            outcome=outcome,
            attempts=attempts,
            message=message,
        )
        self._state.record_cycle(report)
        return report

    # --- checks around an attempt -------------------------------------------

    def _robot_is_ready(self) -> bool:
        """True once the robot is connected, waiting a bounded time for it.

        Counted in polls rather than against the clock, so the wait is the
        same length whatever `wait` does - and a test can run it instantly.
        """
        if self._robot_ready():
            return True
        for _ in range(self._connect_polls):
            self._state.set_status(
                f"cycle {self._cycle_index}: waiting for the robot to connect")
            if self._wait(ROBOT_POLL_S):
                return False                    # shutting down
            if self._robot_ready():
                return True
        return False

    def _object_was_lifted(self, target: DetectedObject) -> bool:
        """True if the object has gone from where the robot was sent."""
        if self._verify_tolerance_mm <= 0.0:
            return True

        scene = self._get_scene()
        if scene is None:
            return True

        for candidate in scene.objects:
            if candidate.shape is not target.shape:
                continue
            distance = math.hypot(candidate.pose.x - target.pose.x,
                                  candidate.pose.y - target.pose.y)
            if distance <= self._verify_tolerance_mm:
                return False
        return True
