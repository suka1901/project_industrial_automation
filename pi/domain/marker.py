"""Where an ArUco marker's corners sit in work object millimetres.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import math
from typing import List, Tuple

# Corner order used by cv2.aruco.detectMarkers, in a marker-local frame whose
# origin is the marker centre, X to the right and Y upwards. Multiplied by
# half the side length at call time.
_UNIT_CORNERS: Tuple[Tuple[float, float], ...] = (
    (-1.0, +1.0),   # top-left
    (+1.0, +1.0),   # top-right
    (+1.0, -1.0),   # bottom-right
    (-1.0, -1.0),   # bottom-left
)


def marker_world_corners(
    side_length_mm: float,
    centre_xy_mm: Tuple[float, float],
    angle_deg: float = 0.0,
    y_axis_flipped: bool = False,
) -> List[Tuple[float, float]]:
    """The marker's four corners in work object millimetres.

    Returned in the order detectMarkers reports the image corners: top-left,
    top-right, bottom-right, bottom-left. y_axis_flipped mirrors Y, which is
    needed when the work object Y runs opposite to the marker frame.
    """
    if side_length_mm <= 0.0:
        raise ValueError("Marker side length must be positive")

    half = side_length_mm / 2.0
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    centre_x, centre_y = centre_xy_mm
    y_sign = -1.0 if y_axis_flipped else 1.0

    corners: List[Tuple[float, float]] = []
    for unit_x, unit_y in _UNIT_CORNERS:
        local_x = unit_x * half
        local_y = unit_y * half * y_sign
        # Standard 2D rotation, then translate to the marker's place on the table.
        corners.append((
            centre_x + local_x * cos_t - local_y * sin_t,
            centre_y + local_x * sin_t + local_y * cos_t,
        ))
    return corners


def pixel_mm_ratio_from_perimeter(perimeter_px: float, side_length_mm: float) -> float:
    """Pixels per millimetre from a marker's perimeter - the course's method."""
    if side_length_mm <= 0.0:
        raise ValueError("Marker side length must be positive")
    return perimeter_px / (side_length_mm * 4.0)
