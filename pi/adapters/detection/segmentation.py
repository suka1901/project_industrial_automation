"""Separates an object from the paper it lies on, inside a detection box.

Both the colour classifier and the orientation estimator need the object's own
pixels rather than the whole bounding box: a star fills barely a third of its
box, so anything averaged over the box is really measuring the paper.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from typing import Any


def object_mask(crop: Any, threshold: int = 0) -> Any:
    """Binary mask of the object within a crop, 255 where the object is.

    `threshold` of 0 means Otsu, which follows the lighting on its own. The
    object may be lighter or darker than the paper, so the polarity is chosen
    by whichever fills the middle of the crop - the detector put it there.
    """
    import cv2

    grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    grey = cv2.GaussianBlur(grey, (5, 5), 0)

    if threshold > 0:
        _, mask = cv2.threshold(grey, threshold, 255, cv2.THRESH_BINARY)
    else:
        _, mask = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    if mask[mask.shape[0] // 2, mask.shape[1] // 2] == 0:
        mask = cv2.bitwise_not(mask)
    return mask
