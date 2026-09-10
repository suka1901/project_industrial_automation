"""Pre-flight check for packages, camera, config and marker.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
MARKER_FRAMES = 15          # frames used for the stability estimate
STABLE_PX_PER_MM = 0.02     # gate from STEPS.md 2.5
SHEET_BRIGHT_MIN = 150      # 95th percentile grey the A3 sheet should reach
SHEET_BRIGHT_MAX = 245      # above this the paper is clipping
SATURATED_MAX_PCT = 0.1     # share of pixels allowed at 255

results: List[Tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    symbol = {PASS: "  ok  ", FAIL: " FAIL ", SKIP: " skip "}[status]
    print(f"[{symbol}] {name:<26} {detail}")


# --- packages --------------------------------------------------------------

def check_python() -> None:
    version = sys.version_info
    text = f"{version.major}.{version.minor}.{version.micro}"
    if version >= (3, 9):
        record("python", PASS, text)
    else:
        record("python", FAIL, f"{text} - 3.9 or newer is needed")


def check_opencv() -> None:
    try:
        import cv2
    except ImportError:
        record("opencv", FAIL, "not installed - pip install opencv-contrib-python")
        return

    if not hasattr(cv2, "aruco"):
        record("opencv", FAIL,
               f"{cv2.__version__} has no aruco - you have the plain "
               "opencv-python package. Remove every opencv package, then "
               "install only opencv-contrib-python")
        return

    record("opencv", PASS, f"{cv2.__version__} with aruco")


def check_package(label: str, module: str, install: str) -> None:
    try:
        __import__(module)
    except ImportError:
        record(label, FAIL, f"not installed - pip install {install}")
        return
    record(label, PASS)


# --- camera ----------------------------------------------------------------

def check_camera(grab: bool) -> Optional[Any]:
    """Enumerate Basler cameras and optionally grab one frame."""
    try:
        from pypylon import pylon
    except ImportError:
        record("pypylon", FAIL,
               "not installed - install the Basler Pylon SDK, then pip install pypylon")
        return None
    record("pypylon", PASS)

    try:
        devices = pylon.TlFactory.GetInstance().EnumerateDevices()
    except Exception as exc:
        record("camera search", FAIL, str(exc))
        return None

    if not devices:
        record("camera found", FAIL,
               "no Basler camera detected - check the cable, and confirm "
               "Pylon Viewer sees it before blaming Python")
        return None

    names = ", ".join(f"{d.GetModelName()} ({d.GetSerialNumber()})" for d in devices)
    record("camera found", PASS, names)

    if not grab:
        return None

    try:
        from adapters.camera.camera import Camera
        camera = Camera()
        camera.open()
        frame = None
        for _ in range(10):
            frame = camera.read()
            if frame is not None and frame.image is not None:
                break
        if frame is None or frame.image is None:
            camera.close()
            record("frame grab", FAIL, "camera opened but delivered no image")
            return None
        height, width = frame.image.shape[:2]
        record("frame grab", PASS, f"{width} x {height}")
        report_camera_settings(camera)
        return camera
    except Exception as exc:
        record("frame grab", FAIL, str(exc))
        return None


def report_camera_settings(camera: Any) -> None:
    """Print what the camera is actually set to, so config.yaml can match it.

    preflight opens the camera without applying the config, so these are the
    camera's own values - the ones to copy into config.yaml.
    """
    device = getattr(camera, "_camera", None)
    if device is None:
        return

    def read(name: str):
        try:
            return device.GetNodeMap().GetNode(name).GetValue()
        except Exception:
            return None

    exposure = read("ExposureTime")
    gain = read("Gain")
    auto_exposure = read("ExposureAuto")
    auto_gain = read("GainAuto")
    rate = read("ResultingFrameRate")

    if exposure is not None:
        record("camera exposure", PASS, f"{exposure:.0f} us  ->  put this in config.yaml")
    if gain is not None:
        record("camera gain", PASS, f"{gain:.2f}  ->  put this in config.yaml")
    if rate is not None:
        record("camera rate", PASS, f"{rate:.1f} fps")

    for label, value in (("exposure", auto_exposure), ("gain", auto_gain)):
        if value is None:
            continue
        if str(value).lower() == "off":
            record(f"auto {label}", PASS, "off")
        else:
            record(f"auto {label}", FAIL,
                   f"'{value}' - turn it OFF in Pylon Viewer. Colours will drift "
                   "between your dataset and the demonstration")


# --- configuration ---------------------------------------------------------

def check_config() -> None:
    try:
        from infrastructure.config_loader import load_config
        config = load_config(BASE_DIR / "config" / "config.yaml")
    except Exception as exc:
        record("config.yaml", FAIL, str(exc))
        return

    camera_kind = config.get("camera", {}).get("kind")
    detector_kind = config.get("detector", {}).get("kind")
    mapper = config.get("coordinates", {}).get("mapper")
    transport = config.get("robot", {}).get("transport")
    marker = config.get("aruco", {}).get("marker_length_mm")

    record("config.yaml", PASS,
           f"camera={camera_kind} detector={detector_kind} "
           f"mapper={mapper} robot={transport}")

    if camera_kind != "basler":
        record("config: camera", SKIP,
               f"kind is '{camera_kind}' - set it to 'basler' for live work")
    if mapper != "aruco":
        record("config: mapper", SKIP,
               f"mapper is '{mapper}' - set it to 'aruco' once calibrated")
    if marker:
        record("config: marker", PASS, f"marker_length_mm = {marker}")

    # The detector the config asks for must actually be runnable here. On the
    # Pi this is the difference between a clean message now and a stack trace
    # after the camera and the GUI have already started.
    if detector_kind == "yolo":
        try:
            import ultralytics  # noqa: F401
        except ImportError:
            record("config: detector", FAIL,
                   "kind is 'yolo' but ultralytics is not installed - on the Pi "
                   "run with --config config/profiles/pi.yaml (kind: ncnn)")
    elif detector_kind == "ncnn":
        try:
            import ncnn  # noqa: F401
            record("config: detector", PASS, "kind=ncnn, no torch needed")
        except ImportError:
            record("config: detector", FAIL, "kind is 'ncnn' but ncnn is not installed")


MIN_SEATINGS = 3        # below this the play across seatings means nothing


def judge_slot_angles(in_use: dict, measured: dict, quality: dict) -> tuple:
    """Compare what config uses against what was measured. Pure, so it is tested.

    Returns (status, detail). The order of the checks is the order the mistakes
    actually happen in: not pasted, never measured, then not measured enough.
    """
    turning = {k: v for k, v in in_use.items() if k != "CIRCLE"}

    stale = {name: (in_use.get(name, 0.0), value) for name, value in measured.items()
             if abs(in_use.get(name, 0.0) - value) > 0.01}
    if stale:
        detail = ", ".join(f"{n}: config {c:.2f} vs measured {m:.2f}"
                           for n, (c, m) in sorted(stale.items()))
        return FAIL, (f"NOT PASTED - {detail}. Copy the place_slot_angles_deg "
                      f"block from calibration/slot_angles.yaml into config.yaml")

    missing = sorted(n for n in turning if n not in measured)
    if missing:
        return FAIL, (f"never measured: {', '.join(missing)} - "
                      f"these would place unrotated")

    thin = sorted(n for n, q in quality.items()
                  if n != "CIRCLE" and isinstance(q, dict)
                  and int(q.get("seatings", 0)) < MIN_SEATINGS)
    if thin:
        return SKIP, (f"only 1-2 seatings for {', '.join(thin)} - the play is "
                      f"unknown, seat each one at least {MIN_SEATINGS} times")

    plays = [f"{n} {q.get('play_deg', 0):.2f}deg"
             for n, q in sorted(quality.items())
             if n != "CIRCLE" and isinstance(q, dict)]
    return PASS, ("pasted; play " + ", ".join(plays)) if plays else (PASS, "pasted")[1]


def check_slot_angles() -> None:
    """Did the measured slot angles ever reach config.yaml?

    calibration/slot_angles.py writes a block for pasting; nothing reads that
    file at run time. Forgetting to paste it is silent and expensive: every
    object is then placed unrotated, which looks like a calibration fault
    rather than a missed step.
    """
    import yaml

    try:
        from infrastructure.config_loader import load_config
        config = load_config(BASE_DIR / "config" / "config.yaml")
    except Exception:
        return                                  # check_config already failed

    in_use = {str(k).upper(): float(v) for k, v in
              (config.get("coordinates", {}).get("place_slot_angles_deg") or {}).items()}
    turning = {k: v for k, v in in_use.items() if k != "CIRCLE"}

    measured_file = BASE_DIR / "calibration" / "slot_angles.yaml"
    if not measured_file.is_file():
        if turning and not any(turning.values()):
            record("slot angles", SKIP,
                   "all zero and nothing measured yet - run calibration/slot_angles.py")
        else:
            record("slot angles", PASS, f"{len(turning)} shape(s) set in config.yaml")
        return

    try:
        saved = yaml.safe_load(measured_file.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        record("slot angles", FAIL, f"cannot read slot_angles.yaml: {exc}")
        return

    measured = {str(k).upper(): float(v) for k, v in
                (saved.get("place_slot_angles_deg") or {}).items()}
    quality = {str(k).upper(): v for k, v in (saved.get("slot_angle_quality") or {}).items()}

    status, detail = judge_slot_angles(in_use, measured, quality)
    record("slot angles", status, detail)


# --- marker ----------------------------------------------------------------

def check_lighting(camera: Optional[Any]) -> None:
    """Judge the exposure from the brightest part of the frame - the A3 sheet."""
    if camera is None:
        record("lighting", SKIP, "no camera")
        return

    import cv2
    import numpy as np

    frame = camera.read()
    if frame is None or frame.image is None:
        record("lighting", FAIL, "no frame")
        return

    grey = cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY) if frame.image.ndim == 3 else frame.image
    sheet = float(np.percentile(grey, 95))
    saturated = float((grey >= 255).mean()) * 100.0
    detail = f"sheet {sheet:.0f}/255, {saturated:.2f}% clipped"

    if saturated > SATURATED_MAX_PCT:
        record("lighting", FAIL, detail + " - lower exposure or diffuse the lamp")
    elif sheet < SHEET_BRIGHT_MIN:
        record("lighting", FAIL, detail +
               " - add light or raise exposure until the sheet reads 180-210")
    elif sheet > SHEET_BRIGHT_MAX:
        record("lighting", FAIL, detail + " - close to clipping, lower exposure")
    else:
        record("lighting", PASS, detail)


def check_marker(camera: Optional[Any], length_mm: float) -> None:
    """Detect the marker over several frames and report how steady it is."""
    if camera is None:
        record("marker", SKIP, "no camera")
        return

    try:
        from adapters.detection.aruco import ArUco
        aruco = ArUco(marker_length_mm=length_mm)
    except Exception as exc:
        record("marker", FAIL, str(exc))
        return

    ratios: List[float] = []
    seen_ids: List[int] = []
    for _ in range(MARKER_FRAMES):
        frame = camera.read()
        if frame is None or frame.image is None:
            continue
        corners, ids = aruco.detect(frame.image)
        if ids is None or len(corners) == 0:
            continue
        seen_ids = [int(v) for v in ids.flatten()]
        ratios.append(aruco.pixel_mm_ratio(corners[0]))

    if not ratios:
        record("marker detected", FAIL,
               "not seen in any frame - check it is in view, lit evenly, "
               "in focus and free of glare")
        return

    record("marker detected", PASS,
           f"ids {seen_ids} in {len(ratios)}/{MARKER_FRAMES} frames")

    mean = statistics.mean(ratios)
    spread = statistics.pstdev(ratios) if len(ratios) > 4 else 0.0
    detail = f"{mean:.3f} px/mm, jitter {spread:.4f}"

    frame = camera.read()
    if frame is not None and frame.image is not None and mean > 0:
        height, width = frame.image.shape[:2]
        record("field of view", PASS,
               f"{width / mean:.0f} x {height / mean:.0f} mm "
               f"({1000.0 / mean:.0f} um per pixel)")

    if len(ratios) < MARKER_FRAMES:
        record("marker steady", FAIL, detail + " - dropped frames, detection is marginal")
    elif spread <= STABLE_PX_PER_MM:
        record("marker steady", PASS, detail)
    else:
        record("marker steady", FAIL,
               detail + f" - above {STABLE_PX_PER_MM} px/mm. Fix focus, "
               "lighting and glare before trusting any coordinate")


# --- entry point -----------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight check for the INA700 station")
    parser.add_argument("--length", type=float, default=100.0,
                        help="marker edge in mm; 0 skips the marker check")
    parser.add_argument("--no-camera", action="store_true",
                        help="skip everything that needs the camera")
    args = parser.parse_args()

    print("INA700 pre-flight\n")

    check_python()
    check_opencv()
    check_package("numpy", "numpy", "numpy")
    check_package("pyyaml", "yaml", "PyYAML")
    check_package("pillow", "PIL", "pillow")
    check_package("tkinter", "tkinter", "python3-tk (apt) or reinstall Python with tcl/tk")

    check_config()
    check_slot_angles()

    camera = None if args.no_camera else check_camera(grab=True)

    check_lighting(camera)

    if args.length and args.length > 0:
        check_marker(camera, args.length)
    else:
        record("marker", SKIP, "marker check disabled (--length 0)")

    if camera is not None:
        camera.close()

    failures = [name for name, status, _ in results if status == FAIL]
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
