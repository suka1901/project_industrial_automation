"""Measures the angle each shape must arrive at in its slot.

Point the camera so the jig is in frame, seat each object in its own slot, and
draw a box round that slot. The angle is read where the object already lies.

The older way - lift the object straight out of the slot without turning it,
set it on the picking sheet, measure there - put a hand movement between the
slot and the number. Any twist during the lift became a permanent error in a
value every placement depends on.

Record each shape SEVERAL times: seat it, press SPACE, lift it out, seat it
again, press SPACE again. A shape-matched slot still has play in it, and the
spread across seatings is the only honest measure of how much. One reading
cannot tell you whether it is repeatable to a tenth of a degree or to five.

SPACE is refused until the slot has been seen EMPTY since the last seating.
Recording without lifting the object out just copies one reading, and the
play then comes out near zero - which looks like a perfect slot and means
nothing at all.

Keys: R box the slot, 1-5 pick the shape, SPACE record a seating,
      C clear this shape, S save, Q quit.

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
from domain.angles import (circular_mean_deg,  # noqa: E402
                           circular_spread_deg)
from calibration.view import (display_scale, shrink,  # noqa: E402
                              to_full_resolution)

SELECTABLE: List[Shape] = list(Shape)
HISTORY = 40           # frames of history behind the stability readout
STABLE_DEG = 0.5       # frame-to-frame spread below which a seating counts
# Play across seatings beyond this share of the symmetry period means the slot
# is not holding the shape as tightly as a single reading would suggest.
LOOSE_SHARE = 0.10


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
    parser.add_argument("--display-width", type=int, default=1100,
                        help="preview width in pixels; the measurement stays full size")
    args = parser.parse_args()

    from adapters.detection.orientation_estimator import HarmonicOrientationEstimator
    estimator = HarmonicOrientationEstimator()

    # Every seating of each shape, not one value per shape: the spread across
    # them is what says whether a single stored angle can be trusted.
    seatings: Dict[Shape, List[float]] = {}
    history: Deque[float] = deque(maxlen=HISTORY)
    # A seating only counts once the slot has been seen empty since the last
    # one. Without this the same seating can be recorded over and over: the
    # reading re-settles to the identical value and the play comes out near
    # zero, which looks like a superbly repeatable slot and is really just one
    # measurement copied thirty times.
    armed = True
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

            # Everything below measures frame.image at full resolution; the
            # canvas is only what the operator looks at.
            scale = display_scale(frame.image, args.display_width)
            canvas = shrink(frame.image, scale)

            region = regions.get(selected)
            box = largest_object_box(frame.image, region)

            if region is not None:
                x, y, w, h = region
                cv2.rectangle(canvas,
                              (int(x * scale), int(y * scale)),
                              (int((x + w) * scale), int((y + h) * scale)),
                              (255, 180, 0), 2)

            angle: Optional[float] = None
            if box is not None:
                detection = Detection(
                    shape=selected, colour=Colour.UNKNOWN, confidence=1.0,
                    centre=box.centre, angle_deg=0.0, box=box,
                )
                angle = estimator.measure(frame, detection).angle_deg
                history.append(angle)

                cv2.rectangle(canvas,
                              (int(box.u_min * scale), int(box.v_min * scale)),
                              (int(box.u_max * scale), int(box.v_max * scale)),
                              (0, 200, 0), 2)
            else:
                history.clear()
                # Slot empty: the object is out, so the next one is genuinely new.
                armed = True

            spread = statistics.pstdev(history) if len(history) > 8 else 99.0
            steady = spread < STABLE_DEG

            period = selected.symmetry_period_deg
            lines = [
                f"shape: {selected.value}   period {period:.0f} deg"
                if period else f"shape: {selected.value}   no orientation",
                (f"angle: {angle:+7.2f} deg   spread {spread:.2f}"
                 if angle is not None else "angle: no object in view"),
                ("STEADY - press SPACE to record" if steady else "settling...")
                if armed else "LIFT THE OBJECT OUT, then seat it again",
                ("slot boxed" if region is not None
                 else "press R and drag a box round this slot"),
            ]
            for index, line in enumerate(lines):
                cv2.putText(canvas, line, (12, 32 + index * 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (0, 200, 0) if steady else (0, 165, 255), 2)

            for index, shape in enumerate(SELECTABLE):
                values = seatings.get(shape, [])
                period = shape.symmetry_period_deg
                if not values:
                    text = f"{index + 1}  {shape.value:<9} --"
                    colour = (220, 220, 220)
                elif not period:
                    text = f"{index + 1}  {shape.value:<9} n/a (no orientation)"
                    colour = (220, 220, 220)
                else:
                    play = circular_spread_deg(values, period)
                    text = (f"{index + 1}  {shape.value:<9}"
                            f"n={len(values)}  {circular_mean_deg(values, period):+7.2f}"
                            f"  play {play:5.2f}")
                    if len(values) < 3:
                        text += "  (seat it again)"
                        colour = (0, 165, 255)
                    elif play > LOOSE_SHARE * period:
                        text += "  LOOSE"
                        colour = (0, 165, 255)
                    else:
                        colour = (0, 200, 0)
                cv2.putText(canvas, text, (12, 140 + index * 26),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 1)

            cv2.imshow("slot angles - R box slot, 1-5 shape, SPACE record, S save, Q quit",
                       canvas)
            key = cv2.waitKey(20) & 0xFF

            if key in (ord("q"), ord("Q")):
                break
            if ord("1") <= key <= ord("5"):
                selected = SELECTABLE[key - ord("1")]
                history.clear()
                armed = True
            if key in (ord("r"), ord("R")):
                title = "drag a box round this slot, then ENTER"
                chosen = cv2.selectROI(title, shrink(frame.image, scale),
                                       showCrosshair=False)
                cv2.destroyWindow(title)
                # A zero-width selection means the operator pressed ESC.
                # The box is drawn on the shrunken preview, so it must be
                # scaled back up before it can search the real frame.
                regions[selected] = (to_full_resolution(chosen, scale)
                                     if chosen[2] and chosen[3] else None)
                if regions[selected] is None:
                    regions.pop(selected, None)
                history.clear()
            if key in (ord("c"), ord("C")):
                seatings.pop(selected, None)
                history.clear()
                armed = True
                print(f"{selected.value}: cleared, start again.")
            if key == ord(" ") and angle is not None:
                if not armed:
                    print("That would record the same seating again. Lift the "
                          "object out of the slot, then seat it and try once more.")
                elif not steady:
                    print("Not steady yet - wait for the reading to settle.")
                elif selected.is_rotationally_free:
                    seatings[selected] = [0.0]
                    print(f"{selected.value}: a circle needs no angle, recorded 0.0")
                else:
                    seatings.setdefault(selected, []).append(statistics.median(history))
                    values = seatings[selected]
                    period = selected.symmetry_period_deg
                    play = circular_spread_deg(values, period)
                    print(f"{selected.value}: seating {len(values)} read "
                          f"{values[-1]:+.2f}  ->  angle "
                          f"{circular_mean_deg(values, period):+.2f}, play {play:.2f} deg")
                    if len(values) < 3:
                        print("    Lift it out and seat it again - three seatings "
                              "minimum before the play means anything.")
                    elif play > LOOSE_SHARE * period:
                        print(f"    The slot has {play:.1f} deg of play against a "
                              f"{period:.0f} deg period. Placement must tolerate that.")
                    # Disarmed until the slot is seen empty again, so the
                    # same seating cannot be counted twice.
                    history.clear()
                    armed = False
            if key in (ord("s"), ord("S")):
                write_yaml(Path(args.out), seatings)
    finally:
        source.close()
        cv2.destroyAllWindows()

    write_yaml(Path(args.out), seatings)
    return 0


def write_yaml(path: Path, seatings: Dict[Shape, List[float]]) -> None:
    """Write the block to paste into config.yaml.

    Each angle is the circular mean over the seatings, and the play is carried
    alongside it as a comment: it is the tolerance every placement of that
    shape has to live inside, and it is worth seeing when reading the config.
    """
    if not seatings:
        print("Nothing recorded.")
        return

    lines = ["# Measured with calibration/slot_angles.py.",
             "# Re-measure whenever the jig moves.",
             "# 'play' is the spread across seatings - the slot's own slack plus",
             "# measurement noise. The placement must tolerate all of it.",
             "place_slot_angles_deg:"]
    for shape, values in seatings.items():
        period = shape.symmetry_period_deg
        angle = circular_mean_deg(values, period) if period else 0.0
        play = circular_spread_deg(values, period) if period else 0.0
        note = f"{len(values)} seating(s)"
        if period and len(values) < 3:
            note += ", TOO FEW to judge the play"
        elif period and play > LOOSE_SHARE * period:
            note += f", LOOSE: {play:.2f} deg of a {period:.0f} deg period"
        else:
            note += f", play {play:.2f} deg"
        lines.append(f"  {shape.value}: {angle:.2f}   # {note}")
    text = "\n".join(lines) + "\n"

    path.write_text(text, encoding="utf-8")
    print(f"\nSaved to {path}\n\n{text}")


if __name__ == "__main__":
    raise SystemExit(main())
