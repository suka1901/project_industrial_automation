"""Worker threads and their supervision.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import List, Optional

from domain.models import Frame, InferenceResult, MappedScene
from application.coordinate_service import CoordinateService
from application.shared_state import SharedState
from application.vision_pipeline import VisionPipeline
from ports.interfaces import FrameSource

log = logging.getLogger(__name__)


def put_newest(target: queue.Queue, item) -> None:
    """Put an item on a bounded queue, dropping the oldest one if it is full.

    Every stage wants the newest data, never a backlog: a queue that blocked
    here would make a slow consumer stall the stage feeding it.
    """
    if target.full():
        try:
            target.get_nowait()
        except queue.Empty:
            pass
    target.put(item)


class Worker(threading.Thread):
    """A named thread that repeats one step until told to stop."""

    def __init__(self, name: str, shutdown: threading.Event) -> None:
        super().__init__(name=name, daemon=True)
        self._shutdown = shutdown

    def step(self) -> None:
        """One unit of work. Must return promptly so shutdown stays responsive."""
        raise NotImplementedError

    def on_start(self) -> None:
        """Optional set-up performed inside the thread."""

    def on_stop(self) -> None:
        """Optional clean-up, always run even after an error."""

    def run(self) -> None:
        log.info("%s started", self.name)
        try:
            self.on_start()
            while not self._shutdown.is_set():
                self.step()
        except Exception as exc:
            log.exception("%s crashed: %s", self.name, exc)
            self._shutdown.set()  # one dying thread stops the whole app
        finally:
            self.on_stop()
            log.info("%s stopped", self.name)


class CaptureWorker(Worker):
    """Thread 1 - keeps the newest camera frame available, nothing else."""

    def __init__(self, shutdown: threading.Event, source: FrameSource,
                 output: "queue.Queue[Frame]", max_fps: float = 10.0,
                 tap_path: Optional[str] = None,
                 tap_interval_s: float = 0.5) -> None:
        super().__init__("capture", shutdown)
        self._source = source
        self._output = output
        # The camera can only be opened once, so a calibration tool that needs
        # frames while this is running reads them from here instead.
        self._tap_path = tap_path
        self._tap_interval_s = tap_interval_s
        self._next_tap = 0.0
        # Without this the loop grabs as fast as the camera allows. The Basler
        # runs at 71.8 fps and inference does about 2.4, so 97% of those frames
        # are dropped unread - at 15 MB each that is roughly a gigabyte per
        # second of memory traffic, and a core pinned, to no purpose. It starves
        # the GUI thread, which is what "the GUI is lagging" turned out to be.
        self._min_interval_s = 1.0 / max_fps if max_fps > 0 else 0.0
        self._next_grab = 0.0

    def on_start(self) -> None:
        self._source.open()

    def step(self) -> None:
        # Wait out the remainder of the interval rather than sleeping a fixed
        # amount, so a slow read does not compound into a slower rate.
        if self._min_interval_s > 0.0:
            wait = self._next_grab - time.monotonic()
            if wait > 0.0 and self._shutdown.wait(wait):
                return
            self._next_grab = time.monotonic() + self._min_interval_s

        frame = self._source.read()
        if frame is None:
            self._shutdown.wait(0.02)  # brief pause instead of a busy spin
            return
        # Bounded queue: drop the stale frame rather than grow memory.
        put_newest(self._output, frame)
        self._write_tap(frame)

    def _write_tap(self, frame: Frame) -> None:
        """Drop the newest frame where another process can read it.

        Written to a temporary name and renamed into place, so a reader never
        opens a half-written image. JPEG rather than PNG: encoding 5 megapixels
        costs about 70 ms on the Pi against 400 ms for PNG, and the artefacts
        are far below what a contour cares about.
        """
        if not self._tap_path:
            return
        now = time.monotonic()
        if now < self._next_tap:
            return
        self._next_tap = now + self._tap_interval_s
        try:
            import cv2
            # The ".part" goes BEFORE the extension: imwrite picks the format
            # from the suffix, so a file ending .part is not an image it knows
            # how to write, and it fails silently returning False.
            root, _, extension = self._tap_path.rpartition(".")
            temporary = (f"{root}.part.{extension}" if root
                         else f"{self._tap_path}.part.jpg")
            if cv2.imwrite(temporary, frame.image,
                           [int(cv2.IMWRITE_JPEG_QUALITY), 92]):
                os.replace(temporary, self._tap_path)
        except Exception as exc:          # a tap must never stop the capture
            log.debug("Frame tap failed: %s", exc)

    def on_stop(self) -> None:
        self._source.close()


class InferenceWorker(Worker):
    """Thread 2 - runs the AI model, orientation and colour, and times it."""

    def __init__(self, shutdown: threading.Event, pipeline: VisionPipeline,
                 frames: "queue.Queue[Frame]",
                 results: "queue.Queue[InferenceResult]",
                 state: SharedState) -> None:
        super().__init__("inference", shutdown)
        self._pipeline = pipeline
        self._frames = frames
        self._results = results
        self._state = state

    def on_start(self) -> None:
        self._pipeline.warm_up()

    def step(self) -> None:
        try:
            frame = self._frames.get(timeout=0.2)
        except queue.Empty:
            return

        result = self._pipeline.process(frame)
        self._state.set_inference_time(result.elapsed_ms)
        # The GUI shows what the camera sees, whether or not a cycle is running.
        self._state.set_preview(frame.image, result.detections, frame.sequence)
        put_newest(self._results, result)


class MappingWorker(Worker):
    """Thread 3 - translates pixel detections into work object coordinates.

    Its own thread, as the assignment lists coordinate translation as a
    function in its own right. It also keeps the displayed positions live:
    the view shows where every object is right now, not only where the last
    cycle's target was.
    """

    def __init__(self, shutdown: threading.Event, coordinates: CoordinateService,
                 results: "queue.Queue[InferenceResult]",
                 scenes: "queue.Queue[MappedScene]",
                 state: SharedState) -> None:
        super().__init__("mapping", shutdown)
        self._coordinates = coordinates
        self._results = results
        self._scenes = scenes
        self._state = state

    def step(self) -> None:
        try:
            result = self._results.get(timeout=0.2)
        except queue.Empty:
            return

        # The homography is re-solved on the inference thread from each frame;
        # the mapper guards it with a lock, so reading it here is safe.
        scene = MappedScene(
            objects=tuple(self._coordinates.to_objects(result.detections)),
            elapsed_ms=result.elapsed_ms,
            frame_sequence=result.frame_sequence,
        )
        self._state.set_detections(scene.objects)
        put_newest(self._scenes, scene)


class LatestResultHolder:
    """Keeps the most recent item from a queue for the cycle controller to pull.

    Used for mapped scenes; it works for any queue whose newest item is the
    only one that matters.
    """

    def __init__(self, results: queue.Queue) -> None:
        self._results = results
        self._latest = None
        self._lock = threading.Lock()

    def __call__(self):
        """Return the freshest available item, waiting briefly if needed."""
        try:
            item = self._results.get(timeout=1.0)
        except queue.Empty:
            item = None

        with self._lock:
            if item is not None:
                self._latest = item
            # Drain anything that arrived while we waited.
            while True:
                try:
                    self._latest = self._results.get_nowait()
                except queue.Empty:
                    break
            return self._latest


class ThreadSupervisor:
    """Starts every worker and shuts them all down together."""

    def __init__(self, shutdown: threading.Event) -> None:
        self._shutdown = shutdown
        self._workers: List[threading.Thread] = []

    def add(self, worker: threading.Thread) -> None:
        self._workers.append(worker)

    def start_all(self) -> None:
        for worker in self._workers:
            worker.start()

    def stop_all(self, timeout_s: float = 5.0) -> None:
        """Signal shutdown and wait for every thread to finish."""
        self._shutdown.set()
        for worker in self._workers:
            worker.join(timeout=timeout_s)
            if worker.is_alive():
                log.warning("%s did not stop within %.1f s", worker.name, timeout_s)


class CycleWorker(Worker):
    """Thread 4 - owns the robot conversation and runs one cycle per request."""

    def __init__(self, shutdown: threading.Event, controller,
                 requests: "queue.Queue", state: SharedState) -> None:
        super().__init__("cycle", shutdown)
        self._controller = controller
        self._requests = requests
        self._state = state

    def step(self) -> None:
        try:
            request = self._requests.get(timeout=0.2)
        except queue.Empty:
            return

        report = self._controller.run_cycle(request)
        log.info("Cycle %d finished: %s after %d attempt(s) - %s",
                 report.cycle_index, report.outcome.value,
                 report.attempts, report.message)
        self._state.set_status(
            f"cycle {report.cycle_index}: {report.outcome.value.lower()} "
            f"({report.attempts} attempt(s))"
        )


class ConnectionWorker(Worker):
    """Thread 5 - brings the robot connection up and keeps the status current."""

    def __init__(self, shutdown: threading.Event, transport, state: SharedState,
                 quit_message: str = "quit#") -> None:
        super().__init__("connection", shutdown)
        self._transport = transport
        self._state = state
        self._quit_message = quit_message
        self._has_connected = False

    def step(self) -> None:
        if not self._has_connected:
            self._state.set_status("waiting for the robot to connect")
            try:
                self._transport.start()
                self._has_connected = True
                self._state.set_connected(True)
                self._state.set_status("robot connected - ready for a cycle")
            except Exception as exc:
                log.warning("Robot connection attempt failed: %s", exc)
                self._shutdown.wait(2.0)
            return

        # Once connected there is nothing to poll; just track the status.
        self._state.set_connected(self._transport.is_connected)
        self._shutdown.wait(1.0)

    def on_stop(self) -> None:
        if self._has_connected:
            try:
                self._transport.send(self._quit_message)
            except Exception as exc:
                log.debug("Could not send the quit message: %s", exc)
        self._transport.close()
        self._state.set_connected(False)
