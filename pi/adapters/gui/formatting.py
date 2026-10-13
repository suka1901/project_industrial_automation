"""How values are worded for the operator.

Kept apart from the Tk widgets so the wording can be tested on any machine,
including one with no display, and so the rules sit in one readable place.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from domain.models import DetectedObject

NO_ANGLE = "n/a"


def angle_confidence_text(obj: DetectedObject) -> str:
    """How well an ideal shape fitted the object's outline, 0 to 1.

    Information, not a warning: every object is placed at the best angle that
    could be worked out for it, and this says how good that reading was. A
    circle has no orientation, so there is nothing to fit.
    """
    if obj.shape.is_rotationally_free:
        return NO_ANGLE
    return f"{obj.detection.angle_confidence:.3f}"
