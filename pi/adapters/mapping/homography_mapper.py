"""Maps pixels to millimetres through a homography.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from domain.models import PixelPoint
from ports.interfaces import CoordinateMapper

log = logging.getLogger(__name__)


def project(matrix: Any, point: PixelPoint) -> Tuple[float, float]:
    """Apply a 3x3 homography to one pixel and return millimetres.

    [x' y' w']T = H . [u v 1]T,  then x = x'/w', y = y'/w'.
    """
    import numpy as np

    x, y, w = matrix @ np.array([point.u, point.v, 1.0], dtype="float64")
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
        with self._lock:
            if self._matrix is None:
                raise RuntimeError("No calibration yet - the marker has not been seen")
            matrix = self._matrix
        return project(matrix, point)
