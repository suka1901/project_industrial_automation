"""Dataset bookkeeping for the capture tool.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

log = logging.getLogger(__name__)

IMAGE_SUFFIX = ".png"
# Scenes with several shapes together. Not a shape, so it gets its own folder
# rather than distorting the count of whichever shape happened to be selected.
MIXED = "mixed"
# Matches "circle_0007.png" and captures the number, so a new session continues
# numbering instead of overwriting yesterday's photos.
_INDEX_PATTERN = re.compile(r"_(\d+)$")


class CaptureSession:
    """Owns the dataset folder: where a photo goes and what it is called.

    Categories are plain names. Folder layout is capture bookkeeping only -
    YOLO takes its classes from the annotation files, never from the folder.
    """

    def __init__(self, root: Path, categories: Sequence[str]) -> None:
        self._root = Path(root)
        self._categories = [name.lower() for name in categories]

    # --- layout ------------------------------------------------------------

    def folder_for(self, category: str) -> Path:
        """One subfolder per category - labelling later is far quicker this way."""
        return self._root / category.lower()

    def prepare(self) -> None:
        """Create the folder tree. Safe to call every time the tool starts."""
        for category in self._categories:
            self.folder_for(category).mkdir(parents=True, exist_ok=True)
        log.info("Dataset ready at %s", self._root)

    # --- naming ------------------------------------------------------------

    def highest_index(self, category: str) -> int:
        """Largest photo number already present for this category, or 0."""
        folder = self.folder_for(category)
        if not folder.is_dir():
            return 0

        highest = 0
        for path in folder.glob(f"*{IMAGE_SUFFIX}"):
            match = _INDEX_PATTERN.search(path.stem)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest

    def next_path(self, category: str) -> Path:
        """Path for the next photo here, continuing the numbering."""
        index = self.highest_index(category) + 1
        return self.folder_for(category) / f"{category.lower()}_{index:04d}{IMAGE_SUFFIX}"

    # --- counts ------------------------------------------------------------

    def count(self, category: str) -> int:
        """How many photos exist for this category."""
        folder = self.folder_for(category)
        if not folder.is_dir():
            return 0
        return len(list(folder.glob(f"*{IMAGE_SUFFIX}")))

    def counts(self) -> Dict[str, int]:
        """Photo count per category, for the coverage readout in the GUI."""
        return {category: self.count(category) for category in self._categories}

    # --- saving ------------------------------------------------------------

    def save(self, image, category: str) -> Optional[Path]:
        """Write one full-resolution image and return where it landed."""
        import cv2

        if image is None:
            log.warning("Nothing to save - no image")
            return None

        self.folder_for(category).mkdir(parents=True, exist_ok=True)
        path = self.next_path(category)

        if not cv2.imwrite(str(path), image):
            log.error("Could not write %s", path)
            return None

        log.info("Saved %s", path)
        return path

    @property
    def categories(self) -> List[str]:
        return list(self._categories)

    @property
    def root(self) -> Path:
        return self._root
