"""Pre-annotate the unlabelled photos with a partly-trained model.

Round one is labelled by hand; a model trained on it proposes boxes for the
rest, and correcting a proposal is far quicker than drawing from nothing.
Output is a JSON file to import into Label Studio as predictions - never as
annotations, so a wrong proposal can never masquerade as your own work.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from infrastructure.config_loader import load_config  # noqa: E402
from infrastructure.logging_setup import configure_logging  # noqa: E402

log = logging.getLogger("prelabel")

# Lower than the run-time threshold on purpose: a spare box is one keypress to
# delete, while a missed object has to be drawn from scratch.
DEFAULT_CONFIDENCE = 0.25


def labelled_stems(labels_dir: Path) -> set:
    """Stems already annotated - these must not be overwritten with guesses."""
    if not labels_dir.is_dir():
        return set()
    return {path.stem for path in labels_dir.glob("*.txt")}


def predict(model_path: str, images: List[Path], names: List[str],
            image_size: int, confidence: float) -> List[Dict[str, Any]]:
    """Run the model and shape each result the way Label Studio expects."""
    from ultralytics import YOLO  # pyright: ignore[reportMissingImports]

    model = YOLO(model_path, task="detect")
    out: List[Dict[str, Any]] = []

    for path in images:
        result = model.predict(str(path), imgsz=image_size, conf=confidence,
                               verbose=False)[0]
        height, width = result.orig_shape
        regions = []
        for box in (result.boxes or []):
            u0, v0, u1, v1 = (float(v) for v in box.xyxy[0].tolist())
            regions.append({
                "from_name": "label",
                "to_name": "image",
                "type": "rectanglelabels",
                "original_width": width,
                "original_height": height,
                "image_rotation": 0,
                # Label Studio takes percentages of the image, top-left origin.
                "value": {
                    "x": 100.0 * u0 / width,
                    "y": 100.0 * v0 / height,
                    "width": 100.0 * (u1 - u0) / width,
                    "height": 100.0 * (v1 - v0) / height,
                    "rotation": 0,
                    "rectanglelabels": [names[int(box.cls.item())]],
                },
                "score": float(box.conf.item()),
            })
        out.append({"image": path.name, "result": regions,
                    "score": min((r["score"] for r in regions), default=0.0)})
        log.info("%s: %d proposal(s)", path.name, len(regions))

    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Propose boxes for the photos that are not labelled yet")
    parser.add_argument("--model", default="../model/best.pt")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--label-dir", default=None, help="default model/dataset/label")
    parser.add_argument("--out", default=None, help="default <label-dir>/predictions.json")
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    parser.add_argument("--all", action="store_true",
                        help="include photos that are already labelled")
    args = parser.parse_args()

    configure_logging(level="INFO", log_file=None)
    config = load_config(BASE_DIR / args.config)
    detector = config.get("detector", {})
    class_map = detector.get("class_map", {})
    names = [str(class_map[index]).lower() for index in sorted(class_map)]

    label_dir = Path(args.label_dir) if args.label_dir else \
        (BASE_DIR / ".." / "model" / "dataset" / "label").resolve()
    images = sorted((label_dir / "images").glob("*.jpg"))
    if not args.all:
        done = labelled_stems(label_dir / "labels")
        images = [p for p in images if p.stem not in done]

    if not images:
        log.error("Nothing to do - every photo under %s is already labelled", label_dir)
        return 1

    predictions = predict(args.model, images, names,
                          int(detector.get("image_size", 640)), args.confidence)

    out = Path(args.out) if args.out else label_dir / "predictions.json"
    out.write_text(json.dumps(predictions, indent=1), encoding="utf-8")

    total = sum(len(p["result"]) for p in predictions)
    empty = sum(1 for p in predictions if not p["result"])
    print(f"\n{len(predictions)} photo(s), {total} proposed box(es)")
    print(f"  nothing proposed on {empty} - check those by hand")
    print(f"\n{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
