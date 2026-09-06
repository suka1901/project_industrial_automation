"""Manual four-point calibration, a fallback to the marker.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import csv
import sys
from typing import Any
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from adapters.mapping.homography_mapper import HomographyMapper  # noqa: E402


def load_world_points(path: Path):
    """Read the measured work-object coordinates, one 'x_mm,y_mm' per line."""
    points = []
    with path.open("r", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if not row or row[0].strip().startswith("#"):
                continue
            points.append((float(row[0]), float(row[1])))
    return points


def main() -> int:
    import cv2

    parser = argparse.ArgumentParser(description="Solve the camera homography")
    parser.add_argument("--image", required=True,
                        help="a still photo of the table from the fixed camera")
    parser.add_argument("--points", required=True,
                        help="CSV of measured work-object coordinates, in click order")
    parser.add_argument("--output", default=str(BASE_DIR / "calibration/homography.json"))
    args = parser.parse_args()

    world_points = load_world_points(Path(args.points))
    image = cv2.imread(args.image)
    if image is None:
        print(f"Could not read image: {args.image}")
        return 1

    print(f"Click {len(world_points)} point(s) in the same order as your CSV.")
    print("Keys:  u = undo last click   s = solve and save   q = quit")

    pixel_points: list[tuple[float, float]] = []

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(pixel_points) < len(world_points):
            pixel_points.append((float(x), float(y)))
            print(f"  point {len(pixel_points)}: pixel ({x}, {y}) "
                  f"-> {world_points[len(pixel_points) - 1]} mm")

    window = "calibration - click the measured points"
    cv2.namedWindow(window)
    cv2.setMouseCallback(window, on_mouse)

    while True:
        # Annotated Any because OpenCV's stubs declare the drawing helpers
        # as taking Mat while imread returns a plain ndarray - the two are
        # the same object at runtime, but the checker treats them apart.
        canvas: Any = image.copy()
        for index, (u, v) in enumerate(pixel_points):
            cv2.drawMarker(canvas, (int(u), int(v)), (0, 0, 255),
                           cv2.MARKER_CROSS, 20, 2)
            cv2.putText(canvas, str(index + 1), (int(u) + 8, int(v) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.imshow(window, canvas)

        key = cv2.waitKey(20) & 0xFF
        if key == ord("q"):
            break
        if key == ord("u") and pixel_points:
            pixel_points.pop()
            print("  undone")
        if key == ord("s"):
            if len(pixel_points) < 4:
                print("Need at least four points before solving.")
                continue
            mapper, residual = HomographyMapper.fit(
                pixel_points, world_points[:len(pixel_points)]
            )
            mapper.save(args.output, residual_mm=residual)
            print(f"\nSaved to {args.output}")
            print(f"Mean reprojection error: {residual:.2f} mm")
            if residual > 2.0:
                print("WARNING: over 2 mm. Re-measure your points or spread them wider.")
            break

    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
