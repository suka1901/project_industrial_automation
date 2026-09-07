"""How values are worded for the operator.

Kept apart from the Tk widgets so the wording can be tested on any machine,
including one with no display, and so the rules sit in one readable place.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from domain.models import DetectedObject

NO_ANGLE = "n/a"
SKIP_MARK = "  SKIP"


def angle_confidence_text(obj: DetectedObject, gate: float) -> str:
    """How clearly the outline showed its symmetry, and what follows from it.

    A circle has no orientation, so there is nothing to measure and nothing to
    gate on. Anything else below the gate is skipped rather than placed
    crooked - and saying so is the difference between an operator understanding
    a skipped object and being baffled by one the camera clearly sees.
    """
    if obj.shape.is_rotationally_free:
        return NO_ANGLE
    value = obj.detection.angle_confidence
    return f"{value:.3f}" + (SKIP_MARK if value < gate else "")
