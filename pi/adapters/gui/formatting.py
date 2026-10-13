"""How values are worded for the operator.

Kept apart from the Tk widgets so the wording can be tested on any machine,
including one with no display, and so the rules sit in one readable place.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from domain.models import DetectedObject

NO_ANGLE = "n/a"
# Short enough not to be truncated in the table column, and unambiguous when
# it is. "NO ANGLE" clipped to "NO AN" reads as nothing at all.
NOT_TRUSTED_MARK = "  WEAK"


def angle_confidence_text(obj: DetectedObject, gate: float) -> str:
    """How clearly the outline showed its symmetry, and what follows from it.

    A circle has no orientation, so there is nothing to measure and nothing to
    doubt. Anything else below the gate is placed unrotated, which is worth
    saying out loud: the object will be picked and put down, just not turned.
    """
    if obj.shape.is_rotationally_free:
        return NO_ANGLE
    value = obj.detection.angle_confidence
    return f"{value:.3f}" + ("" if obj.angle_trusted else NOT_TRUSTED_MARK)


def untrusted_angle_warning(objects) -> str:
    """One line naming every object that will be placed unrotated.

    Empty when there is nothing to warn about, so the caller can simply test
    it. Naming the shapes matters - "one object" sends the operator hunting.
    """
    doubtful = [o.shape.value for o in objects if not o.angle_trusted]
    if not doubtful:
        return ""
    shapes = ", ".join(sorted(doubtful))
    return (f"WEAK ANGLE  -  {shapes}  will be placed UNROTATED. ")
