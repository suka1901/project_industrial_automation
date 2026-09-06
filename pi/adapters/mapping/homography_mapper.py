"""Maps pixels to millimetres through a homography.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

from domain.models import PixelPoint
from ports.interfaces import CoordinateMapper

log = logging.getLogger(__name__)


class HomographyMapper(CoordinateMapper):
    """Applies a saved 3x3 homography to map pixels to millimetres."""

    def __init__(self, matrix: Optional[Any] = None) -> None:
        self._matrix = None
        if matrix is not None:
            self._set_matrix(matrix)

    def _set_matrix(self, matrix: Any) -> None:
        import numpy as np
        self._matrix = np.array(matrix, dtype="float64").reshape(3, 3)

    # --- persistence -------------------------------------------------------

    @classmethod
    def from_file(cls, path: str) -> "HomographyMapper":
        """Load a calibration produced by the calibration script."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        mapper = cls(data["homography"])
        log.info("Loaded homography from %s (residual %.2f mm)",
                 path, data.get("residual_mm", float("nan")))
        return mapper

    def save(self, path: str, residual_mm: float = 0.0) -> None:
        """Write the matrix and its fit quality to disk."""
        if self._matrix is None:
            raise RuntimeError("Nothing to save - mapper is not calibrated")
        payload = {
            "homography": self._matrix.tolist(),
            "residual_mm": residual_mm,
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("Saved homography to %s", path)

    # --- fitting -----------------------------------------------------------

    @classmethod
    def fit(
        cls,
        pixel_points: Sequence[Tuple[float, float]],
        world_points_mm: Sequence[Tuple[float, float]],
    ) -> Tuple["HomographyMapper", float]:
        """Solve the homography from matched point pairs."""
        import cv2
        import numpy as np

        if len(pixel_points) < 4:
            raise ValueError("At least four point pairs are required")

        source = np.array(pixel_points, dtype="float32").reshape(-1, 1, 2)
        target = np.array(world_points_mm, dtype="float32").reshape(-1, 1, 2)

        matrix, _ = cv2.findHomography(source, target, method=0)
        if matrix is None:
            raise RuntimeError("Homography solve failed - check your point pairs")

        projected = cv2.perspectiveTransform(source, matrix)
        residual = float(np.mean(np.linalg.norm(projected - target, axis=2)))

        return cls(matrix), residual

    # --- use ---------------------------------------------------------------

    def is_calibrated(self) -> bool:
        return self._matrix is not None

    def to_world_xy(self, point: PixelPoint) -> Tuple[float, float]:
        """Map one pixel to work object X and Y in millimetres."""
        if self._matrix is None:
            raise RuntimeError("Mapper is not calibrated")

        import numpy as np
        source = np.array([point.u, point.v, 1.0], dtype="float64")
        x, y, w = self._matrix @ source
        if abs(w) < 1e-9:
            raise ValueError(f"Degenerate projection for pixel {point}")
        return float(x / w), float(y / w)


class IdentityMapper(CoordinateMapper):
    """A trivial mapper for offline development: 1 pixel = ``scale`` millimetres."""

    def __init__(self, scale_mm_per_px: float = 0.5,
                 offset_mm: Tuple[float, float] = (0.0, 0.0)) -> None:
        self._scale = scale_mm_per_px
        self._offset = offset_mm

    def is_calibrated(self) -> bool:
        return True

    def to_world_xy(self, point: PixelPoint) -> Tuple[float, float]:
        return (point.u * self._scale + self._offset[0],
                point.v * self._scale + self._offset[1])


class MutableHomographyMapper(CoordinateMapper):
    """A homography that a live calibrator can replace while the system runs."""

    def __init__(self) -> None:
        import threading
        self._lock = threading.RLock()
        self._matrix = None
        self._scale_px_per_mm: Optional[float] = None

    def set_matrix(self, matrix, scale_px_per_mm: Optional[float] = None) -> None:
        """Install a freshly solved homography. Called by the calibrator."""
        import numpy as np
        with self._lock:
            self._matrix = np.array(matrix, dtype="float64").reshape(3, 3)
            self._scale_px_per_mm = scale_px_per_mm

    @property
    def scale_px_per_mm(self) -> Optional[float]:
        """Most recent pixels-per-millimetre estimate, for display and checks."""
        with self._lock:
            return self._scale_px_per_mm

    def is_calibrated(self) -> bool:
        with self._lock:
            return self._matrix is not None

    def to_world_xy(self, point: PixelPoint) -> Tuple[float, float]:
        """Map one pixel to work object X and Y in millimetres."""
        import numpy as np
        with self._lock:
            if self._matrix is None:
                raise RuntimeError("No calibration yet - the marker has not been seen")
            matrix = self._matrix

        x, y, w = matrix @ np.array([point.u, point.v, 1.0], dtype="float64")
        if abs(w) < 1e-9:
            raise ValueError(f"Degenerate projection for pixel {point}")
        return float(x / w), float(y / w)
