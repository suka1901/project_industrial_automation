"""Check the labels, then split them into a YOLO train/val tree.

Runs after Label Studio has exported. Validation comes first: a malformed
label file trains a model that fails silently, and that is expensive to
diagnose later than it is to catch here.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import logging
from itertools import combinations
import random
import shutil
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import yaml  # noqa: E402

from infrastructure.config_loader import load_config  # noqa: E402
from infrastructure.logging_setup import configure_logging  # noqa: E402
log = logging.getLogger("split_dataset")

# build_label_set.py writes JPEG; raw camera frames are PNG. Accept either, so
# a label set built by hand from the raw folders still works.
IMAGE_SUFFIXES = (".jpg", ".png")

VALIDATION_FRACTION = 0.2
SPLIT_SEED = 1              # fixed, so a re-run reproduces the same split
BRIGHTNESS_BANDS = 3        # val must span the lighting conditions, not one
DUPLICATE_IOU = 0.80        # above this, one object has been boxed twice


@dataclass(frozen=True)
class Sample:
    """One image and the label file that belongs with it."""

    image: Path
    label: Path
    class_ids: Tuple[int, ...]
    brightness: float

    @property
    def is_negative(self) -> bool:
        return not self.class_ids


@lru_cache(maxsize=None)
def sheet_brightness(path: Path) -> float:
    """95th percentile grey, read at quarter size."""
    import cv2
    import numpy as np

    image = cv2.imread(str(path), cv2.IMREAD_REDUCED_GRAYSCALE_4)
    if image is None:
        return 0.0
    return float(np.percentile(image, 95))


def parse_label(path: Path, class_count: int) -> Tuple[Tuple[int, ...], List[str]]:
    """Return the class ids in this file, plus a problem for every bad row."""
    if not path.is_file():
        return (), [f"{path.name}: missing"]

    class_ids: List[int] = []
    problems: List[str] = []
    boxes: List[List[float]] = []

    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        row = raw.split()
        if not row:
            continue
        if len(row) != 5:
            problems.append(f"{path.name}:{number}: {len(row)} fields, expected 5")
            continue
        try:
            class_id = int(row[0])
            values = [float(v) for v in row[1:]]
        except ValueError:
            problems.append(f"{path.name}:{number}: not numeric")
            continue
        if not 0 <= class_id < class_count:
            problems.append(f"{path.name}:{number}: class {class_id} out of range")
            continue
        if any(not 0.0 <= v <= 1.0 for v in values):
            problems.append(f"{path.name}:{number}: coordinates not normalised")
            continue
        if values[2] <= 0.0 or values[3] <= 0.0:
            problems.append(f"{path.name}:{number}: zero-sized box")
            continue
        class_ids.append(class_id)
        boxes.append(values)

    problems.extend(duplicate_boxes(path.name, boxes))
    return tuple(class_ids), problems


def collect(images_dir: Path, labels_dir: Path,
            class_count: int) -> Tuple[List[Sample], List[str]]:
    """Pair every image with its label file and validate as we go."""
    samples: List[Sample] = []
    problems: List[str] = []

    for image in sorted(p for p in images_dir.iterdir()
                        if p.suffix.lower() in IMAGE_SUFFIXES):
        label = labels_dir / f"{image.stem}.txt"
        class_ids, issues = parse_label(label, class_count)
        problems.extend(issues)
        if issues and not label.is_file():
            continue
        samples.append(Sample(image, label, class_ids, sheet_brightness(image)))

    orphans = {p.stem for p in labels_dir.glob("*.txt")} - {s.image.stem for s in samples}
    problems.extend(f"{stem}.txt: no matching image" for stem in sorted(orphans))
    return samples, problems


def _iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Intersection over union of two YOLO boxes (cx, cy, w, h)."""
    corners = [(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2) for cx, cy, w, h in (a, b)]
    (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) = corners
    overlap = (max(0.0, min(ax1, bx1) - max(ax0, bx0))
               * max(0.0, min(ay1, by1) - max(ay0, by0)))
    union = a[2] * a[3] + b[2] * b[3] - overlap
    return overlap / union if union > 0 else 0.0


def duplicate_boxes(name: str, boxes: Sequence[Sequence[float]]) -> List[str]:
    """Pairs overlapping so heavily they must be one object boxed twice.

    A double-drag in the labelling tool leaves two boxes on one object. YOLO
    then trains on it as though it were two, and nothing downstream complains.
    """
    return [f"{name}: boxes {i + 1} and {j + 1} overlap at IoU {_iou(boxes[i], boxes[j]):.2f}"
            for i, j in combinations(range(len(boxes)), 2)
            if _iou(boxes[i], boxes[j]) > DUPLICATE_IOU]


def check_exported_class_order(label_dir: Path, names: Sequence[str]) -> List[str]:
    """Compare the exporter's class order with config.

    Label Studio numbers classes by their order in the labelling config. If that
    order differs from detector.class_map, training succeeds and every shape
    comes out mislabelled at run time - the worst kind of failure, because
    nothing crashes.
    """
    path = label_dir / "classes.txt"
    if not path.is_file():
        return [f"{path} not found - check the class order by hand"]

    exported = [line.strip().lower()
                for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if exported == list(names):
        return []
    return [f"class order mismatch: classes.txt has {exported}, "
            f"config.yaml expects {list(names)}"]


def stratum_of(sample: Sample, edges: Sequence[float]) -> Tuple[int, ...]:
    """Group key: which classes are present, and which lighting band.

    Splitting inside these groups keeps both the class balance and the
    lighting spread of the whole set in train and val alike.
    """
    band = sum(1 for edge in edges if sample.brightness > edge)
    return tuple(sorted(set(sample.class_ids))) + (-1, band)


def split(samples: Sequence[Sample], fraction: float,
          seed: int) -> Tuple[List[Sample], List[Sample]]:
    """Stratified split, deterministic for a given seed."""
    import numpy as np

    brightness = [s.brightness for s in samples]
    edges = [float(np.percentile(brightness, 100.0 * i / BRIGHTNESS_BANDS))
             for i in range(1, BRIGHTNESS_BANDS)]

    groups: Dict[Tuple[int, ...], List[Sample]] = {}
    for sample in samples:
        groups.setdefault(stratum_of(sample, edges), []).append(sample)

    rng = random.Random(seed)
    train: List[Sample] = []
    validation: List[Sample] = []
    for key in sorted(groups, key=str):
        members = sorted(groups[key], key=lambda s: s.image.name)
        rng.shuffle(members)
        # At least one goes to val whenever the group has more than one member,
        # so no class or lighting band is missing from validation entirely.
        wanted = max(1, round(len(members) * fraction)) if len(members) > 1 else 0
        validation.extend(members[:wanted])
        train.extend(members[wanted:])
    return train, validation


def write_split(samples: Sequence[Sample], root: Path, name: str) -> None:
    images = root / name / "images"
    labels = root / name / "labels"
    for folder in (images, labels):
        folder.mkdir(parents=True, exist_ok=True)
    for sample in samples:
        shutil.copy2(sample.image, images / sample.image.name)
        shutil.copy2(sample.label, labels / sample.label.name)


def write_data_yaml(root: Path, names: Sequence[str]) -> Path:
    """The file Ultralytics reads. Class order here IS the class_map order."""
    path = root / "data.yaml"
    path.write_text(yaml.safe_dump({
        "path": str(root),
        "train": "train/images",
        "val": "val/images",
        "names": {index: name for index, name in enumerate(names)},
    }, sort_keys=False), encoding="utf-8")
    return path


def report(title: str, samples: Sequence[Sample], names: Sequence[str]) -> None:
    counts = {name: 0 for name in names}
    for sample in samples:
        for class_id in sample.class_ids:
            counts[names[class_id]] += 1
    negatives = sum(1 for s in samples if s.is_negative)
    print(f"  {title:<6} {len(samples):4d} images, {negatives:3d} empty   "
          + "  ".join(f"{name} {count}" for name, count in counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate labels and build the YOLO split")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--label-dir", default=None, help="default model/dataset/label")
    parser.add_argument("--out", default=None, help="default model/dataset/yolo")
    parser.add_argument("--fraction", type=float, default=VALIDATION_FRACTION)
    parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    args = parser.parse_args()

    configure_logging(level="INFO", log_file=None)
    config = load_config(BASE_DIR / args.config)

    # data.yaml must agree with detector.class_map, so both come from one place.
    class_map = config.get("detector", {}).get("class_map", {})
    names = [str(class_map[index]).lower() for index in sorted(class_map)]
    if not names:
        log.error("detector.class_map is empty in %s", args.config)
        return 1

    dataset = (BASE_DIR / ".." / "model" / "dataset").resolve()
    label_dir = Path(args.label_dir) if args.label_dir else dataset / "label"
    out = Path(args.out) if args.out else dataset / "yolo"

    samples, problems = collect(label_dir / "images", label_dir / "labels", len(names))
    problems = check_exported_class_order(label_dir, names) + problems

    if problems:
        print(f"\n{len(problems)} problem(s) - fix these before training:\n")
        for line in problems[:40]:
            print(f"  {line}")
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        return 1

    if not samples:
        log.error("No images found under %s", label_dir / "images")
        return 1

    train, validation = split(samples, args.fraction, args.seed)

    if out.exists():
        shutil.rmtree(out)
    write_split(train, out, "train")
    write_split(validation, out, "val")
    data_yaml = write_data_yaml(out, names)

    print(f"\nClasses: {', '.join(f'{i}={n}' for i, n in enumerate(names))}")
    report("train", train, names)
    report("val", validation, names)
    print(f"\n{data_yaml}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
