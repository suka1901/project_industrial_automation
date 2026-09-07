"""Turn Label Studio's exported annotations into YOLO label files.

Label Studio's local target storage drops one JSON per annotation on disk.
This reads that folder and writes the .txt files split_dataset.py expects, so
the export never has to travel through a download folder by hand.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Set
from urllib.parse import unquote

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import yaml  # noqa: E402

from infrastructure.logging_setup import configure_logging  # noqa: E402

log = logging.getLogger("labels_from_export")


def stem_of(image_value: str) -> str:
    """Filename stem from Label Studio's image value.

    The value is a URL whose query carries a WINDOWS path (images\\name.jpg).
    Splitting on os.sep alone loses the backslash on Linux, so split on both.
    """
    return Path(re.split(r"[\\/]", unquote(image_value))[-1]).stem


def convert(export_dir: Path, images_dir: Path, labels_dir: Path,
            class_index: Dict[str, int]) -> None:
    """Write one .txt per image, and report anything that does not line up."""
    labels_dir.mkdir(parents=True, exist_ok=True)
    for stale in labels_dir.iterdir():
        if stale.is_file():
            stale.unlink()

    images: Set[str] = {p.stem for p in images_dir.glob("*.jpg")}
    counts: collections.Counter = collections.Counter()
    written = boxes = empty = 0
    orphans: List[str] = []
    seen: Set[str] = set()

    for path in sorted(export_dir.iterdir()):
        if path.is_dir():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        stem = stem_of(data["task"]["data"]["image"])

        if stem not in images:
            # The task was deleted after this file was written.
            orphans.append(stem)
            continue
        if stem in seen:
            log.warning("%s has more than one annotation file; keeping the first", stem)
            continue
        seen.add(stem)

        rows = []
        for region in data.get("result", []):
            if region.get("type") != "rectanglelabels":
                continue
            value = region["value"]
            name = value["rectanglelabels"][0]
            counts[name] += 1
            rows.append(
                f"{class_index[name]} "
                f"{(value['x'] + value['width'] / 2) / 100:.6f} "
                f"{(value['y'] + value['height'] / 2) / 100:.6f} "
                f"{value['width'] / 100:.6f} {value['height'] / 100:.6f}")

        (labels_dir / f"{stem}.txt").write_text("\n".join(rows), encoding="utf-8")
        written += 1
        boxes += len(rows)
        empty += not rows

    print(f"\n{written} label file(s), {boxes} box(es), {empty} empty hard negative(s)")
    print("  " + "  ".join(f"{name} {counts[name]}" for name in class_index))
    if orphans:
        print(f"  skipped {len(orphans)} export(s) whose image is gone: "
              f"{', '.join(sorted(orphans))}")
    unlabelled = sorted(images - seen)
    if unlabelled:
        print(f"  NO LABEL for {len(unlabelled)}: {', '.join(unlabelled[:10])}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build YOLO labels from Label Studio's exported annotations")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--label-dir", default=None, help="default model/dataset/label")
    args = parser.parse_args()

    configure_logging(level="INFO", log_file=None)
    config = yaml.safe_load((BASE_DIR / args.config).read_text(encoding="utf-8"))
    class_map = config.get("detector", {}).get("class_map", {})
    class_index = {str(class_map[i]).lower(): i for i in sorted(class_map)}

    label_dir = Path(args.label_dir) if args.label_dir else \
        (BASE_DIR / ".." / "model" / "dataset" / "label").resolve()
    export_dir = label_dir / "annotations"
    if not export_dir.is_dir():
        log.error("No export folder at %s - add a local Target Storage in "
                  "Label Studio pointing there, then Sync", export_dir)
        return 1

    convert(export_dir, label_dir / "images", label_dir / "labels", class_index)
    (label_dir / "classes.txt").write_text(
        "\n".join(class_index) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
