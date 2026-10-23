"""Aim the lamp by numbers instead of by eye.

A white object on white paper is the hardest thing this cell has to measure,
and whether it CAN be measured is decided before any code runs. Measured over
the labelled photos, grouped by how bright the A3 sheet reads:

    sheet 95th percentile    white square        coloured square
    under 100                13 grey levels      56 grey levels
    100 to 150               22                 100
    150 and up               34                  77

A coloured square is measurable in any light you own. A white one lives or
dies on the lamp, and the number that says which is the CONTRAST - the grey
levels between the object and the paper it lies on. This prints it live, for
every object on the table, so the lamp can be moved until the number is
right rather than until the picture looks nice.

Two things matter and only one is obvious:

    more light     raises every contrast roughly in proportion
    light from the SIDE  gives the object's edge a shadow to cast

The second is what rescues a white square. Its face reflects almost exactly
what the paper reflects, so no amount of light separates them by level - but
its edge still steps, and a raking light deepens that step. The gradient
route reads the step; the brightness route cannot.

    python3 tools/light_meter.py                      the camera
    python3 tools/light_meter.py --camera tap         while main.py runs
    python3 tools/light_meter.py --once               one reading, then quit

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from adapters.detection.segmentation import contrast_levels      # noqa: E402
from infrastructure.config_loader import load_config             # noqa: E402
from infrastructure.container import Container                   # noqa: E402
# The sheet's target band lives in preflight, which is the other tool that
# judges it. One definition, so the two can never disagree about what good
# light is.
from tools.preflight import (SATURATED_MAX_PCT, SHEET_BRIGHT_MAX,  # noqa: E402
                             SHEET_BRIGHT_MIN)

# Contrast, in grey levels, between an object and its paper. Measured on the
# labelled photos: below 20 no segmentation found the outline at all, and
# every reading above 40 was acted on. Between them it depends on the object.
CONTRAST_POOR = 20.0
CONTRAST_GOOD = 40.0

# The fit the orientation estimator must reach for its angle to be used as
# measured rather than guessed at. Mirrors orientation.min_fit.
DEFAULT_MIN_FIT = 0.60

PADDING_PX = 4


def build_source(kind: str, path: Optional[str]):
    """The camera, the frame main.py drops for other tools, or a folder."""
    if kind == "basler":
        from adapters.camera.camera import Camera
        return Camera()
    if kind == "tap":
        from adapters.camera.tap_source import TapFrameSource
        return TapFrameSource(path or "/tmp/ina700_frame.jpg")
    from adapters.camera.file_source import FileFrameSource
    return FileFrameSource(directory=path or str(BASE_DIR / ".." / "model" / "dataset"))


def sheet_brightness(image: Any) -> tuple:
    """How bright the paper is, and how much of the frame has clipped."""
    import cv2
    import numpy as np

    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return (float(np.percentile(grey, 95)),
            float((grey >= 255).mean()) * 100.0)


def sheet_verdict(sheet: float, clipped: float) -> str:
    """One word for the lamp, and what to do about it."""
    if clipped > SATURATED_MAX_PCT:
        return "CLIPPING - lower the exposure or diffuse the lamp"
    if sheet < SHEET_BRIGHT_MIN:
        wanted = (SHEET_BRIGHT_MIN + SHEET_BRIGHT_MAX) / 2.0
        return f"TOO DARK - needs {wanted / max(sheet, 1.0):.1f}x more light"
    if sheet > SHEET_BRIGHT_MAX:
        return "TOO BRIGHT - close to clipping"
    return "good"


def contrast_verdict(contrast: float) -> str:
    if contrast < CONTRAST_POOR:
        return "no edge to find"
    if contrast < CONTRAST_GOOD:
        return "marginal"
    return "good"


def crop_of(image: Any, box) -> Optional[Any]:
    """The pixels the orientation estimator works on, padding included."""
    if box is None:
        return None
    height, width = image.shape[:2]
    left = max(0, int(box.u_min) - PADDING_PX)
    top = max(0, int(box.v_min) - PADDING_PX)
    right = min(width, int(box.u_max) + PADDING_PX)
    bottom = min(height, int(box.v_max) + PADDING_PX)
    if right - left < 8 or bottom - top < 8:
        return None
    return image[top:bottom, left:right]


def report(frame, pipeline, min_fit: float) -> None:
    """One screen: the paper first, then every object on it."""
    sheet, clipped = sheet_brightness(frame.image)
    print("\033[H\033[J", end="")          # home, then clear - no scrolling

    # Before the block rather than inside it: the pipeline prints the
    # inference time of its own accord, and the course asks for that line
    # every cycle. It belongs at the top, not through the middle of a table.
    result = pipeline.process(frame)

    print(f"\n  sheet {sheet:3.0f}/255   clipped {clipped:5.2f}%   "
          f"{sheet_verdict(sheet, clipped)}")
    print(f"  (want {SHEET_BRIGHT_MIN:.0f} to {SHEET_BRIGHT_MAX:.0f}; "
          f"aim near the top of that for a white object)\n")

    if not result.detections:
        print("  nothing on the table")
        return

    print(f"  {'shape':8} {'colour':7} {'seen':>5} {'contrast':>9} {'fit':>5}   what the angle costs")
    for detection in result.detections:
        crop = crop_of(frame.image, detection.box)
        contrast = contrast_levels(crop) if crop is not None else 0.0
        if detection.shape.is_rotationally_free:
            verdict = "a circle needs no angle"
        elif detection.angle_confidence >= min_fit:
            verdict = "measured"
        else:
            verdict = f"GUESSED - {contrast_verdict(contrast)}"
        print(f"  {detection.shape.value:8} {detection.colour.value:7} "
              f"{detection.confidence:5.2f} {contrast:9.0f} "
              f"{detection.angle_confidence:5.2f}   {verdict}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Live lighting meter")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--camera", default="basler", choices=("basler", "tap", "file"))
    parser.add_argument("--path", default=None, help="folder or tap file")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="seconds between readings")
    parser.add_argument("--once", action="store_true", help="one reading, then quit")
    args = parser.parse_args()

    # The screen IS the output; log lines landing in the middle of it would
    # make the numbers unreadable just as the lamp is being moved.
    logging.basicConfig(level=logging.ERROR)

    config = load_config(BASE_DIR / args.config)
    container = Container(config, BASE_DIR)
    pipeline = container.build_vision_pipeline()
    min_fit = float(config.get("orientation", {}).get("min_fit", DEFAULT_MIN_FIT))

    source = build_source(args.camera, args.path)
    source.open()
    pipeline.warm_up()
    try:
        while True:
            frame = source.read()
            if frame is not None and frame.image is not None:
                report(frame, pipeline, min_fit)
                if args.once:
                    return 0
            time.sleep(max(0.0, args.interval))
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        source.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
