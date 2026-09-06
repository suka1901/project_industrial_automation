"""Measure how accurately the outline pipeline reads an angle, without labels.

Ground truth comes from rotating the photo by a known amount: whatever the
angle is, it must move by exactly that. Run it after a shooting session or a
lighting change to confirm the orientation stage still holds up.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""
from __future__ import annotations

import glob
import math
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from domain.orientation import harmonic_orientation, resample_radial  # noqa: E402

DATASET = BASE_DIR / ".." / "model" / "dataset" / "raw" / "mixed"

PAD = 8
ORDERS = (3, 4, 5, 6)
MIN_SIDE, MAX_SIDE = 120, 400        # real objects are 180-260 px; excludes the
                                     # sheet outline and the 519 px marker sheet


def find_objects(img):
    """Filled masks and boxes for the objects lying on the A3 sheet.

    The sheet is isolated first. Without that the dark table joins every object
    into one blob spanning the whole frame.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    v, s = hsv[:, :, 2], hsv[:, :, 1]
    sheet_level = float(np.percentile(v, 95))

    sheet = ((v > 0.55 * sheet_level) & (s < 80)).astype(np.uint8)
    sheet = cv2.morphologyEx(sheet, cv2.MORPH_CLOSE, np.ones((61, 61), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(sheet, 8)
    if count < 2:
        return []
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    # Eroded, so the sheet's own edge against the table is not an "object".
    inside = cv2.erode((labels == biggest).astype(np.uint8), np.ones((41, 41), np.uint8))

    # On the sheet, an object is darker than the paper or coloured. 0.80 rather
    # than 0.55 so white objects on white paper are not missed.
    on = (((v < 0.80 * sheet_level) | (s >= 70)).astype(np.uint8)) & inside
    on = cv2.morphologyEx(on, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    on = cv2.morphologyEx(on, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))

    contours, _ = cv2.findContours(on, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    found = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (MIN_SIDE < w < MAX_SIDE and MIN_SIDE < h < MAX_SIDE):
            continue
        if not 0.6 < w / float(h) < 1.7:
            continue
        if cv2.contourArea(contour) < 0.25 * w * h:
            continue
        filled = np.zeros(on.shape, np.uint8)
        cv2.drawContours(filled, [contour], -1, 255, -1)
        found.append(((x, y, w, h), filled))
    return found


def otsu_mask(crop):
    """Exactly what HarmonicOrientationEstimator._mask does."""
    grey = cv2.GaussianBlur(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    _, m = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if m[m.shape[0] // 2, m.shape[1] // 2] == 0:
        m = cv2.bitwise_not(m)
    return m


def signature(mask):
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return None
    pts = [(float(p[0][0]), float(p[0][1])) for p in max(cs, key=cv2.contourArea)]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return resample_radial(
        [(math.atan2(y - cy, x - cx), math.hypot(x - cx, y - cy)) for x, y in pts],
        bins=180)


def crop_rotated(img, box, degrees):
    """Crop the object after rotating the FULL image, so the background stays real."""
    x, y, w, h = box
    cx, cy = x + w / 2.0, y + h / 2.0
    m = cv2.getRotationMatrix2D((cx, cy), degrees, 1.0)
    rotated = cv2.warpAffine(img, m, (img.shape[1], img.shape[0]),
                             flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    half = int(max(w, h) / 2) + PAD
    y0, y1 = max(0, int(cy) - half), min(img.shape[0], int(cy) + half)
    x0, x1 = max(0, int(cx) - half), min(img.shape[1], int(cx) + half)
    return rotated[y0:y1, x0:x1]


def fold(a, n):
    period = 360.0 / n
    return (a + period / 2) % period - period / 2


rows = []
for path in sorted(glob.glob(str(DATASET.resolve() / "*.png")))[::7][:10]:
    img = cv2.imread(path)
    sheet95 = float(np.percentile(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 95))
    for box, filled in find_objects(img):
        x, y, w, h = box
        inside = filled[y:y + h, x:x + w] > 0
        hsv = cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_BGR2HSV)
        sat = float(hsv[:, :, 1][inside].mean())
        val = float(hsv[:, :, 2][inside].mean())
        # The hard case is a LIGHT object on light paper. Black objects also
        # have low saturation but plenty of contrast, so value decides.
        if val > 0.75 * sheet95:
            kind = "white"
        elif sat < 70:
            kind = "black"
        else:
            kind = "colour"
        contrast = abs(val - sheet95) / max(sheet95, 1.0)

        base = signature(otsu_mask(crop_rotated(img, box, 0.0)))
        if base is None:
            continue

        # Rotation consistency at every candidate order. At run time the order
        # is known exactly - YOLO gives the class - so this asks the real
        # question: given the right N, how good is the outline?
        per_order = {}
        for n in ORDERS:
            a0, z0 = harmonic_orientation(base, n)
            errors = []
            for delta in (13.0, 29.0, 47.0):
                sig = signature(otsu_mask(crop_rotated(img, box, delta)))
                if sig is None:
                    continue
                a1, _ = harmonic_orientation(sig, n)
                errors.append(abs(fold(a1 - a0 + delta, n)))
            if errors:
                per_order[n] = (max(errors), z0)

        if not per_order:
            continue
        best_n = min(per_order, key=lambda n: per_order[n][0])
        argmax_n = max(per_order, key=lambda n: per_order[n][1])
        rows.append((Path(path).name, kind, sheet95, contrast, best_n,
                     per_order[best_n][1], per_order[best_n][0], argmax_n,
                     per_order[argmax_n][0]))

print(f"{'photo':17s} {'kind':6s} {'sheet':>5s} {'contr':>6s} | "
      f"{'bestN':>5s} {'|Z|':>5s} {'err':>7s} | {'argmaxN':>7s} {'its err':>8s}")
for r in rows:
    print(f"{r[0]:17s} {r[1]:6s} {r[2]:5.0f} {r[3]:6.2f} | "
          f"{r[4]:5d} {r[5]:5.3f} {r[6]:6.2f}d | {r[7]:7d} {r[8]:7.2f}d")

for kind in ("colour", "black", "white"):
    sel = [r for r in rows if r[1] == kind]
    if not sel:
        continue
    errs = [r[6] for r in sel]
    print(f"\n{kind}: n={len(sel)}  correct-order error: median {np.median(errs):.2f} deg, "
          f"worst {max(errs):.2f} deg, under 2 deg: {sum(1 for e in errs if e < 2.0)}/{len(errs)}")
    print(f"  median |Z| at that order: {np.median([r[5] for r in sel]):.3f}")
    print(f"  picking the order by |Z| instead would agree "
          f"{sum(1 for r in sel if r[4] == r[7])}/{len(sel)} times")

print("\n--- does |Z| predict the error? (all objects, correct order) ---")
for low, high in ((0.0, 0.05), (0.05, 0.10), (0.10, 1.0)):
    sel = [r for r in rows if low <= r[5] < high]
    if sel:
        errs = [r[6] for r in sel]
        print(f"  |Z| {low:.2f}-{high:.2f}: n={len(sel):3d}  median {np.median(errs):6.2f} deg  "
              f"worst {max(errs):6.2f} deg  under 2 deg: {sum(1 for e in errs if e < 2.0)}/{len(errs)}")
