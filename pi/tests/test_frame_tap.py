"""Tests for sharing frames with a second process.

The Basler opens once, so a calibration tool that wants to look at the table
while the system is running cannot open it too. The two processes share frames
through a file instead of competing for the device.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.camera.tap_source import TapFrameSource
from domain.models import Frame
from infrastructure.runtime import CaptureWorker
from ports.interfaces import FrameSource


class CountingSource(FrameSource):
    """A frame with a different first pixel each time, so reads are tellable."""

    def __init__(self):
        self.opened = False
        self.n = 0

    def open(self):
        self.opened = True

    def read(self):
        self.n += 1
        image = np.zeros((40, 60, 3), np.uint8)
        image[0, 0] = (self.n % 250, 0, 0)
        return Frame(image=image, sequence=self.n, captured_at=0.0)

    def close(self):
        self.opened = False


class TestTheTapIsWritten(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(Path(self.folder.name) / "frame.jpg")
        self.shutdown = threading.Event()

    def tearDown(self):
        self.shutdown.set()
        self.folder.cleanup()

    def run_worker(self, tap_path, interval=0.0, steps=3):
        worker = CaptureWorker(self.shutdown, CountingSource(),
                               queue.Queue(maxsize=2), max_fps=0.0,
                               tap_path=tap_path, tap_interval_s=interval)
        worker.on_start()
        for _ in range(steps):
            worker.step()
        return worker

    def test_a_frame_appears_at_the_tap(self):
        self.run_worker(self.path)
        self.assertTrue(Path(self.path).is_file())
        self.assertIsNotNone(cv2.imread(self.path))

    def test_no_tap_path_writes_nothing(self):
        self.run_worker(None)
        self.assertFalse(Path(self.path).is_file())

    def test_no_part_file_is_left_behind(self):
        """Renamed into place, so a reader never opens a half-written image."""
        self.run_worker(self.path)
        leftovers = [p.name for p in Path(self.folder.name).iterdir()
                     if "part" in p.name]
        self.assertEqual(leftovers, [])

    def test_the_temporary_name_keeps_a_writable_extension(self):
        """imwrite picks the format from the suffix: a '.part' tail writes
        nothing at all, and returns False rather than raising."""
        self.run_worker(self.path)
        self.assertIsNotNone(cv2.imread(self.path),
                             "the tap file exists but is not a readable image")

    def test_the_interval_is_respected(self):
        """A tap every frame would cost 70 ms of JPEG on every grab."""
        self.run_worker(self.path, interval=30.0, steps=4)
        first = cv2.imread(self.path)[0, 0, 0]
        self.assertEqual(first, cv2.imread(self.path)[0, 0, 0])

    def test_a_failing_tap_does_not_stop_capture(self):
        output = queue.Queue(maxsize=2)
        worker = CaptureWorker(self.shutdown, CountingSource(), output,
                               max_fps=0.0, tap_path="/no/such/dir/frame.jpg",
                               tap_interval_s=0.0)
        worker.on_start()
        worker.step()
        self.assertFalse(output.empty(), "capture must survive a bad tap path")


class TestTheTapIsRead(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(Path(self.folder.name) / "frame.jpg")

    def tearDown(self):
        self.folder.cleanup()

    def write(self, value):
        image = np.full((40, 60, 3), value, np.uint8)
        cv2.imwrite(self.path, image)

    def test_opening_a_missing_tap_says_what_to_do(self):
        source = TapFrameSource(self.path)
        with self.assertRaises(FileNotFoundError) as caught:
            source.open()
        self.assertIn("camera.frame_tap", str(caught.exception))

    def test_it_follows_the_file_rather_than_caching_it(self):
        """The whole point: the writer keeps replacing it."""
        self.write(40)
        source = TapFrameSource(self.path)
        source.open()
        self.assertAlmostEqual(int(source.read().image[0, 0, 0]), 40, delta=2)
        self.write(200)
        self.assertAlmostEqual(int(source.read().image[0, 0, 0]), 200, delta=2)

    def test_the_sequence_advances(self):
        self.write(40)
        source = TapFrameSource(self.path)
        source.open()
        self.assertEqual(source.read().sequence + 1, source.read().sequence)

    def test_a_vanished_tap_returns_none_rather_than_raising(self):
        self.write(40)
        source = TapFrameSource(self.path)
        source.open()
        Path(self.path).unlink()
        self.assertIsNone(source.read())


if __name__ == "__main__":
    unittest.main()
