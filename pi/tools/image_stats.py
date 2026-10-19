"""Cheap statistics over a photo, shared by the dataset tools.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def sheet_brightness(path: Path) -> float:
    """95th percentile grey - the A3 sheet. Used to spread the sample evenly.

    Read at quarter size: a percentile does not need 5 megapixels, and these
    files are large enough that full reads dominate the run time.
    """
    import cv2
    import numpy as np

    image = cv2.imread(str(path), cv2.IMREAD_REDUCED_GRAYSCALE_4)
    if image is None:
        return 0.0
    return float(np.percentile(np.asarray(image, dtype=np.float64), 95))
