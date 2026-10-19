"""Works out marker_angle_deg and y_axis_flipped from one object.

Put one object somewhere you can measure from the work object's origin
corner, read what the GUI says, and give this both numbers:

    python tools/solve_axes.py --true 60 80 --reported 278.5 121.5

It prints which of the eight settings turns the reading into the truth.

Why this and not trial and error: there are four angles times two mirrors,
and at the station each attempt costs an edit, a deploy and a restart. The
arithmetic is the same either way, so it may as well be done once, here.

The maths: every setting places the marker's four corners in work object
millimetres, and the homography follows from those four points. Changing the
setting therefore moves the whole output by one rigid transform about the
marker centre - a rotation, and a mirror if the flip changes. So the reading
you already have is enough to predict all eight.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import List, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

ANGLES = (0.0, 90.0, 180.0, 270.0)
# Below this the candidate explains the reading; above it, it does not. A
# millimetre or two of hand measurement is expected, a quarter turn is not.
CLOSE_ENOUGH_MM = 8.0


def transform(point: Tuple[float, float], centre: Tuple[float, float],
              angle_deg: float, flipped: bool) -> Tuple[float, float]:
    """Where `point` lands when the world corners are built this way."""
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    y_sign = -1.0 if flipped else 1.0
    local_x = point[0] - centre[0]
    local_y = (point[1] - centre[1]) * y_sign
    return (centre[0] + local_x * cos_t - local_y * sin_t,
            centre[1] + local_x * sin_t + local_y * cos_t)


def inverse_transform(point: Tuple[float, float], centre: Tuple[float, float],
                      angle_deg: float, flipped: bool) -> Tuple[float, float]:
    """Undo `transform` - back to the marker's own frame."""
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    dx = point[0] - centre[0]
    dy = point[1] - centre[1]
    local_x = dx * cos_t + dy * sin_t
    local_y = -dx * sin_t + dy * cos_t
    if flipped:
        local_y = -local_y
    return (centre[0] + local_x, centre[1] + local_y)


def candidates(reported: Tuple[float, float], centre: Tuple[float, float],
               current_angle: float, current_flip: bool) -> List[tuple]:
    """Every setting, and where the same object would then read."""
    # Back out of the current setting first, then into each candidate.
    neutral = inverse_transform(reported, centre, current_angle, current_flip)
    rows = []
    for angle in ANGLES:
        for flipped in (False, True):
            rows.append((angle, flipped, transform(neutral, centre, angle, flipped)))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--true", dest="truth", nargs=2, type=float, required=True,
                        metavar=("X", "Y"), help="measured from the origin corner")
    parser.add_argument("--reported", nargs=2, type=float, required=True,
                        metavar=("X", "Y"), help="what the GUI says for that object")
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()

    from infrastructure.config_loader import load_config
    config = load_config(BASE_DIR / args.config)
    aruco = config.get("aruco", {})
    marker = aruco.get("marker_centre_xy_mm", (0.0, 0.0))
    centre = (float(marker[0]), float(marker[1]))
    current_angle = float(aruco.get("marker_angle_deg", 0.0))
    current_flip = bool(aruco.get("y_axis_flipped", False))

    truth = (args.truth[0], args.truth[1])
    reported = (args.reported[0], args.reported[1])

    print(f"\nmarker centre {centre[0]:.1f}, {centre[1]:.1f} mm   "
          f"now: angle {current_angle:.0f}, flipped {current_flip}")
    print(f"object truly at {truth[0]:.1f}, {truth[1]:.1f} - "
          f"read as {reported[0]:.1f}, {reported[1]:.1f}\n")

    rows = []
    for angle, flipped, landed in candidates(reported, centre,
                                             current_angle, current_flip):
        error = math.dist(landed, truth)
        rows.append((error, angle, flipped, landed))
    rows.sort()

    print(f"{'angle':>6}{'flipped':>9}{'would read':>22}{'off by':>10}")
    for error, angle, flipped, landed in rows:
        mark = "  <-- this one" if error <= CLOSE_ENOUGH_MM else ""
        print(f"{angle:6.0f}{str(flipped):>9}"
              f"{landed[0]:12.1f},{landed[1]:8.1f}{error:10.1f}{mark}")

    best_error, best_angle, best_flip, _ = rows[0]
    if best_error > CLOSE_ENOUGH_MM:
        print(f"\nNothing fits within {CLOSE_ENOUGH_MM:.0f} mm. The axes are not "
              f"merely turned: check that wobj1 was taught with +X along the "
              f"SHORT (297 mm) edge, and that marker_centre_xy_mm is the "
              f"marker's real place on the sheet.")
        return 1

    runner_up = rows[1][0]
    print(f"\n  marker_angle_deg: {best_angle:.1f}")
    print(f"  y_axis_flipped: {str(best_flip).lower()}")
    if runner_up - best_error < CLOSE_ENOUGH_MM:
        print("\n  WARNING: a second setting fits almost as well. Measure a "
              "second object, further from the marker centre, before trusting "
              "this - near the centre every setting agrees.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
