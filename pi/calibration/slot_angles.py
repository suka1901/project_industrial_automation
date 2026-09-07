"""Measures the angle each shape must arrive at in its slot.

Point the camera so the jig is in frame, seat each object in its own slot, and
draw a box round that slot. The angle is read where the object already lies.

The older way - lift the object straight out of the slot without turning it,
set it on the picking sheet, measure there - put a hand movement between the
slot and the number. Any twist during the lift became a permanent error in a
value every placement depends on.

Keys: R box the slot, 1-5 pick the shape, SPACE record, S save, Q quit.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from domain.enums import Shape  # noqa: E402
from domain.models import BoundingBox, Detection  # noqa: E402
from domain.enums import Colour  # noqa: E402

SELECTABLE: List[Shape] = list(Shape)
HISTORY = 40           # frames of history behind the stability readout
STABLE_DEG = 0.5       # spread below which a reading is worth recording


def build_source(kind: str, path: Optional[str]):
    if kind == "basler":
        from adapters.camera.camera import Camera
        return Camera()
    from adapters.camera.file_source import FileFrameSource
    return FileFrameSource(directory=path or str(BASE_DIR / ".." / "model" / "dataset"))


def largest_object_box(image, region: Optional[Tuple[int, int, int, int]] = None
                       ) -> Optional[BoundingBox]:
    """Bounding box of the biggest thing in view, ignoring specks.

    `region` restricts the search to one slot. Without it the jig plate itself,
    or an object still lying on the sheet, is often the biggest thing in frame.
    """
    import cv2

    offset_x = offset_y = 0
    if region is not None:
        x, y, w, h = region
        image = image[y:y + h, x:x + w]
        offset_x, offset_y = x, y
        if image.size == 0:
            return None

    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    grey = cv2.GaussianBlur(grey, (5, 5), 0)
    _, mask = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        mask = cv2.bitwise_not(mask)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < 500:
        return None

    # A "contour" covering nearly the whole search area means there was no
    # object to separate from the background - an empty slot, or a region
    # drawn entirely on the plate. Reporting a box here would let an angle be
    # recorded from nothing at all.
    searched = float(image.shape[0] * image.shape[1])
    if area > 0.9 * searched:
        return None

    x, y, w, h = cv2.boundingRect(largest)
    x += offset_x
    y += offset_y
    return BoundingBox(float(x), float(y), float(x + w), float(y + h))


def main() -> int:
    import cv2

    parser = argparse.ArgumentParser(description="Measure the jig's slot angles")
    parser.add_argument("--camera", default="basler", choices=("basler", "file"))
    parser.add_argument("--path", default=None)
    parser.add_argument("--out", default=str(BASE_DIR / "calibration" / "slot_angles.yaml"))
    args = parser.parse_args()

    from adapters.detection.orientation_estimator import HarmonicOrientationEstimator
    estimator = HarmonicOrientationEstimator()

    recorded: Dict[Shape, float] = {}
    history: Deque[float] = deque(maxlen=HISTORY)
    selected = SELECTABLE[0]
    # One region per shape: each slot sits somewhere different on the jig.
    regions: Dict[Shape, Tuple[int, int, int, int]] = {}

    source = build_source(args.camera, args.path)
    source.open()
    print(__doc__)

    try:
        while True:
            frame = source.read()
            if frame is None or frame.image is None:
                continue

            canvas = frame.image.copy()
            region = regions.get(selected)
            box = largest_object_box(frame.image, region)

            if region is not None:
                x, y, w, h = region
                cv2.rectangle(canvas, (x, y), (x + w, y + h), (255, 180, 0), 2)

            angle: Optional[float] = None
            if box is not None:
                detection = Detection(
                    shape=selected, colour=Colour.UNKNOWN, confidence=1.0,
                    centre=box.centre, angle_deg=0.0, box=box,
                )
                angle = estimator.measure(frame, detection).angle_deg
                history.append(angle)

                cv2.rectangle(canvas,
                              (int(box.u_min), int(box.v_min)),
                              (int(box.u_max), int(box.v_max)), (0, 200, 0), 2)
            else:
                history.clear()

            spread = statistics.pstdev(history) if len(history) > 8 else 99.0
            steady = spread < STABLE_DEG

            period = selected.symmetry_period_deg
            lines = [
                f"shape: {selected.value}   period {period:.0f} deg"
                if period else f"shape: {selected.value}   no orientation",
                (f"angle: {angle:+7.2f} deg   spread {spread:.2f}"
                 if angle is not None else "angle: no object in view"),
                "STEADY - press SPACE to record" if steady else "settling...",
                ("slot boxed" if region is not None
                 else "press R and drag a box round this slot"),
            ]
            for index, line in enumerate(lines):
                cv2.putText(canvas, line, (12, 32 + index * 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (0, 200, 0) if steady else (0, 165, 255), 2)

            for index, shape in enumerate(SELECTABLE):
                mark = "*" if shape in recorded else " "
                value = f"{recorded[shape]:+.2f}" if shape in recorded else "--"
                cv2.putText(canvas, f"{index + 1} {mark}{shape.value:<9}{value}",
                            (12, 140 + index * 26), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (220, 220, 220), 1)

            cv2.imshow("slot angles - R box slot, 1-5 shape, SPACE record, S save, Q quit",
                       canvas)
            key = cv2.waitKey(20) & 0xFF

            if key == ord("q"):
                break
            if ord("1") <= key <= ord("5"):
                selected = SELECTABLE[key - ord("1")]
                history.clear()
            if key in (ord("r"), ord("R")):
                chosen = cv2.selectROI(
                    "drag a box round this slot, then ENTER", frame.image,
                    showCrosshair=False)
                cv2.destroyWindow("drag a box round this slot, then ENTER")
                # A zero-width selection means the operator pressed ESC.
                regions[selected] = tuple(int(v) for v in chosen) if chosen[2] and chosen[3] else None
                if regions[selected] is None:
                    regions.pop(selected, None)
                history.clear()
            if key == ord(" ") and angle is not None:
                if not steady:
                    print("Not steady yet - wait for the reading to settle.")
                elif selected.is_rotationally_free:
                    recorded[selected] = 0.0
                    print(f"{selected.value}: a circle needs no angle, recorded 0.0")
                else:
                    recorded[selected] = statistics.median(history)
                    print(f"{selected.value}: {recorded[selected]:+.2f} deg")
            if key == ord("s"):
                write_yaml(Path(args.out), recorded)
    finally:
        source.close()
        cv2.destroyAllWindows()

    write_yaml(Path(args.out), recorded)
    return 0


def write_yaml(path: Path, recorded: Dict[Shape, float]) -> None:
    """Write the block to paste into config.yaml."""
    if not recorded:
        print("Nothing recorded.")
        return

    lines = ["# Measured with calibration/slot_angles.py.",
             "# Re-measure whenever the jig moves.",
             "place_slot_angles_deg:"]
    lines += [f"  {shape.value}: {value:.2f}" for shape, value in recorded.items()]
    text = "\n".join(lines) + "\n"

    path.write_text(text, encoding="utf-8")
    print(f"\nSaved to {path}\n\n{text}")


if __name__ == "__main__":
    raise SystemExit(main())
