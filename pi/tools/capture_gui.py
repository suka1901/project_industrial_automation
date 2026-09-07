"""Capture training photos: live preview, one button, one photo.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))


from domain.enums import Shape  # noqa: E402
from domain.models import Frame  # noqa: E402
from infrastructure.config_loader import load_config  # noqa: E402
from infrastructure.logging_setup import configure_logging  # noqa: E402
from ports.interfaces import FrameSource  # noqa: E402
from tools.capture_session import MIXED, CaptureSession  # noqa: E402

log = logging.getLogger("capture")

PREVIEW_WIDTH = 720          # display size only; saved images stay full size
REFRESH_MS = 40              # about 25 fps in the UI


class LatestFrame:
    """A one-slot mailbox: the grabber writes, the UI reads the newest."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Optional[Frame] = None

    def put(self, frame: Frame) -> None:
        with self._lock:
            self._frame = frame

    def get(self) -> Optional[Frame]:
        with self._lock:
            return self._frame


class GrabberThread(threading.Thread):
    """Pulls frames off the camera so the UI never blocks on the sensor."""

    def __init__(self, source: FrameSource, mailbox: LatestFrame,
                 shutdown: threading.Event) -> None:
        super().__init__(name="grabber", daemon=True)
        self._source = source
        self._mailbox = mailbox
        self._shutdown = shutdown

    def run(self) -> None:
        try:
            self._source.open()
            while not self._shutdown.is_set():
                frame = self._source.read()
                if frame is None:
                    self._shutdown.wait(0.02)
                    continue
                self._mailbox.put(frame)
        except Exception as exc:
            log.exception("Camera thread stopped: %s", exc)
            self._shutdown.set()
        finally:
            self._source.close()


class CaptureWindow:
    """The operator window: preview, scene picker, counts, Capture button."""

    def __init__(self, session: CaptureSession, mailbox: LatestFrame,
                 shutdown: threading.Event, aruco: Any,
                 marker_id: Optional[int]) -> None:
        self._session = session
        self._mailbox = mailbox
        self._shutdown = shutdown
        self._aruco = aruco
        self._marker_id = marker_id

        self._photo = None          # keeps a reference so Tk does not bin it
        self._marker_seen = False
        self._last_saved = ""

        self._root = tk.Tk()
        self._root.title("INA700 - dataset capture")
        self._root.protocol("WM_DELETE_WINDOW", self._handle_close)
        self._root.bind("<space>", lambda _event: self._handle_capture())

        self._build_widgets()

    # --- construction ------------------------------------------------------

    def _build_widgets(self) -> None:
        controls = ttk.Frame(self._root, padding=10)
        controls.pack(side="left", fill="y")

        ttk.Label(controls, text="Scene", font=("", 20, "bold")).pack(anchor="w")

        categories = self._session.categories
        self._category_var = tk.StringVar(value=categories[0])
        for category in categories:
            ttk.Radiobutton(controls, text=category.title(),
                            value=category, variable=self._category_var,
                            command=self._refresh_counts).pack(anchor="w")

        ttk.Separator(controls, orient="horizontal").pack(fill="x", pady=10)

        self._require_marker = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Require marker",
                        variable=self._require_marker).pack(anchor="w")

        ttk.Button(controls, text="Capture  (space)",
                   command=self._handle_capture).pack(fill="x", pady=(12, 6))

        ttk.Separator(controls, orient="horizontal").pack(fill="x", pady=10)

        ttk.Label(controls, text="Photos so far", font=("", 10, "bold")).pack(anchor="w")
        self._counts_label = ttk.Label(controls, text="", justify="left")
        self._counts_label.pack(anchor="w", pady=(2, 0))

        self._preview = ttk.Label(self._root)
        self._preview.pack(side="right", padx=10, pady=10)

        self._status = ttk.Label(self._root, text="starting camera",
                                 relief="sunken", anchor="w", padding=4)
        self._status.pack(side="bottom", fill="x")

        self._refresh_counts()

    # --- events ------------------------------------------------------------

    def _selected_category(self) -> str:
        return self._category_var.get()

    def _handle_capture(self) -> None:
        """Save the current full-resolution frame under the selected scene."""
        frame = self._mailbox.get()
        if frame is None or frame.image is None:
            self._status.config(text="no image from the camera yet")
            return

        if self._require_marker.get() and not self._marker_seen:
            self._status.config(
                text="NOT SAVED - the marker is not visible (untick "
                     "'Require marker' to save anyway)")
            return

        path = self._session.save(frame.image, self._selected_category())
        if path is None:
            self._status.config(text="could not write the file - check the folder")
            return

        self._last_saved = path.name
        self._refresh_counts()

    def _handle_close(self) -> None:
        self._shutdown.set()
        self._root.destroy()

    # --- rendering ---------------------------------------------------------

    def _refresh_counts(self) -> None:
        lines = [f"{category.title():<10} {count}"
                 for category, count in self._session.counts().items()]
        self._counts_label.config(text="\n".join(lines))

    def _render_preview(self, image) -> None:
        """Draw markers, shrink for display, and push into the Tk label."""
        import cv2
        from PIL import Image, ImageTk

        annotated = image.copy()

        self._marker_seen = False
        if self._aruco is not None:
            try:
                corners, ids = self._aruco.detect(annotated)
                chosen = self._aruco.corners_for_id(corners, ids, self._marker_id)
                if chosen is not None:
                    self._aruco.draw(annotated, corners, ids)
                    self._marker_seen = True
            except Exception as exc:
                log.debug("Marker detection failed: %s", exc)

        # Shrink for display only. The saved file is always the full frame.
        height, width = annotated.shape[:2]
        scale = PREVIEW_WIDTH / float(width)
        preview = cv2.resize(annotated, (PREVIEW_WIDTH, int(height * scale)))

        rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
        self._photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self._preview.config(image=self._photo)

    def _tick(self) -> None:
        frame = self._mailbox.get()
        if frame is not None and frame.image is not None:
            try:
                self._render_preview(frame.image)
            except Exception as exc:
                log.exception("Preview failed: %s", exc)

        marker_text = "marker OK" if self._marker_seen else "MARKER NOT VISIBLE"
        saved_text = f"   last saved: {self._last_saved}" if self._last_saved else ""
        self._status.config(text=f"{marker_text}{saved_text}")

        self._root.after(REFRESH_MS, self._tick)

    def run(self) -> None:
        self._root.after(REFRESH_MS, self._tick)
        self._root.mainloop()


def build_source(kind: str, path: Optional[str]) -> FrameSource:
    """Pick a frame source without dragging in the whole application container."""
    if kind == "basler":
        from adapters.camera.camera import Camera
        return Camera()
    if kind == "file":
        from adapters.camera.file_source import FileFrameSource
        return FileFrameSource(directory=path or str(BASE_DIR / "../model/dataset"))
    from adapters.camera.synthetic_source import SyntheticFrameSource
    return SyntheticFrameSource()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture training photos")
    parser.add_argument("--source", default="basler",
                        choices=("basler", "file", "synthetic"))
    parser.add_argument("--path", default=None, help="image folder for --source file")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--out", default=None,
                        help="dataset root (default model/dataset/raw)")
    args = parser.parse_args()

    configure_logging(level="INFO", log_file=None)
    config = load_config(BASE_DIR / args.config)

    # Every shape, not just the three assigned ones: the two you must ignore
    # still belong in the photos as unlabelled hard negatives. MIXED holds the
    # scenes with several shapes at once, which is what the robot actually sees.
    categories = [shape.value.lower() for shape in Shape] + [MIXED]

    root = Path(args.out) if args.out else (BASE_DIR / ".." / "model" / "dataset" / "raw")
    session = CaptureSession(root.resolve(), categories)
    session.prepare()

    marker_config = config.get("aruco", {})
    try:
        from adapters.detection.aruco import ArUco
        aruco = ArUco(
            dictionary_name=marker_config.get("dictionary", "DICT_5X5_100"),
            marker_length_mm=float(marker_config.get("marker_length_mm", 100.0)),
        )
    except Exception as exc:
        log.warning("ArUco unavailable, continuing without the overlay: %s", exc)
        aruco = None

    shutdown = threading.Event()
    mailbox = LatestFrame()
    grabber = GrabberThread(build_source(args.source, args.path), mailbox, shutdown)
    grabber.start()

    window = CaptureWindow(session, mailbox, shutdown, aruco,
                           marker_config.get("marker_id"))
    try:
        window.run()
    finally:
        shutdown.set()
        grabber.join(timeout=3.0)
        print(f"\nDataset now at {session.root}")
        for category, count in session.counts().items():
            print(f"  {category.title():<10} {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
