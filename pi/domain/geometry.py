"""Rotation maths: folding an angle into a shape's symmetry.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from domain.enums import Shape


def wrap_deg(angle_deg: float, period_deg: float) -> float:
    """Wrap ``angle_deg`` into the half-open interval [0, period_deg)."""
    if period_deg <= 0.0:
        return 0.0
    return angle_deg % period_deg


def normalise_for_shape(angle_deg: float, shape: Shape, slot_angle_deg: float = 0.0) -> float:
    """Reduce a measured angle to the smallest rotation that still fits the slot."""
    if shape.is_rotationally_free:
        return 0.0

    period = shape.symmetry_period_deg
    delta = wrap_deg(angle_deg - slot_angle_deg, period)

    # Prefer the shorter of the two equivalent rotations, e.g. +80 deg on a
    # square becomes -10 deg, which the wrist reaches far more comfortably.
    if delta > period / 2.0:
        delta -= period
    return delta


def place_rotation_deg(
    object_angle_deg: float,
    shape: Shape,
    slot_angle_deg: float = 0.0,
) -> float:
    """Wrist rotation to apply when PLACING the object.

    A suction cup picks straight down, so the object arrives on the cup still
    at its own angle. Seating it in a slot at slot_angle_deg needs a turn of
    slot - object, folded into the shape's symmetry so it stays small.
    """
    if shape.is_rotationally_free:
        return 0.0
    return normalise_for_shape(slot_angle_deg - object_angle_deg, shape, 0.0)
