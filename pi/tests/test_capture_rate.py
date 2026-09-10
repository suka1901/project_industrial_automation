"""Tests that the capture loop does not run flat out.

Without a throttle the loop grabs as fast as the source allows. On the real
camera that is 71.8 fps of 15 MB frames - about a gigabyte a second - while
inference consumes about 2.4 of them. The other 97% are dropped unread, and
the core spent producing them is a core the GUI is not getting.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import queue
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from domain.models import Frame
from infrastructure.runtime import CaptureWorker


class InstantSource:
    """A source with no cost at all, so only the throttle limits the rate."""

    def __init__(self):
        self.reads = 0

    def open(self):
        pass

    def close(self):
        pass

    def read(self):
        self.reads += 1
        return Frame(image=np.zeros((4, 4, 3), np.uint8),
                     sequence=self.reads, captured_at=0.0)


def grabs_in(seconds: float, max_fps: float) -> int:
    source, frames, stop = InstantSource(), queue.Queue(maxsize=2), threading.Event()
    worker = CaptureWorker(stop, source, frames, max_fps=max_fps)
    thread = threading.Thread(target=worker.run, daemon=True)
    thread.start()
    time.sleep(seconds)
    stop.set()
    thread.join(timeout=2.0)
    return source.reads


class TestCaptureRate(unittest.TestCase):

    def test_the_rate_is_bounded(self):
        """The assertion that matters: not thousands. Generous bounds, because
        a timing test on a loaded machine should not be the flaky one."""
        reads = grabs_in(0.5, max_fps=20.0)
        self.assertLess(reads, 40, "the throttle is not limiting the loop")
        self.assertGreater(reads, 2, "the throttle is starving the loop")

    def test_a_higher_limit_grabs_more(self):
        slow = grabs_in(0.5, max_fps=6.0)
        fast = grabs_in(0.5, max_fps=30.0)
        self.assertGreater(fast, slow)

    def test_zero_means_unlimited(self):
        """0 disables the throttle - kept so a bench test can still run flat
        out deliberately, rather than silently."""
        self.assertGreater(grabs_in(0.2, max_fps=0.0), 100)

    def test_it_stops_promptly_while_waiting(self):
        """The wait must be interruptible: at 1 fps a shutdown that waited out
        the interval would hang the whole application for a second."""
        source, frames, stop = InstantSource(), queue.Queue(maxsize=2), threading.Event()
        worker = CaptureWorker(stop, source, frames, max_fps=1.0)
        thread = threading.Thread(target=worker.run, daemon=True)
        thread.start()
        time.sleep(0.1)
        started = time.monotonic()
        stop.set()
        thread.join(timeout=2.0)
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
