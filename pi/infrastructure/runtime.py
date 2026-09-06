"""Worker threads and their supervision.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import List, Optional

from domain.models import Frame, InferenceResult
from application.shared_state import SharedState
from application.vision_pipeline import VisionPipeline
from ports.interfaces import FrameSource

log = logging.getLogger(__name__)


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
                 output: "queue.Queue[Frame]") -> None:
        super().__init__("capture", shutdown)
        self._source = source
        self._output = output

    def on_start(self) -> None:
        self._source.open()

    def step(self) -> None:
        frame = self._source.read()
        if frame is None:
            self._shutdown.wait(0.02)  # brief pause instead of a busy spin
            return
        # Bounded queue: drop the stale frame rather than grow memory.
        if self._output.full():
            try:
                self._output.get_nowait()
            except queue.Empty:
                pass
        self._output.put(frame)

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

        if self._results.full():
            try:
                self._results.get_nowait()
            except queue.Empty:
                pass
        self._results.put(result)


class LatestResultHolder:
    """Keeps the most recent inference result for the cycle controller to pull."""

    def __init__(self, results: "queue.Queue[InferenceResult]") -> None:
        self._results = results
        self._latest: Optional[InferenceResult] = None
        self._lock = threading.Lock()

    def __call__(self) -> Optional[InferenceResult]:
        """Return the freshest available result, waiting briefly if needed."""
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
    """Thread 3 - owns the robot conversation and runs one cycle per request."""

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
    """Thread 4 - brings the robot connection up and keeps the status current."""

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
