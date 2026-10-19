"""Tests for the coordinate-translation thread.

The worker's step() is called directly, so no thread is started.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import queue
import threading
import unittest

from domain.enums import Colour, Shape
from domain.models import Detection, InferenceResult, PixelPoint
from application.coordinate_service import CoordinateService
from application.shared_state import SharedState
from adapters.mapping.homography_mapper import IdentityMapper
from infrastructure.runtime import LatestResultHolder, MappingWorker, put_newest


def make_result(sequence):
    detection = Detection(shape=Shape.SQUARE, colour=Colour.BLUE, confidence=0.9,
                          centre=PixelPoint(100.0, 50.0), angle_deg=10.0,
                          angle_confidence=0.5)
    return InferenceResult(detections=(detection,), elapsed_ms=420.0,
                           frame_sequence=sequence)


class TestMappingWorker(unittest.TestCase):
    def setUp(self):
        self.results = queue.Queue(maxsize=2)
        self.scenes = queue.Queue(maxsize=2)
        self.state = SharedState()
        self.worker = MappingWorker(threading.Event(),
                                    CoordinateService(IdentityMapper()),
                                    self.results, self.scenes, self.state)

    def test_translates_a_result_into_a_scene(self):
        self.results.put(make_result(7))
        self.worker.step()
        scene = self.scenes.get_nowait()
        self.assertEqual(scene.frame_sequence, 7)
        self.assertEqual(scene.elapsed_ms, 420.0)
        self.assertEqual(len(scene.objects), 1)
        self.assertIs(scene.objects[0].shape, Shape.SQUARE)

    def test_publishes_live_positions_for_the_view(self):
        self.results.put(make_result(1))
        self.worker.step()
        self.assertEqual(len(self.state.snapshot().detections), 1)

    def test_nothing_waiting_is_not_an_error(self):
        self.worker.step()          # returns after its short timeout
        self.assertTrue(self.scenes.empty())

    def test_holder_hands_the_cycle_the_newest_scene(self):
        for sequence in (1, 2, 3):
            self.results.put(make_result(sequence))
            self.worker.step()
        newest = LatestResultHolder(self.scenes)()
        assert newest is not None, "the holder came back empty"
        self.assertEqual(newest.frame_sequence, 3)


class TestPutNewest(unittest.TestCase):
    def test_a_full_queue_drops_its_oldest_item(self):
        target = queue.Queue(maxsize=2)
        for item in (1, 2, 3):
            put_newest(target, item)
        self.assertEqual([target.get_nowait(), target.get_nowait()], [2, 3])


if __name__ == "__main__":
    unittest.main()
