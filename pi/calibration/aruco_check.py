"""Live marker check: detection, scale, and stability.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import deque
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))


from calibration.view import display_scale, shrink  # noqa: E402


def marker_length_from_config(default: float = 100.0) -> float:
    """Marker size from config.yaml, so the tool runs with no arguments."""
    try:
        from infrastructure.config_loader import load_config
        config = load_config(BASE_DIR / "config" / "config.yaml")
        return float(config["aruco"]["marker_length_mm"])
    except Exception:
        return default


def build_source(kind: str, path: str | None):
    """Create a frame source without needing the whole config machinery."""
    if kind == "basler":
        from adapters.camera.camera import Camera
        return Camera()
    from adapters.camera.file_source import FileFrameSource
    return FileFrameSource(directory=path or str(BASE_DIR / "../model/dataset"))


def main() -> int:
    import cv2

    parser = argparse.ArgumentParser(description="Live ArUco marker check")
    parser.add_argument("--length", type=float, default=None,
                        help="marker side length in mm (default: from config.yaml)")
    parser.add_argument("--camera", default="basler", choices=("basler", "tap", "file"))
    parser.add_argument("--path", default=None, help="image folder for --camera file")
    parser.add_argument("--dictionary", default="DICT_5X5_100")
    args = parser.parse_args()
    if args.length is None:
        args.length = marker_length_from_config()

    if not hasattr(cv2, "aruco"):
        print("cv2.aruco is missing")
        return 1

    # Reuses the same ArUco class the running system uses, so this tool can
    # never drift away from what the calibrator actually does.
    from adapters.detection.aruco import ArUco
    aruco = ArUco(dictionary_name=args.dictionary, marker_length_mm=args.length)

    # A short history lets us report how stable the measurement is, which is a
    # far more useful number than any single reading.
    history: deque[float] = deque(maxlen=60)

    source = build_source(args.camera, args.path)
    source.open()
    print("Press q to quit.")

    try:
        while True:
            frame = source.read()
            if frame is None or frame.image is None:
                continue

            image = frame.image.copy()
            corners, ids = aruco.detect(image)

            if ids is not None and len(corners) > 0:
                aruco.draw(image, corners, ids)

                ratio = aruco.pixel_mm_ratio(corners[0])
                history.append(ratio)

                spread = statistics.pstdev(history) if len(history) > 4 else 0.0
                text = (f"ids={[int(v) for v in ids.flatten()]}  "
                        f"{ratio:.3f} px/mm  (jitter {spread:.4f})")
                colour = (0, 200, 0) if spread < 0.02 else (0, 165, 255)
            else:
                text = "no marker detected"
                colour = (0, 0, 255)

            cv2.putText(image, text, (36, 32), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, colour, 2)
            cv2.imshow("ArUco check - press q to quit",
                       shrink(image, display_scale(image)))

            if (cv2.waitKey(20) & 0xFF) == ord("q"):
                break
    finally:
        source.close()
        cv2.destroyAllWindows()

    if history:
        print(f"\nmean ratio : {statistics.mean(history):.3f} px/mm")
        print(f"jitter     : {statistics.pstdev(history):.4f} px/mm")
        print("A jitter above about 0.02 px/mm means the detection is unstable - "
              "check focus, lighting and glare before trusting any coordinates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
