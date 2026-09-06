"""Thread-safe state shared between the workers and the GUI.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import threading
from typing import Sequence

from domain.models import CycleReport, DetectedObject, StateSnapshot


class SharedState:
    """A small guarded record of "what the system looks like right now"."""

    def __init__(self) -> None:
        # RLock rather than Lock so a helper method may call another safely.
        self._lock = threading.RLock()
        self._snapshot = StateSnapshot()

    def snapshot(self) -> StateSnapshot:
        """Return the current immutable view. Cheap, and safe from any thread."""
        with self._lock:
            return self._snapshot

    def _replace(self, **changes) -> None:
        """Internal helper: swap in a new snapshot with some fields changed."""
        import dataclasses
        with self._lock:
            self._snapshot = dataclasses.replace(self._snapshot, **changes)

    # --- individual update methods, one per concern -----------------------

    def set_connected(self, connected: bool) -> None:
        self._replace(connected=connected)

    def set_inference_time(self, elapsed_ms: float) -> None:
        self._replace(inference_ms=elapsed_ms)

    def set_detections(self, detections: Sequence[DetectedObject]) -> None:
        # Stored as a tuple so the GUI cannot accidentally mutate the list.
        self._replace(detections=tuple(detections))

    def set_status(self, text: str) -> None:
        self._replace(status_text=text)

    def record_cycle(self, report: CycleReport) -> None:
        self._replace(last_report=report, cycle_index=report.cycle_index)
