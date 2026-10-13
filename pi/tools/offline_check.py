"""Run the whole vision pipeline over held-out photos, with no hardware.

Ultralytics' own metrics only judge the detector. This judges what the robot
will actually be told: shape, colour, and whether the angle was measured well
enough to place on. It compares against the labels, so it needs no camera.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import collections
import logging
import statistics
import sys
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))


from domain.models import Frame  # noqa: E402
from infrastructure.container import Container  # noqa: E402
from infrastructure.config_loader import load_config  # noqa: E402
from infrastructure.logging_setup import configure_logging  # noqa: E402

log = logging.getLogger("offline_check")


def ground_truth(label: Path, names: Dict[int, str]) -> collections.Counter:
    """Objects the labels say are in one photo."""
    counts: collections.Counter = collections.Counter()
    if not label.is_file():
        return counts
    for row in label.read_text(encoding="utf-8").splitlines():
        if row.strip():
            counts[names[int(row.split()[0])]] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the pipeline over held-out photos and score it")
    parser.add_argument("--config", default="config/profiles/offline.yaml")
    parser.add_argument("--split", default=None,
                        help="default model/dataset/yolo/val")
    args = parser.parse_args()

    configure_logging(level="ERROR", log_file=None)
    import cv2

    config = load_config(BASE_DIR / args.config)
    class_map = config.get("detector", {}).get("class_map", {})
    names = {index: str(class_map[index]).upper() for index in sorted(class_map)}

    split = Path(args.split) if args.split else \
        (BASE_DIR / ".." / "model" / "dataset" / "yolo" / "val").resolve()
    labels = split / "labels"
    if not labels.is_dir():
        # ground_truth() treats a missing label file as "nothing expected", so
        # without this the run completes and reports a confidently wrong score
        # for all 55 photos - which is worse than failing.
        log.error("No labels under %s. Every photo would score against an "
                  "empty ground truth and the result would be meaningless. "
                  "The Pi bundle must include model/dataset/yolo/val/labels "
                  "as well as val/images.", labels)
        return 1

    images = sorted((split / "images").glob("*.jpg"))
    if not images:
        log.error("No photos under %s - run tools/split_dataset.py first", split / "images")
        return 1

    print(f"{len(images)} photo(s) from {split.name}, loading the model...")
    pipeline = Container(config, BASE_DIR).build_vision_pipeline()
    pipeline.warm_up()

    matched = missed = spurious = exact = 0
    colours: collections.Counter = collections.Counter()
    confidence: Dict[str, List[float]] = collections.defaultdict(list)
    # Not a gate - nothing is refused on the fit any more. These are the
    # readings the system would have had to guess at, which is what to look
    # at when a placement came out crooked.
    guessed: List[str] = []
    guess_below = float(config.get("orientation", {}).get("min_fit", 0.60))

    for path in images:
        image = cv2.imread(str(path))
        detections = pipeline.process(
            Frame(image=image, sequence=0, captured_at=0.0)).detections

        found: collections.Counter = collections.Counter()
        for detection in detections:
            found[detection.shape.value.upper()] += 1
            colours[detection.colour.value] += 1
            confidence[detection.shape.value.upper()].append(detection.angle_confidence)
            if (not detection.shape.is_rotationally_free
                    and detection.angle_confidence < guess_below):
                guessed.append(f"{path.stem}  {detection.shape.value} "
                               f"fit {detection.angle_confidence:.3f}")

        truth = ground_truth(split / "labels" / f"{path.stem}.txt", names)
        exact += truth == found
        for name in set(truth) | set(found):
            expected, actual = truth.get(name, 0), found.get(name, 0)
            matched += min(expected, actual)
            missed += max(0, expected - actual)
            spurious += max(0, actual - expected)

    total = matched + missed
    print(f"\nobjects   matched {matched}   missed {missed}   spurious {spurious}"
          f"   of {total} labelled")
    print(f"recall {matched / total:.3f}   "
          f"precision {matched / max(1, matched + spurious):.3f}")
    print(f"whole photo exactly right: {exact}/{len(images)}")

    print(f"\ncolour: {dict(colours)}")
    if colours.get("UNKNOWN"):
        print(f"  {colours['UNKNOWN']} object(s) unnamed - check the colour thresholds")

    print(f"\nshape fit, a guess below {guess_below}:")
    for shape in sorted(confidence):
        values = confidence[shape]
        if not values:
            continue
        below = sum(1 for v in values if v < guess_below)
        note = "  (no orientation to measure)" if shape == "CIRCLE" else \
               f"  guessed: {below}"
        print(f"  {shape:7s} n={len(values):3d}  median {statistics.median(values):.3f}"
              f"{note}")

    if guessed:
        print(f"\n{len(guessed)} angle(s) came from a consensus rather than a "
              f"clean fit - still placed turned, just less precisely:")
        for line in guessed[:12]:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
