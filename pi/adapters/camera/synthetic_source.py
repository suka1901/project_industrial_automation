"""Emits empty frames, for running with no hardware at all.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import time
from typing import Optional

from domain.models import Frame
from ports.interfaces import FrameSource


class SyntheticFrameSource(FrameSource):
    """Emits placeholder frames at a fixed rate. Carries no image data."""

    def __init__(self, fps: float = 10.0) -> None:
        self._interval_s = 1.0 / max(fps, 0.1)
        self._sequence = 0

    def open(self) -> None:
        """Nothing to acquire."""

    def read(self) -> Optional[Frame]:
        time.sleep(self._interval_s)
        self._sequence += 1
        return Frame(image=None, sequence=self._sequence,
                     captured_at=time.monotonic())

    def close(self) -> None:
        """Nothing to release."""
