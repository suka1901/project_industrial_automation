"""Fitting a 2448 x 2048 camera frame onto a laptop screen.

The measurement always runs on the full-resolution frame; only the picture
shown to the operator is shrunk. Anything the operator draws on the shrunken
picture has to be scaled back up before it is used, which is what
`to_full_resolution` is for.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from typing import Any, Tuple

DISPLAY_WIDTH = 1100        # comfortable on a laptop; nothing measures this


def display_scale(image: Any, width: int = DISPLAY_WIDTH) -> float:
    """Shrink factor for the preview. 1.0 when the frame already fits."""
    if image is None or image.shape[1] <= 0:
        return 1.0
    return min(1.0, float(width) / float(image.shape[1]))


def shrink(image: Any, scale: float) -> Any:
    """A copy of the frame at display size."""
    import cv2
    if scale >= 1.0:
        return image.copy()
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def to_full_resolution(box: Tuple[int, int, int, int],
                       scale: float) -> Tuple[int, int, int, int]:
    """Map an (x, y, w, h) drawn on the preview back onto the real frame.

    Skipping this is the trap: the box would look right on screen and then
    search the wrong part of the image, a tenth of the way in from the corner.
    """
    if scale <= 0.0:
        return tuple(int(v) for v in box)
    return tuple(int(round(v / scale)) for v in box)
