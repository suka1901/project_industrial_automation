"""Assemble the images to label, with a budget for empty hard negatives.

Photos of the assigned shapes all go forward. Photos containing only the
forbidden shapes carry no labels at all, and too many empty images make a
YOLO model timid, so only a stratified sample of them is included.

Images are written out downscaled, as JPEG. The camera's 2448 px frames are
about 6 MB each, which makes the labelling UI crawl and the set far too large
to upload for training - and none of it survives anyway, because the network
resizes to 640 px. At 1280 px an object is still around 130 px here.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import List, Sequence, Set, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from infrastructure.config_loader import load_config  # noqa: E402
from infrastructure.logging_setup import configure_logging  # noqa: E402
from tools.capture_session import IMAGE_SUFFIX, MIXED  # noqa: E402

log = logging.getLogger("build_label_set")

# Share of the label set allowed to be images with no objects in them at all.
# Ultralytics suggests roughly 10 percent; 15 leaves room without swamping it.
NEGATIVE_FRACTION = 0.15

# Photos deliberately left out, one stem per line, '#' for comments. Kept
# beside the label set so a rebuild cannot quietly reinstate them.
EXCLUDED_FILE = "excluded.txt"

OUTPUT_WIDTH = 1280      # comfortably above the 640 the network trains at
JPEG_QUALITY = 92        # visually lossless at this scale, about 40x smaller


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
    return float(np.percentile(image, 95))


def images_in(folder: Path) -> List[Path]:
    return sorted(folder.glob(f"*{IMAGE_SUFFIX}"))


def already_labelled(label_dir: Path) -> Set[str]:
    """Photos someone has annotated. These are pinned into the set.

    The negative budget scales with the number of target photos, so re-running
    with a different target count re-samples a *different* subset of negatives
    - silently orphaning labels drawn against the old one.
    """
    labels = label_dir / "labels"
    if not labels.is_dir():
        return set()
    return {path.stem for path in labels.glob("*.txt")}


def excluded_stems(label_dir: Path) -> Set[str]:
    """Photos to leave out, listed by whoever removed them."""
    path = label_dir / EXCLUDED_FILE
    if not path.is_file():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


def split_folders(raw: Path, assigned: Sequence[str]) -> Tuple[List[Path], List[Path]]:
    """Folders holding assigned shapes, and folders holding only forbidden ones."""
    targets, negatives = [], []
    for folder in sorted(p for p in raw.iterdir() if p.is_dir()):
        bucket = targets if folder.name in assigned or folder.name == MIXED else negatives
        bucket.append(folder)
    return targets, negatives


def sample_evenly(paths: Sequence[Path], wanted: int) -> List[Path]:
    """Take `wanted` images spread across the brightness range, not the first N.

    Brightness moves in blocks between shooting sessions, so ordering by it and
    stepping through picks up every lighting condition present.
    """
    if wanted <= 0:
        return []
    if wanted >= len(paths):
        return list(paths)
    ordered = sorted(paths, key=sheet_brightness)
    step = len(ordered) / float(wanted)
    return [ordered[int(index * step)] for index in range(wanted)]


def negative_budget(target_count: int) -> int:
    """How many empty images the set can carry at NEGATIVE_FRACTION."""
    return int(round(target_count * NEGATIVE_FRACTION / (1.0 - NEGATIVE_FRACTION)))


def output_name(source: Path) -> str:
    return f"{source.stem}.jpg"


def write_all(chosen: Sequence[Tuple[Path, bool]], destination: Path,
              width: int) -> None:
    """Downscale each image into the label folder, keeping the aspect ratio."""
    import cv2

    destination.mkdir(parents=True, exist_ok=True)
    for source, _ in chosen:
        image = cv2.imread(str(source))
        if image is None:
            log.warning("Could not read %s", source)
            continue
        height = int(round(image.shape[0] * width / image.shape[1]))
        resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(destination / output_name(source)), resized,
                    [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])


def write_manifest(chosen: Sequence[Tuple[Path, bool]], path: Path) -> None:
    """Record where every image came from, so a labelling mistake is traceable."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["image", "source_folder", "expect_labels", "sheet_brightness"])
        for source, expect_labels in sorted(chosen, key=lambda item: item[0].name):
            writer.writerow([output_name(source), source.parent.name,
                             "yes" if expect_labels else "no",
                             f"{sheet_brightness(source):.0f}"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect images for labelling, with a hard-negative budget")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--raw", default=None, help="default model/dataset/raw")
    parser.add_argument("--out", default=None, help="default model/dataset/label/images")
    parser.add_argument("--width", type=int, default=OUTPUT_WIDTH,
                        help="output width in pixels")
    parser.add_argument("--rebuild", action="store_true",
                        help="replace an existing label set that already has labels")
    args = parser.parse_args()

    configure_logging(level="INFO", log_file=None)
    config = load_config(BASE_DIR / args.config)
    assigned = [name.lower() for name in config.get("shapes", [])]
    if not assigned:
        log.error("No shapes in %s - nothing to label", args.config)
        return 1

    raw = Path(args.raw) if args.raw else (BASE_DIR / ".." / "model" / "dataset" / "raw")
    raw = raw.resolve()
    out = Path(args.out) if args.out else (raw.parent / "label" / "images")

    # Refuse to silently discard labelling work. The output folder is rebuilt
    # from scratch, so a stray run would otherwise undo hand edits.
    labels = out.parent / "labels"
    if out.is_dir() and labels.is_dir() and any(labels.glob("*.txt")) and not args.rebuild:
        log.error("%s already has %d label file(s). Rebuilding replaces every "
                  "image. Pass --rebuild if that is really what you want.",
                  labels, len(list(labels.glob("*.txt"))))
        return 1

    skip = excluded_stems(out.parent)
    target_folders, negative_folders = split_folders(raw, assigned)
    targets = [p for folder in target_folders
               for p in images_in(folder) if p.stem not in skip]
    negatives = [p for folder in negative_folders
                 for p in images_in(folder) if p.stem not in skip]
    if skip:
        print(f"excluding {len(skip)} photo(s) listed in {EXCLUDED_FILE}")

    if not targets:
        log.error("No images for %s under %s", assigned, raw)
        return 1

    # Anything already annotated stays in, whatever the budget says.
    pinned = already_labelled(out.parent)
    must_keep = [p for p in negatives if p.stem in pinned]
    candidates = [p for p in negatives if p.stem not in pinned]

    budget = negative_budget(len(targets))
    kept_negatives = must_keep + sample_evenly(
        candidates, max(0, budget - len(must_keep)))
    if must_keep:
        print(f"keeping {len(must_keep)} already-labelled negative(s)")

    chosen: List[Tuple[Path, bool]] = [(p, True) for p in targets]
    chosen += [(p, False) for p in kept_negatives]

    # Regenerate from scratch: a leftover image from an earlier run is one the
    # labeller will annotate and split_dataset.py will then fail to explain.
    if out.is_dir():
        shutil.rmtree(out)
    write_all(chosen, out, args.width)
    write_manifest(chosen, out.parent / "manifest.csv")

    print(f"\nLabel set at {out}")
    print(f"  with objects   {len(targets):4d}  "
          f"({', '.join(f.name for f in target_folders)})")
    print(f"  empty negatives{len(kept_negatives):4d}  of {len(negatives)} available "
          f"({', '.join(f.name for f in negative_folders)})")
    print(f"  total          {len(chosen):4d}   at {args.width} px, JPEG")
    print(f"\nManifest: {out.parent / 'manifest.csv'}")
    print(f"Held back: {len(negatives) - len(kept_negatives)} negatives, "
          "for a second round if the model over-fires")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
