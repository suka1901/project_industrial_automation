"""Tests for the cycle logic, its retries, and its wait for the robot.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest

from domain.enums import Colour, CycleOutcome, Shape
from domain.models import Detection, MappedScene, PickRequest, PixelPoint
from application.coordinate_service import CoordinateService
from application.cycle_controller import CycleController
from application.selectors import AllowedShapeSelector
from application.shared_state import SharedState
from adapters.mapping.homography_mapper import IdentityMapper


def make_scene():
    """One red star, already mapped - what the mapping thread would hand over."""
    detection = Detection(shape=Shape.STAR, colour=Colour.RED, confidence=0.95,
                          centre=PixelPoint(120.0, 240.0), angle_deg=30.0,
                          angle_confidence=0.5)
    objects = CoordinateService(IdentityMapper()).to_objects([detection])
    return MappedScene(objects=tuple(objects), elapsed_ms=180.0, frame_sequence=1)


class FakeClock:
    """Records every pause instead of sleeping, and can fake a shutdown."""

    def __init__(self, stop_after=None):
        self.pauses = []
        self._stop_after = stop_after

    def __call__(self, seconds):
        self.pauses.append(seconds)
        return self._stop_after is not None and len(self.pauses) >= self._stop_after


class TestCycleController(unittest.TestCase):
    def _build(self, outcomes, robot_ready=lambda: True, clock=None, **options):
        self.calls = []
        self.clock = clock or FakeClock()

        def commander(target):
            self.calls.append(target)
            return outcomes.pop(0)

        return CycleController(
            get_scene=make_scene,
            selector=AllowedShapeSelector([Shape.STAR]),
            commander=commander,
            state=SharedState(),
            max_attempts=3,
            robot_ready=robot_ready,
            wait=self.clock,
            **options,
        )

    def test_success_on_first_attempt(self):
        controller = self._build([CycleOutcome.SUCCESS])
        report = controller.run_cycle(PickRequest())
        self.assertIs(report.outcome, CycleOutcome.SUCCESS)
        self.assertEqual(report.attempts, 1)
        self.assertEqual(self.clock.pauses, [])      # no retry, no pause

    def test_retries_twice_then_succeeds(self):
        controller = self._build([CycleOutcome.FAILED,
                                  CycleOutcome.FAILED,
                                  CycleOutcome.SUCCESS])
        report = controller.run_cycle(PickRequest())
        self.assertIs(report.outcome, CycleOutcome.SUCCESS)
        self.assertEqual(report.attempts, 3)

    def test_gives_up_after_three_attempts(self):
        controller = self._build([CycleOutcome.FAILED] * 3)
        report = controller.run_cycle(PickRequest())
        self.assertIs(report.outcome, CycleOutcome.FAILED)
        self.assertEqual(len(self.calls), 3)

    def test_cycle_index_increments(self):
        controller = self._build([CycleOutcome.SUCCESS, CycleOutcome.SUCCESS])
        self.assertEqual(controller.run_cycle(PickRequest()).cycle_index, 1)
        self.assertEqual(controller.run_cycle(PickRequest()).cycle_index, 2)

    def test_pauses_before_each_retry_only(self):
        controller = self._build([CycleOutcome.FAILED] * 3, retry_delay_s=1.5)
        controller.run_cycle(PickRequest())
        # Three attempts, so two pauses - never one before the first try.
        self.assertEqual(self.clock.pauses, [1.5, 1.5])

    def test_no_attempt_is_spent_while_the_robot_is_away(self):
        controller = self._build([], robot_ready=lambda: False, connect_wait_s=0)
        report = controller.run_cycle(PickRequest())
        self.assertIs(report.outcome, CycleOutcome.FAILED)
        self.assertEqual(report.attempts, 0)
        self.assertEqual(self.calls, [])
        self.assertIn("not connected", report.message)

    def test_waits_for_the_robot_then_picks(self):
        answers = iter([False, False, True])
        controller = self._build([CycleOutcome.SUCCESS],
                                 robot_ready=lambda: next(answers),
                                 connect_wait_s=5.0)
        report = controller.run_cycle(PickRequest())
        self.assertIs(report.outcome, CycleOutcome.SUCCESS)
        self.assertEqual(report.attempts, 1)
        self.assertEqual(len(self.clock.pauses), 2)

    def test_connection_wait_is_bounded(self):
        controller = self._build([], robot_ready=lambda: False, connect_wait_s=2.0)
        report = controller.run_cycle(PickRequest())
        self.assertEqual(report.attempts, 0)
        self.assertEqual(len(self.clock.pauses), 4)     # 2.0 s at 0.5 s a poll

    def test_robot_lost_mid_cycle_stops_the_retries(self):
        answers = iter([True, False])
        controller = self._build([CycleOutcome.FAILED],
                                 robot_ready=lambda: next(answers),
                                 connect_wait_s=0)
        report = controller.run_cycle(PickRequest())
        self.assertEqual(report.attempts, 1)
        self.assertIn("not connected", report.message)

    def test_shutdown_during_the_pause_ends_the_cycle(self):
        controller = self._build([CycleOutcome.FAILED] * 3,
                                 clock=FakeClock(stop_after=1),
                                 retry_delay_s=1.5)
        report = controller.run_cycle(PickRequest())
        self.assertEqual(report.attempts, 1)
        self.assertIn("shutting down", report.message)

    def test_object_still_on_the_board_is_retried(self):
        controller = self._build([CycleOutcome.SUCCESS] * 3,
                                 verify_tolerance_mm=12.0)
        report = controller.run_cycle(PickRequest())
        # The fake scene never changes, so the star is always "still there".
        self.assertIs(report.outcome, CycleOutcome.FAILED)
        self.assertEqual(report.attempts, 3)
        self.assertIn("still on the board", report.message)


if __name__ == "__main__":
    unittest.main()


class TestWhatTheOperatorIsTold(unittest.TestCase):
    """The wait after sending is a wait on a PERSON - up to five minutes of it.

    A status line that says "picking" through all of that is how an operator
    comes to believe the system has hung and starts restarting things."""

    def _run_one_cycle(self):
        state = SharedState()
        seen = []

        def commander(target):
            seen.append(state.snapshot().status_text)   # what it says mid-wait
            return CycleOutcome.SUCCESS

        CycleController(
            get_scene=make_scene,
            selector=AllowedShapeSelector([Shape.STAR]),
            commander=commander,
            state=state,
            wait=FakeClock(),
        ).run_cycle(PickRequest())
        return seen[0], state.snapshot().status_text

    def test_it_asks_for_the_yellow_button_while_the_robot_waits(self):
        while_waiting, _ = self._run_one_cycle()
        self.assertIn("YELLOW BUTTON", while_waiting)
        self.assertIn("star", while_waiting)

    def test_and_says_the_robot_is_moving_once_it_is(self):
        _, afterwards = self._run_one_cycle()
        self.assertIn("placing", afterwards)
