"""Separates an object from the paper it lies on, inside a detection box.

Both the colour classifier and the orientation estimator need the object's own
pixels rather than the whole bounding box: a star fills barely a third of its
box, so anything averaged over the box is really measuring the paper.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from typing import Any

# A mask covering this much of the crop is the paper, not the object. Even a
# square that fills its box leaves the padding, so anything near the whole
# crop means the segmentation grabbed the wrong side of the threshold.
WHOLE_CROP_FRACTION = 0.92

# The share of a crop's gradient magnitudes that belong to the object's border.
# An outline is thin: a few pixels wide round one shape in a box barely bigger
# than it is.
EDGE_PERCENTILE = 88.0


def object_mask(crop: Any, threshold: int = 0) -> Any:
    """Binary mask of the object within a crop, 255 where the object is.

    `threshold` of 0 means Otsu, which follows the lighting on its own.

    The object may be lighter or darker than the paper, so one of the two
    polarities is right and the other is the paper around it. Both are scored
    and the better one wins.
    """
    import cv2

    grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    grey = cv2.GaussianBlur(grey, (5, 5), 0)

    if threshold > 0:
        _, mask = cv2.threshold(grey, threshold, 255, cv2.THRESH_BINARY)
    else:
        _, mask = cv2.threshold(grey, 0, 255,
                                cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    inverted = cv2.bitwise_not(mask)
    return mask if plausibility(mask) >= plausibility(inverted) else inverted


def plausibility(mask: Any) -> float:
    """How much this polarity looks like an object the detector framed.

    The detector put the object in the middle of the box, so the object fills
    the middle and does not fill the border. Scored as the difference, which
    lands near +1 for the right polarity and near -1 for the paper, so the two
    are never close enough for noise to decide between them.
    """
    return middle_fraction(mask) - border_fraction(mask)


def middle_fraction(mask: Any) -> float:
    """How much of the crop's middle third is set."""
    height, width = mask.shape[:2]
    import numpy as np

    top, bottom = height // 3, height - height // 3
    left, right = width // 3, width - width // 3
    middle = mask[top:max(bottom, top + 1), left:max(right, left + 1)]
    if middle.size == 0:
        return 0.0
    return float(np.count_nonzero(middle)) / float(middle.size)


def border_fraction(mask: Any) -> float:
    """How much of the crop's outermost ring of pixels is set."""
    import numpy as np

    edges = np.concatenate([mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]])
    if edges.size == 0:
        return 0.0
    return float(np.count_nonzero(edges)) / float(edges.size)


def contrast_levels(crop: Any, threshold: int = 0) -> float:
    """Grey-level separation between the object and the paper it lies on.
    """
    import cv2
    import numpy as np

    grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    grey = cv2.GaussianBlur(grey, (5, 5), 0)
    if threshold > 0:
        split = float(threshold)
    else:
        split, _ = cv2.threshold(grey, 0, 255,
                                 cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark, light = grey[grey <= split], grey[grey > split]
    if dark.size == 0 or light.size == 0:
        return 0.0
    return float(np.median(light) - np.median(dark))


# A mask can sit below WHOLE_CROP_FRACTION and still be the paper: the hole
# the object leaves in it is filled by clean_mask, and what remains stops a
# little short of the corners.
PAPER_BORDER_FRACTION = 0.35


def looks_like_paper(mask: Any, limit: float = PAPER_BORDER_FRACTION) -> bool:
    """True when this mask is the sheet around the object, not the object.

    Worth a test of its own because a filled rectangle fits an ideal SQUARE
    convincingly - 0.70 and 0.63 on the two white-on-white photos, well above
    the threshold that decides a reading can be trusted. A wrong angle that
    arrives with a good score is the one failure the fit cannot catch by
    itself: it is the shape of the crop being measured, not the shape of the
    object, and the crop is a rectangle no matter how the object lies.
    """
    return border_fraction(mask) > limit


def covers_whole_crop(contour_area: float, mask: Any,
                      limit: float = WHOLE_CROP_FRACTION) -> bool:
    """True when the object's outline is essentially the entire crop.

    Neither polarity was plausible - usually glare, or lighting flat enough
    that Otsu split noise instead of the object. Worth saying out loud,
    because the outline is then the crop rectangle and every measurement
    taken from it describes the box rather than the shape.

    Takes the largest contour's AREA rather than the mask's pixel count, so a
    mask speckled with noise outside the object still reads as a failure only
    when the object itself has swollen to fill the box.
    """
    if mask.size == 0:
        return True
    return float(contour_area) / float(mask.size) >= limit


# --------------------------------------------------------------------------
# Other ways to find the object
#
# Otsu above asks "is this pixel darker than that one", which is the only
# question a white object on white paper cannot answer: the two differ by
# three or four grey levels, less than the sensor's noise. The alternatives
# below ask different questions - is it a different COLOUR, is there an EDGE
# here - and each wins on objects where the others fail. Nothing chooses
# between them in advance; best_mask does it per object, by shape.
# --------------------------------------------------------------------------


def clean_mask(mask: Any) -> Any:
    """Fill pinholes, drop speckle, and keep the blob nearest the middle.

    The detector framed the object, so the object is the blob in the middle;
    a second object clipped at the edge of the crop is not ours to measure.
    """
    import cv2
    import numpy as np

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return mask

    height, width = mask.shape[:2]
    middle = np.array([width / 2.0, height / 2.0])
    best, best_score = 0, -1.0
    for index in range(1, count):
        area = float(stats[index, cv2.CC_STAT_AREA])
        distance = float(np.linalg.norm(centroids[index] - middle))
        score = area / (1.0 + distance ** 2)       # big, and near the middle
        if score > best_score:
            best, best_score = index, score
    return np.where(labels == best, 255, 0).astype("uint8")


def _fill_outline(edges: Any) -> Any:
    """Close a traced boundary and fill what it encloses."""
    import cv2
    import numpy as np

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return closed
    filled = np.zeros_like(closed)
    cv2.drawContours(filled, [max(contours, key=cv2.contourArea)], -1, 255, -1)
    return filled


def otsu_mask(crop: Any, threshold: int = 0) -> Any:
    """object_mask, tidied up - the brightness route."""
    return clean_mask(object_mask(crop, threshold))


def _paper_colour(lab: Any) -> Any:
    """The paper's own colour, read from the border ring of the crop."""
    import numpy as np

    ring = np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]])
    return np.median(ring.reshape(-1, 3), axis=0)


def chroma_mask(crop: Any, threshold: int = 0) -> Any:
    """Distance from the paper's HUE, which no shadow changes.

    A shadow darkens L and leaves a and b alone, so dropping L is what stops
    the mask following the shadow's edge instead of the object's. Useless on
    a white or black object, which has no hue at all - hence the fall back.
    """
    import cv2
    import numpy as np

    lab = cv2.cvtColor(cv2.GaussianBlur(crop, (5, 5), 0),
                       cv2.COLOR_BGR2LAB).astype("float32")
    distance = np.linalg.norm(lab[:, :, 1:] - _paper_colour(lab)[1:], axis=2)
    if float(distance.max()) < 6.0:
        return otsu_mask(crop, threshold)     # no colour to separate on
    scaled = np.clip(distance / distance.max() * 255.0, 0, 255).astype("uint8")
    _, mask = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return clean_mask(mask)


def gradient_mask(crop: Any, threshold: int = 0) -> Any:
    """Threshold the gradient, then fill the outline it traces.

    This is the route that works on a white object: its border still steps in
    brightness and casts a hairline shadow, and a gradient reads the step
    rather than the level.
    """
    import cv2
    import numpy as np

    grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    grey = cv2.GaussianBlur(grey, (5, 5), 0)
    magnitude = cv2.magnitude(cv2.Scharr(grey, cv2.CV_32F, 1, 0),
                              cv2.Scharr(grey, cv2.CV_32F, 0, 1))
    magnitude = cv2.GaussianBlur(magnitude, (7, 7), 0)

    # A percentile rather than Otsu, which is what makes this route work on
    # the object it exists for. Otsu splits the magnitudes into two groups of
    # comparable weight; on a white object the border's step is a thin
    # minority against a wide flat interior, so the split lands ABOVE the
    # border and keeps only the few brightest pixels - one per cent of the
    # crop, nothing to fill. 
    cut = float(np.percentile(magnitude, EDGE_PERCENTILE))
    edges = ((magnitude >= cut) * 255).astype("uint8")
    return clean_mask(_fill_outline(edges))


def edge_mask(crop: Any, threshold: int = 0) -> Any:
    """Canny's boundary, filled. Strict: it finds little, but what it finds is good."""
    import cv2
    import numpy as np

    grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    grey = cv2.bilateralFilter(grey, 7, 40, 7)      # smooth, but keep edges
    median = float(np.median(grey))
    edges = cv2.Canny(grey, int(max(0.0, 0.66 * median)),
                      int(min(255.0, 1.33 * median)), L2gradient=True)
    return clean_mask(_fill_outline(edges))


# Tried in this order. Cheapest first only matters for the log; every one is
# run, because the point is to compare them.
CANDIDATE_MASKS = {
    "otsu": otsu_mask,
    "chroma": chroma_mask,
    "gradient": gradient_mask,
    "edges": edge_mask,
}
