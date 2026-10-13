"""Orientation from the radial signature of an outline.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

# (angle in radians from the centroid, distance to the outline)
RadialSample = Tuple[float, float]

DEFAULT_BINS = 180


def resample_radial(samples: Sequence[RadialSample],
                    bins: int = DEFAULT_BINS) -> Optional[List[float]]:
    """Put the outline on an evenly spaced angular grid."""
    if bins < 8 or not samples:
        return None

    width = 2.0 * math.pi / bins
    grid: List[Optional[float]] = [None] * bins

    for angle, radius in samples:
        index = int((angle % (2.0 * math.pi)) / width) % bins
        current = grid[index]
        if current is None or radius > current:
            grid[index] = radius

    filled = [index for index, value in enumerate(grid) if value is not None]
    if len(filled) < bins // 2:
        # More than half the directions saw no outline at all - this is not a
        # closed shape seen from its middle, so refuse rather than invent it.
        return None

    if len(filled) == bins:
        return [value for value in grid if value is not None]

    # Circular linear interpolation across the gaps.
    complete: List[float] = []
    for index in range(bins):
        value = grid[index]
        if value is not None:
            complete.append(value)
            continue

        before = max((i for i in filled if i <= index), default=filled[-1] - bins)
        after = min((i for i in filled if i >= index), default=filled[0] + bins)
        span = after - before
        weight = 0.0 if span == 0 else (index - before) / span
        low = grid[before % bins]
        high = grid[after % bins]
        complete.append((low or 0.0) * (1.0 - weight) + (high or 0.0) * weight)

    return complete


def harmonic_orientation(radii: Sequence[float], order: int) -> Tuple[float, float]:
    """Orientation in degrees and a 0-1 confidence, from a radial signature.
    """
    if order <= 0 or len(radii) < 8:
        return 0.0, 0.0

    total = sum(radii)
    if total <= 0.0:
        return 0.0, 0.0

    step = 2.0 * math.pi / len(radii)
    real = 0.0
    imaginary = 0.0
    for index, radius in enumerate(radii):
        phase = order * index * step
        real += radius * math.cos(phase)
        imaginary += radius * math.sin(phase)

    magnitude = math.hypot(real, imaginary)
    if magnitude <= 1e-9:
        return 0.0, 0.0

    # arg() lands in (-pi, pi], so dividing by the order lands the answer in
    # (-180/order, 180/order] - the symmetry period, for free.
    degrees = math.degrees(math.atan2(imaginary, real)) / order

    # Normalised so a flat signature scores 0 and a strongly N-lobed one scores
    # high. Not a probability, just a comparable number.
    confidence = min(1.0, 2.0 * magnitude / total)

    return degrees, confidence
