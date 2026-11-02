"""Score the orientation estimator against known rotations.

There are no angle labels in the dataset - only boxes - so the ground truth is
made rather than found: every labelled object is rotated by a known amount and
the estimator is asked to recover it. That is also the honest question to ask,
because a constant offset common to every reading cancels in the robot: the
slot angles are measured with the same estimator.

Needs no camera, no robot and no ultralytics - it reads the label boxes
instead of running the detector, and the full-resolution raw frames, so the
crops are the size the live camera really gives.

    python3 tools/orientation_bench.py                  # the estimator
    python3 tools/orientation_bench.py --gates          # where to set the gate
    python3 tools/orientation_bench.py --shape square --limit 60

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import collections
import logging
import math
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from domain.enums import Colour, Shape                              # noqa: E402
from domain.models import BoundingBox, Detection, Frame             # noqa: E402

DATA = (BASE_DIR / ".." / "model" / "dataset").resolve()
RAW_FOLDERS = ("circle", "square", "star", "mixed", "hexagon", "triangle")
LABELLED = {0: Shape.CIRCLE, 1: Shape.SQUARE, 2: Shape.STAR}
# Chosen to be nothing special: not multiples of either symmetry period, and
# not near the half-period where a sign error hides.
TURNS = (11.0, 29.0, 47.0, 67.0, 83.0)
PADDING_PX = 4


def build_estimators() -> Dict[str, Tuple[object, float]]:
    """The estimator, with the gate a reading must clear to be counted.

    Still a dictionary, and still called "estimators", because the question
    this tool answers is "is a change an improvement" - which means running
    two of something side by side. Add the candidate here and the table
    grows a row; that is how the fitted one earned its place over the
    harmonic one it replaced.
    """
    from adapters.detection.fitted_orientation_estimator import FittedOrientationEstimator
    return {
        "fitted (gate 0.80)": (
            FittedOrientationEstimator(padding_px=PADDING_PX), 0.80),
    }


def wrap(value: float, period: float) -> float:
    """Signed distance to the nearest multiple of the symmetry period."""
    value %= period
    return value - period if value > period / 2.0 else value


def raw_frame_for(stem: str) -> Optional[Path]:
    """The full-resolution photo behind a labelled, downscaled one."""
    for folder in RAW_FOLDERS:
        candidate = DATA / "raw" / folder / f"{stem}.png"
        if candidate.is_file():
            return candidate
    return None


def labelled_objects(shape_filter: Optional[str], limit: int, seed: int = 7):
    """(raw photo, shape, normalised box) for every labelled square and star."""
    found = []
    for label in sorted((DATA / "label" / "labels").glob("*.txt")):
        raw = raw_frame_for(label.stem)
        if raw is None:
            continue
        for row in label.read_text(encoding="utf-8").splitlines():
            parts = row.split()
            if len(parts) != 5:
                continue
            shape = LABELLED[int(parts[0])]
            if shape.is_rotationally_free:
                continue                       # a circle has no angle to score
            if shape_filter and shape.value.lower() != shape_filter:
                continue
            found.append((raw, shape, tuple(float(v) for v in parts[1:])))
    random.Random(seed).shuffle(found)
    return found[:limit]


def turned_crop(image, box, turn_deg: float):
    """The crop a detector would hand over, after turning the scene.

    Positive turn_deg is anticlockwise on screen, OpenCV's own convention, so
    a correct estimator's reading must move by MINUS that amount.
    """
    import cv2

    height, width = image.shape[:2]
    centre_x, centre_y = box[0] * width, box[1] * height
    box_w, box_h = box[2] * width, box[3] * height

    reach = int(1.3 * math.hypot(box_w, box_h))
    left, top = int(centre_x) - reach, int(centre_y) - reach
    right, bottom = int(centre_x) + reach, int(centre_y) + reach
    if left < 0 or top < 0 or right > width or bottom > height:
        return None                      # too near the frame edge to turn

    region = image[top:bottom, left:right]
    middle = (region.shape[1] / 2.0, region.shape[0] / 2.0)
    if turn_deg:
        region = cv2.warpAffine(
            region, cv2.getRotationMatrix2D(middle, turn_deg, 1.0),
            (region.shape[1], region.shape[0]), flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE)

    # Where the box lands after the same turn, as an upright box again.
    radians = math.radians(turn_deg)
    corners = [(-box_w / 2, -box_h / 2), (box_w / 2, -box_h / 2),
               (box_w / 2, box_h / 2), (-box_w / 2, box_h / 2)]
    turned = [(x * math.cos(radians) + y * math.sin(radians),
               -x * math.sin(radians) + y * math.cos(radians)) for x, y in corners]
    half_w = max(abs(x) for x, _ in turned) + PADDING_PX
    half_h = max(abs(y) for _, y in turned) + PADDING_PX
    crop = region[max(0, int(middle[1] - half_h)):int(middle[1] + half_h),
                  max(0, int(middle[0] - half_w)):int(middle[0] + half_w)]
    return crop if crop.size else None


def read(estimator, crop, shape: Shape):
    """Measure one crop, as the pipeline would, and time it."""
    height, width = crop.shape[:2]
    whole = BoundingBox(0.0, 0.0, float(width), float(height))
    detection = Detection(shape=shape, colour=Colour.UNKNOWN, confidence=1.0,
                          centre=whole.centre, angle_deg=0.0, box=whole)
    started = time.perf_counter()
    measured = estimator.measure(Frame(image=crop, sequence=0, captured_at=0.0),
                                 detection)
    return measured, (time.perf_counter() - started) * 1000.0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--shape", default=None, choices=("square", "star"))
    parser.add_argument("--gates", action="store_true",
                        help="show how a confidence gate trades coverage "
                             "for accuracy, at several thresholds")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)        # the estimator warns, loudly
    import cv2

    objects = labelled_objects(args.shape, args.limit)
    if not objects:
        print(f"No labelled objects under {DATA}. This tool needs the dataset, "
              f"which lives outside the Pi bundle.")
        return 1

    estimators = build_estimators()
    if args.gates:
        from adapters.detection.fitted_orientation_estimator import (
            FittedOrientationEstimator)
        # min_fit 0 so nothing is refused before the gate itself is applied.
        estimators = {"fitted": (FittedOrientationEstimator(padding_px=PADDING_PX,
                                                            min_fit=0.0), 0.0)}

    rows: Dict[Tuple[str, str], Dict] = collections.defaultdict(
        lambda: {"objects": 0, "usable": 0, "scored": [], "ms": []})

    for raw, shape, box in objects:
        image = cv2.imread(str(raw))
        crops = {}
        for turn in (0.0,) + TURNS:
            crop = turned_crop(image, box, turn)
            if crop is None:
                crops = {}
                break
            crops[turn] = crop
        if not crops:
            continue

        period = 360.0 / shape.symmetry_order
        for name, (estimator, gate) in estimators.items():
            row = rows[(shape.value.lower(), name)]
            readings = {}
            for turn, crop in crops.items():
                measured, elapsed = read(estimator, crop, shape)
                readings[turn] = measured
                row["ms"].append(elapsed)

            row["objects"] += 1
            base = readings[0.0]
            if base.confidence < gate:
                continue                     # refused: no angle would be sent
            row["usable"] += 1
            for turn in TURNS:
                other = readings[turn]
                if other.confidence < gate:
                    continue
                row["scored"].append(
                    (abs(wrap(other.angle_deg - base.angle_deg + turn, period)),
                     min(base.confidence, other.confidence)))

    report(rows, gates=args.gates)
    return 0


def percentile(values: List[float], fraction: float) -> float:
    return sorted(values)[int(fraction * (len(values) - 1))]


def report(rows, gates: bool) -> None:
    if gates:
        print(f"{'shape':7s}{'gate':>6}{'kept':>7}{'med err':>9}{'p90 err':>9}"
              f"{'<2 deg':>8}")
        for (shape, _), row in sorted(rows.items()):
            for gate in (0.0, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90):
                kept = [e for e, quality in row["scored"] if quality >= gate]
                if len(kept) < 5:
                    continue
                print(f"{shape:7s}{gate:6.2f}{len(kept) / len(row['scored']):7.0%}"
                      f"{statistics.median(kept):9.2f}{percentile(kept, 0.9):9.2f}"
                      f"{sum(1 for e in kept if e < 2.0) / len(kept):8.0%}")
        return

    print(f"{'shape':7s}{'estimator':24s}{'usable':>9}{'med err':>9}{'p90 err':>9}"
          f"{'<3 deg':>8}{'ms/obj':>8}")
    for (shape, name), row in sorted(rows.items()):
        errors = [error for error, _ in row["scored"]]
        if not errors:
            print(f"{shape:7s}{name:24s}{row['usable']}/{row['objects']:<5d}"
                  f"   nothing measurable")
            continue
        print(f"{shape:7s}{name:24s}{row['usable']}/{row['objects']:<5d}"
              f"{statistics.median(errors):9.2f}{percentile(errors, 0.9):9.2f}"
              f"{sum(1 for e in errors if e < 3.0) / len(errors):8.0%}"
              f"{statistics.mean(row['ms']):8.1f}")


if __name__ == "__main__":
    raise SystemExit(main())
