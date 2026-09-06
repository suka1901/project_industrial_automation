"""Replays saved images, so the system runs with no camera.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List, Optional

from domain.models import Frame
from ports.interfaces import FrameSource

log = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


class FileFrameSource(FrameSource):
    """Loops through every image in a directory, one per read()."""

    def __init__(self, directory: str, loop: bool = True) -> None:
        self._directory = Path(directory)
        self._loop = loop
        self._paths: List[Path] = []
        self._index = 0
        self._sequence = 0

    def open(self) -> None:
        """Collect and sort the image files so replay order is repeatable."""
        if not self._directory.is_dir():
            raise FileNotFoundError(f"Frame directory not found: {self._directory}")
        self._paths = sorted(
            p for p in self._directory.iterdir()
            if p.suffix.lower() in _IMAGE_SUFFIXES
        )
        if not self._paths:
            raise FileNotFoundError(f"No images in {self._directory}")
        log.info("FileFrameSource loaded %d image(s) from %s",
                 len(self._paths), self._directory)

    def read(self) -> Optional[Frame]:
        """Return the next image, wrapping around when loop is enabled."""
        import cv2  # imported here so the domain/test path stays dependency-free

        if not self._paths:
            return None
        if self._index >= len(self._paths):
            if not self._loop:
                return None
            self._index = 0

        path = self._paths[self._index]
        self._index += 1

        image = cv2.imread(str(path))
        if image is None:
            log.warning("Could not read image %s", path)
            return None

        self._sequence += 1
        return Frame(image=image, sequence=self._sequence,
                     captured_at=time.monotonic())

    def close(self) -> None:
        """Nothing to release for a file source."""
        self._paths = []
