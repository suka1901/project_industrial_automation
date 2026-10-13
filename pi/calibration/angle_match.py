"""Matches the camera's sense of rotation to the robot's.

Solves one equation, by measurement rather than by reasoning about image
conventions, quaternion handedness and what RelTool rotates about:

    placed = picked + k * rz + c

`k` is coordinates.angle_sign, +1 or -1. `c` is the fixed wrist offset between
the picking pose and the slot pose - a constant the placement has to carry
whatever k turns out to be. Both fall out of two cycles with the object
started at two DIFFERENT angles: one cycle cannot separate k from c, because
one equation has two unknowns.

`rz` is not typed in. It is read from the system's own log, so the number
solved with is the exact number sent to the robot.

How to use it, with main.py running and the jig in frame:

    1. P  - drag a box round where the object sits on the sheet
    2. J  - drag a box round the slot it will be placed in
    3. 1-5 - pick the shape
    4. put the object on the sheet, wait for STEADY, press B
    5. run one cycle on the robot
    6. once it is sitting in the slot, wait for STEADY, press A
    7. repeat 4-6 with the object started at a clearly different angle
    8. S  - save

Keep rz away from half the symmetry period (45 deg for a square, 36 for a
star). There a sign error is invisible: +45 and -45 are the same rotation.
The screen warns when a reading lands there.

Keys: P box the sheet, J box the slot, 1-5 shape, B before, A after,
      C clear this shape, S save, Q quit.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, NamedTuple, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from domain.enums import Colour, Shape  # noqa: E402
from domain.models import Detection  # noqa: E402
from domain.angles import (circular_mean_deg,  # noqa: E402
                           circular_spread_deg)
from calibration.slot_angles import (build_source,  # noqa: E402
                                     largest_object_box)
from calibration.view import (display_scale, shrink,  # noqa: E402
                              to_full_resolution)

SELECTABLE: List[Shape] = list(Shape)
HISTORY = 40            # frames behind the stability readout
STABLE_DEG = 0.5        # frame-to-frame spread below which a reading counts
# Two rz values closer together than this cannot tell k = +1 from k = -1:
# the two fits differ by 2*rz, so nearly equal rz gives nearly equal residuals.
MIN_RZ_SPREAD_DEG = 10.0
# A commanded rz within this of half the period is refused outright - there
# +rz and -rz are the same rotation and the measurement proves nothing.
DEGENERATE_MARGIN_DEG = 8.0
# Below this spread in (placed - picked) while rz varies, the wrist is not
# turning at all and no sign can be fitted from the readings.
INERT_SPREAD_DEG = 2.0

MOVE_LINE = re.compile(r"->\s+move\s+(\w+)\s+\S+\s+\S+\s+(-?[\d.]+)#")


class Row(NamedTuple):
    """One cycle: what the camera saw before and after, and what was sent."""

    picked: float
    placed: float
    rz: float


def fold(angle: float, period: float) -> float:
    """Into (-period/2, +period/2] - the shortest equivalent rotation."""
    if period <= 0.0:
        return 0.0
    folded = angle % period
    return folded - period if folded > period / 2.0 else folded


def commands_in(log_path: Path) -> List[Tuple[str, float]]:
    """Every 'move' command the log has recorded, oldest first."""
    if not log_path.is_file():
        return []
    found = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = MOVE_LINE.search(line)
        if match:
            found.append((match.group(1).lower(), float(match.group(2))))
    return found


def fit(rows: List[Row], period: float) -> Dict[str, object]:
    """Which sign explains the readings, and how well.

    Both signs are fitted and compared: the right one leaves a consistent
    offset across the rows, the wrong one leaves an offset that swings by
    twice rz. Choosing by consistency rather than by a single reading is what
    makes two cycles enough.
    """
    result: Dict[str, object] = {"rows": len(rows)}
    if len(rows) < 2:
        result["verdict"] = "need at least two cycles"
        return result

    rz_spread = max(r.rz for r in rows) - min(r.rz for r in rows)
    turn_spread = circular_spread_deg([fold(r.placed - r.picked, period)
                                       for r in rows], period)
    result["rz_spread"] = rz_spread
    result["turn_spread"] = turn_spread

    if rz_spread < MIN_RZ_SPREAD_DEG:
        result["verdict"] = (
            f"the two cycles used almost the same rz ({rz_spread:.1f} deg "
            f"apart). Start the object at a clearly different angle and "
            f"record another cycle.")
        return result

    if turn_spread < INERT_SPREAD_DEG:
        result["verdict"] = (
            f"THE WRIST IS NOT TURNING. rz varied by {rz_spread:.1f} deg but "
            f"the object turned by the same {turn_spread:.2f} deg every time. "
            f"No sign can be fitted from this - RelTool's \\Rz is not reaching "
            f"the motion. Fix that first; this measurement cannot.")
        return result

    for sign in (1, -1):
        residuals = [fold(r.placed - r.picked - sign * r.rz, period) for r in rows]
        result[f"offset{sign:+d}"] = circular_mean_deg(residuals, period)
        result[f"spread{sign:+d}"] = circular_spread_deg(residuals, period)

    best = 1 if result["spread+1"] <= result["spread-1"] else -1
    worst = -best
    result["angle_sign"] = best
    result["offset"] = result[f"offset{best:+d}"]
    result["spread"] = result[f"spread{best:+d}"]
    result["margin"] = result[f"spread{worst:+d}"] - result[f"spread{best:+d}"]

    if result["margin"] < 2.0 * STABLE_DEG:
        result["verdict"] = (
            f"both signs fit about equally well (spreads "
            f"{result['spread+1']:.2f} and {result['spread-1']:.2f}). Record "
            f"another cycle at a different starting angle.")
    else:
        result["verdict"] = "ok"
    return result


def main() -> int:
    import cv2

    parser = argparse.ArgumentParser(
        description="Match the camera's rotation sense to the robot's")
    parser.add_argument("--camera", default="basler", choices=("basler", "tap", "file"))
    parser.add_argument("--path", default=None)
    parser.add_argument("--log", default=str(BASE_DIR / "logs" / "ina700.log"),
                        help="where main.py writes; rz is read from here")
    parser.add_argument("--out",
                        default=str(BASE_DIR / "calibration" / "angle_match.yaml"))
    parser.add_argument("--config", default="config/config.yaml",
                        help="the configuration whose orientation.kind decides HOW the angle is measured. It must be the one main.py runs: a slot angle measured with one estimator does not cancel against an object angle measured with another")
    parser.add_argument("--display-width", type=int, default=1100)
    args = parser.parse_args()

    # The slot angle and the object angle are subtracted from each other at
    # run time, so every constant offset cancels - but only while BOTH are
    # measured the same way. Building the estimator from the configuration is
    # what keeps that true when orientation.kind changes.
    from infrastructure.config_loader import load_config
    from infrastructure.container import Container
    config = load_config(BASE_DIR / args.config)
    estimator = Container(config, BASE_DIR).build_orientation_estimator()
    estimator_kind = str(config.get("orientation", {}).get("kind", "fitted")).lower()
    log_path = Path(args.log)

    rows: Dict[Shape, List[Row]] = {}
    pending: Dict[Shape, Tuple[float, int]] = {}   # picked angle, commands seen
    sheet_region: Optional[Tuple[int, int, int, int]] = None
    slot_region: Optional[Tuple[int, int, int, int]] = None
    history: Deque[float] = deque(maxlen=HISTORY)
    selected = SELECTABLE[0]

    source = build_source(args.camera, args.path)
    source.open()
    print(__doc__)

    try:
        while True:
            frame = source.read()
            if frame is None or frame.image is None:
                continue

            scale = display_scale(frame.image, args.display_width)
            canvas = shrink(frame.image, scale)
            waiting = selected in pending
            # Before a cycle the object is on the sheet; after it, in the slot.
            region = slot_region if waiting else sheet_region

            for area, colour in ((sheet_region, (255, 180, 0)),
                                 (slot_region, (200, 120, 255))):
                if area is None:
                    continue
                x, y, w, h = area
                cv2.rectangle(canvas, (int(x * scale), int(y * scale)),
                              (int((x + w) * scale), int((y + h) * scale)),
                              colour, 2)

            angle: Optional[float] = None
            box = largest_object_box(frame.image, region) if region else None
            if box is not None:
                detection = Detection(shape=selected, colour=Colour.UNKNOWN,
                                      confidence=1.0, centre=box.centre,
                                      angle_deg=0.0, box=box)
                angle = estimator.measure(frame, detection).angle_deg
                history.append(angle)
                cv2.rectangle(canvas,
                              (int(box.u_min * scale), int(box.v_min * scale)),
                              (int(box.u_max * scale), int(box.v_max * scale)),
                              (0, 200, 0), 2)
            else:
                history.clear()

            spread = statistics.pstdev(history) if len(history) > 8 else 99.0
            steady = spread < STABLE_DEG
            period = selected.symmetry_period_deg

            if selected.is_rotationally_free:
                step = "a circle has no orientation - pick another shape"
            elif region is None:
                step = ("press J and box the slot" if waiting
                        else "press P and box the sheet")
            elif waiting:
                step = ("in the slot: wait for STEADY then press A"
                        if angle is not None else "waiting for the object in the slot")
            else:
                step = ("on the sheet: wait for STEADY then press B"
                        if angle is not None else "put the object on the sheet")

            lines = [
                f"shape: {selected.value}   period "
                + (f"{period:.0f} deg" if period else "n/a"),
                (f"angle: {angle:+7.2f} deg   spread {spread:.2f}"
                 if angle is not None else "angle: no object in this box"),
                step,
            ]
            outcome = fit(rows.get(selected, []), period) if period else {}
            if outcome.get("verdict") == "ok":
                lines.append(f"angle_sign {outcome['angle_sign']:+d}   offset "
                             f"{outcome['offset']:+.2f} deg   spread "
                             f"{outcome['spread']:.2f}   n={outcome['rows']}")
            elif outcome.get("verdict"):
                lines.append(str(outcome["verdict"])[:78])

            for index, line in enumerate(lines):
                cv2.putText(canvas, line, (12, 32 + index * 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                            (0, 200, 0) if steady else (0, 165, 255), 2)

            for index, shape in enumerate(SELECTABLE):
                taken = rows.get(shape, [])
                mark = "  <- waiting for the cycle" if shape in pending else ""
                cv2.putText(canvas, f"{index + 1}  {shape.value:<9} "
                                    f"{len(taken)} cycle(s){mark}",
                            (12, 150 + index * 24), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (220, 220, 220), 1)

            cv2.imshow("angle match - P sheet, J slot, 1-5 shape, B before, "
                       "A after, S save, Q quit", canvas)
            key = cv2.waitKey(20) & 0xFF

            if key in (ord("q"), ord("Q")):
                break
            if ord("1") <= key <= ord("5"):
                selected = SELECTABLE[key - ord("1")]
                history.clear()
            if key in (ord("p"), ord("P"), ord("j"), ord("J")):
                title = ("drag a box round the SLOT, then ENTER"
                         if key in (ord("j"), ord("J"))
                         else "drag a box round the SHEET area, then ENTER")
                chosen = cv2.selectROI(title, shrink(frame.image, scale),
                                       showCrosshair=False)
                cv2.destroyWindow(title)
                area = (to_full_resolution(chosen, scale)
                        if chosen[2] and chosen[3] else None)
                if key in (ord("j"), ord("J")):
                    slot_region = area
                else:
                    sheet_region = area
                history.clear()
            if key in (ord("c"), ord("C")):
                rows.pop(selected, None)
                pending.pop(selected, None)
                history.clear()
                print(f"{selected.value}: cleared.")
            if key in (ord("b"), ord("B")):
                if selected.is_rotationally_free:
                    print("A circle has no orientation to match.")
                elif angle is None or not steady:
                    print("Not steady yet - wait for the reading to settle.")
                else:
                    seen = len(commands_in(log_path))
                    pending[selected] = (statistics.median(history), seen)
                    print(f"{selected.value}: before = "
                          f"{pending[selected][0]:+.2f} deg. Run one cycle, "
                          f"then press A with it sitting in the slot.")
            if key in (ord("a"), ord("A")):
                if selected not in pending:
                    print("Press B first, with the object on the sheet.")
                elif angle is None or not steady:
                    print("Not steady yet - wait for the reading to settle.")
                else:
                    picked, seen_before = pending[selected]
                    commands = commands_in(log_path)
                    fresh = [c for c in commands[seen_before:]
                             if c[0] == selected.value.lower()]
                    if not fresh:
                        print(f"No '{selected.value}' command in {log_path} "
                              f"since B was pressed. Did the cycle run, and is "
                              f"main.py writing to that log?")
                    else:
                        rz = fresh[-1][1]
                        half = period / 2.0
                        if abs(abs(fold(rz, period)) - half) < DEGENERATE_MARGIN_DEG:
                            print(f"rz was {rz:+.1f}, which is half the "
                                  f"{period:.0f} deg period - there a sign error "
                                  f"is invisible. Start the object elsewhere and "
                                  f"run this cycle again.")
                            pending.pop(selected, None)
                        else:
                            placed = statistics.median(history)
                            rows.setdefault(selected, []).append(
                                Row(picked, placed, rz))
                            pending.pop(selected, None)
                            print(f"{selected.value}: picked {picked:+.2f}, "
                                  f"rz {rz:+.1f}, placed {placed:+.2f}  "
                                  f"-> turned {fold(placed - picked, period):+.2f}")
                            report(rows[selected], period)
                    history.clear()
            if key in (ord("s"), ord("S")):
                write_yaml(Path(args.out), rows)
    finally:
        source.close()
        cv2.destroyAllWindows()

    write_yaml(Path(args.out), rows)
    return 0


def report(taken: List[Row], period: float) -> None:
    outcome = fit(taken, period)
    if outcome.get("verdict") == "ok":
        print(f"    angle_sign {outcome['angle_sign']:+d}, offset "
              f"{outcome['offset']:+.2f} deg, residual spread "
              f"{outcome['spread']:.2f} deg over {outcome['rows']} cycles "
              f"(the other sign is {outcome['margin']:.2f} deg worse)")
    else:
        print(f"    {outcome.get('verdict')}")


def write_yaml(path: Path, rows: Dict[Shape, List[Row]]) -> None:
    """Write the block to paste into config.yaml, plus the readings behind it."""
    usable = {s: r for s, r in rows.items()
              if s.symmetry_period_deg and len(r) >= 2}
    if not usable:
        print("Nothing to save - two cycles of one shape are the minimum.")
        return

    fits = {s: fit(r, s.symmetry_period_deg) for s, r in usable.items()}
    agreed = {s: f for s, f in fits.items() if f.get("verdict") == "ok"}

    lines = ["# Measured with calibration/angle_match.py.",
             "# Solves placed = picked + k * rz + c across whole cycles, so it",
             "# settles the image convention, the tool axis and RelTool's sense",
             "# in one measurement instead of three arguments.",
             "# Re-measure if the camera is remounted or the cup is re-taught."]

    if not agreed:
        lines.append("# NO AGREED RESULT - see the readings below.")
    else:
        signs = {f["angle_sign"] for f in agreed.values()}
        if len(signs) > 1:
            lines.append("# SHAPES DISAGREE on the sign. That cannot be right -")
            lines.append("# the sense is a property of the camera and the wrist,")
            lines.append("# not of the shape. Re-measure before using this.")
        else:
            sign = signs.pop()
            offsets = [f["offset"] for f in agreed.values()]
            lines += ["coordinates:",
                      f"  angle_sign: {sign}",
                      f"  angle_offset_deg: 0.0   # the {statistics.mean(offsets):+.2f} "
                      f"deg offset is already inside the measured slot angles"]

    lines += ["", "# Not for config.yaml - the readings this rests on."]
    for shape, taken in usable.items():
        outcome = fits[shape]
        lines.append(f"# {shape.value}: {outcome.get('verdict')}")
        for row in taken:
            lines.append(f"#   picked {row.picked:+7.2f}  rz {row.rz:+7.2f}"
                         f"  placed {row.placed:+7.2f}")
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    print(f"\nSaved to {path}\n\n{text}")


if __name__ == "__main__":
    raise SystemExit(main())
