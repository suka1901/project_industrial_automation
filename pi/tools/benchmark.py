"""Time the vision pipeline against the 3-second budget the course sets.

Run this first on the Pi, before touching the camera. It needs only saved
photos, so it answers the one question that could sink the whole demo -
is the model fast enough on this hardware - in a couple of minutes.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))


from domain.models import Frame  # noqa: E402
from infrastructure.container import Container  # noqa: E402
from infrastructure.config_loader import load_config  # noqa: E402
from infrastructure.logging_setup import configure_logging  # noqa: E402

log = logging.getLogger("benchmark")

BUDGET_MS = 3000.0          # the course limit
SAFE_FRACTION = 0.60        # leave headroom: the Pi is slower under load


def main() -> int:
    parser = argparse.ArgumentParser(description="Time the pipeline against the budget")
    parser.add_argument("--config", default="config/profiles/pi.yaml")
    parser.add_argument("--images", default=None,
                        help="default model/dataset/yolo/val/images")
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()

    configure_logging(level="ERROR", log_file=None)
    import cv2

    config = load_config(BASE_DIR / args.config)
    folder = Path(args.images) if args.images else \
        (BASE_DIR / ".." / "model" / "dataset" / "yolo" / "val" / "images").resolve()
    images = sorted(folder.glob("*.jpg"))[:args.count]
    if not images:
        log.error("No photos in %s", folder)
        return 1

    detector = config.get("detector", {})
    print(f"model      {detector.get('model_path')}")
    print(f"image size {detector.get('image_size')}")
    print(f"photos     {len(images)} from {folder.name}\n")

    pipeline = Container(config, BASE_DIR).build_vision_pipeline()

    started = time.perf_counter()
    pipeline.warm_up()
    load_s = time.perf_counter() - started
    print(f"model load and warm-up: {load_s:.1f} s "
          f"(the system is unavailable for this long at start-up)\n")

    times: List[float] = []
    for path in images:
        image = cv2.imread(str(path))
        begin = time.perf_counter()
        pipeline.process(Frame(image=image, sequence=0, captured_at=0.0))
        times.append((time.perf_counter() - begin) * 1000.0)

    median = statistics.median(times)
    worst = max(times)
    print(f"per frame   median {median:.0f} ms   worst {worst:.0f} ms   "
          f"budget {BUDGET_MS:.0f} ms")

    safe = BUDGET_MS * SAFE_FRACTION
    if worst <= safe:
        print(f"\nPASS - worst case is under {safe:.0f} ms, comfortably inside budget")
        return 0
    if worst <= BUDGET_MS:
        print(f"\nTIGHT - inside the {BUDGET_MS:.0f} ms budget but over {safe:.0f} ms. "
              "Re-export the model at a smaller image size for headroom.")
        return 0
    print(f"\nFAIL - over budget. Re-export NCNN at 480 or 416 (the size is fixed "
          "at export, so editing image_size alone will not help) and re-run this.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
