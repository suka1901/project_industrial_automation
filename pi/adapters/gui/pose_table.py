"""The detections as figures, for the window to show beside the picture.

The course asks the GUI to display each detected object's position and
orientation. The overlay shows both - a marker at the centre, a ray along
every symmetry axis - and a picture is the better way to catch a misread,
because a ray lying across the object's own arm is obviously right in a way
that reading 156.5 in a table never is. But a ray cannot be quoted, and an
examiner asking to see the position and orientation is asking for numbers.

Kept apart from tk_view so it can be tested without a display: formatting is
the part with decisions in it, and Tk is not needed to make them.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from typing import Sequence

NOTHING = "no objects in view"

# Enough rows to see a full table without the window resizing itself while
# the operator is looking at it.
MAX_ROWS = 8

HEADER = (f"{'shape':<8}{'colour':<8}{'x mm':>8}{'y mm':>8}"
          f"{'angle':>8}{'rz':>8}{'fit':>6}")

# A circle has no orientation, so it has no angle, no rotation to command and
# no fit to report. Saying so beats printing three zeros that look measured.
NONE_MARK = "-"


def pose_table(objects: Sequence) -> str:
    """One line per object: where it is, how it lies, and how sure of that.

    `angle` is what the camera measured, in its own frame. `rz` is what the
    robot will be told - the turn from that angle to the slot, folded into
    the shape's symmetry. They are different numbers on purpose: seeing both
    is what distinguishes a misread object from a mis-taught slot.
    """
    if not objects:
        return NOTHING

    lines = [HEADER]
    for item in objects[:MAX_ROWS]:
        detection, pose = item.detection, item.pose
        free = detection.shape.is_rotationally_free
        angle = NONE_MARK if free else f"{detection.angle_deg:.1f}"
        turn = NONE_MARK if free else f"{pose.rz:.1f}"
        fit = NONE_MARK if free else f"{detection.angle_confidence:.2f}"
        lines.append(f"{detection.shape.value:<8}{detection.colour.value:<8}"
                     f"{pose.x:>8.1f}{pose.y:>8.1f}{angle:>8}{turn:>8}{fit:>6}")

    hidden = len(objects) - MAX_ROWS
    if hidden > 0:
        lines.append(f"... and {hidden} more")
    return "\n".join(lines)
