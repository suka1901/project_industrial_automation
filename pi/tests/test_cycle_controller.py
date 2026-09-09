"""Tests for the cycle logic and its retries.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest

from domain.enums import Colour, CycleOutcome, Shape
from domain.models import Detection, InferenceResult, PickRequest, PixelPoint
from application.coordinate_service import CoordinateService
from application.cycle_controller import CycleController
from application.selectors import AllowedShapeSelector
from application.shared_state import SharedState
from adapters.mapping.homography_mapper import IdentityMapper


def make_inference():
    detection = Detection(shape=Shape.STAR, colour=Colour.RED, confidence=0.95,
                          centre=PixelPoint(120.0, 240.0), angle_deg=30.0)
    return InferenceResult(detections=(detection,), elapsed_ms=180.0,
                           frame_sequence=1)


class TestCycleController(unittest.TestCase):
    def _build(self, outcomes):
        self.calls = []

        def commander(target):
            self.calls.append(target)
            return outcomes.pop(0)

        return CycleController(
            get_inference=make_inference,
            coordinates=CoordinateService(IdentityMapper()),
            selector=AllowedShapeSelector([Shape.STAR]),
            commander=commander,
            state=SharedState(),
            max_attempts=3,
        )

    def test_success_on_first_attempt(self):
        controller = self._build([CycleOutcome.SUCCESS])
        report = controller.run_cycle(PickRequest())
        self.assertIs(report.outcome, CycleOutcome.SUCCESS)
        self.assertEqual(report.attempts, 1)

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


if __name__ == "__main__":
    unittest.main()
