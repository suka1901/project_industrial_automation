"""Reads the frame the running system last wrote out.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from domain.models import Frame
from ports.interfaces import FrameSource

log = logging.getLogger(__name__)


class TapFrameSource(FrameSource):
    """Re-reads one image file on every read(), so it follows a live tap."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._sequence = 0
        self._warned = False

    def open(self) -> None:
        if not self._path.is_file():
            raise FileNotFoundError(
                f"No frame tap at {self._path}. Set camera.frame_tap in the "
                f"profile main.py is running, and restart it.")

    def read(self) -> Optional[Frame]:
        import time

        import cv2

        # The writer renames a finished file into place, so a read never sees
        # a half-written image - but the file can still vanish for an instant
        # between the unlink and the rename on some filesystems.
        image = cv2.imread(str(self._path))
        if image is None:
            if not self._warned:
                log.warning("Frame tap %s could not be read - is main.py "
                            "still running?", self._path)
                self._warned = True
            return None

        self._warned = False
        self._sequence += 1
        return Frame(image=image, sequence=self._sequence,
                     captured_at=time.monotonic())

    def close(self) -> None:
        """Nothing to release - the writer owns the camera."""
