"""Fitting a 2448 x 2048 camera frame onto a laptop screen.

The measurement always runs on the full-resolution frame; only the picture
shown to the operator is shrunk. Anything the operator draws on the shrunken
picture has to be scaled back up before it is used, which is what
`to_full_resolution` is for.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from typing import Any, Sequence, Tuple

DISPLAY_WIDTH = 1100        # comfortable on a laptop; nothing measures this
DISPLAY_HEIGHT = 760        # a 2448x2048 frame is still 920 tall at 1100 wide


def display_scale(image: Any, width: int = DISPLAY_WIDTH,
                  height: int = DISPLAY_HEIGHT) -> float:
    """Shrink factor for the preview. 1.0 when the frame already fits.

    Both dimensions are honoured. Fitting the width alone leaves a 2448x2048
    frame 920 pixels tall, which still runs off a 768 or 900 pixel screen -
    the bottom of the picture, and the readout drawn on it, simply vanish.
    """
    if image is None or image.shape[1] <= 0 or image.shape[0] <= 0:
        return 1.0
    return min(1.0,
               float(width) / float(image.shape[1]),
               float(height) / float(image.shape[0]))


def shrink(image: Any, scale: float) -> Any:
    """A copy of the frame at display size."""
    import cv2
    if scale >= 1.0:
        return image.copy()
    return cv2.resize(image, (0, 0), fx=scale, fy=scale,
                      interpolation=cv2.INTER_AREA)


def to_full_resolution(box: Sequence[float],
                       scale: float) -> Tuple[int, int, int, int]:
    """Map an (x, y, w, h) drawn on the preview back onto the real frame.

    Skipping this is the trap: the box would look right on screen and then
    search the wrong part of the image, a tenth of the way in from the corner.
    """
    x, y, w, h = box
    if scale <= 0.0:
        return int(x), int(y), int(w), int(h)
    return (int(round(x / scale)), int(round(y / scale)),
            int(round(w / scale)), int(round(h / scale)))
