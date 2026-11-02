"""Averaging angles that wrap.

Every angle here is first folded into the shape's symmetry period and treated
as a direction rather than a number, which is the same trick the orientation
estimator uses on the outline itself.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple


def _phases(angles_deg: Sequence[float], period_deg: float) -> List[float]:
    """Each angle as a direction on the circle of one symmetry period."""
    turn = 2.0 * math.pi / period_deg
    return [angle * turn for angle in angles_deg]


def _resultant(angles_deg: Sequence[float], period_deg: float) -> Tuple[float, float, float]:
    """Mean cosine, mean sine, and their length. Length 1 means perfect agreement."""
    phases = _phases(angles_deg, period_deg)
    count = float(len(phases))
    cosine = sum(math.cos(p) for p in phases) / count
    sine = sum(math.sin(p) for p in phases) / count
    return cosine, sine, math.hypot(cosine, sine)


def circular_mean_deg(angles_deg: Sequence[float], period_deg: float) -> float:
    """Average orientation, folded into [0, period).

    Returns 0.0 for an empty input or a shape with no orientation, and for the
    degenerate case of readings that cancel exactly - there is no meaningful
    average direction then, and inventing one would be worse than saying zero.
    """
    if not angles_deg or period_deg <= 0.0:
        return 0.0

    cosine, sine, length = _resultant(angles_deg, period_deg)
    if length < 1e-9:
        return 0.0

    degrees = math.degrees(math.atan2(sine, cosine)) * period_deg / 360.0
    folded = degrees % period_deg
    # A hair under the period is the same orientation as zero. Reporting
    # 89.999 for a square would read like a quarter turn from 0, not like it.
    if period_deg - folded < 1e-6:
        return 0.0
    return folded


def circular_spread_deg(angles_deg: Sequence[float], period_deg: float) -> float:
    """How much the readings disagree, in degrees of the shape's own angle.

    This is the number that says whether one stored slot angle is trustworthy:
    it is the play in the slot plus the measurement noise, and the placement
    has to tolerate all of it.
    """
    if len(angles_deg) < 2 or period_deg <= 0.0:
        return 0.0

    _, _, length = _resultant(angles_deg, period_deg)
    if length >= 1.0:
        return 0.0
    if length < 1e-9:
        return period_deg / 2.0        # completely scattered

    # Circular standard deviation, converted from phase back into the shape's
    # own degrees so it can be compared against the symmetry period directly.
    phase_sd = math.sqrt(-2.0 * math.log(length))
    return math.degrees(phase_sd) * period_deg / 360.0
