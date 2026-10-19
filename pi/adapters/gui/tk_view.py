"""Operator window: detections, timing, and the cycle controls.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Sequence

from domain.enums import Colour, Shape
from domain.models import PickRequest, StateSnapshot
from ports.interfaces import View

log = logging.getLogger(__name__)

ANY = "Any"


class TkView(View):
    """A small control panel: live detections, timing, and a Start Cycle button."""

    def __init__(
        self,
        allowed_shapes: Sequence[Shape],
        on_cycle_requested: Callable[[PickRequest], None],
        on_close: Callable[[], None],
        snapshot_provider: Callable[[], StateSnapshot],
        refresh_ms: int = 100,
        budget_ms: float = 3000.0,
        preview_max_width: int = 1000,
        has_stopped: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._allowed_shapes = list(allowed_shapes)
        self._on_cycle_requested = on_cycle_requested
        self._on_close = on_close
        self._snapshot_provider = snapshot_provider
        self._refresh_ms = refresh_ms
        # Rescaling a five megapixel frame is the window's whole cost, and on
        # the Pi it competes with the model for the same four cores. Past
        # about this width the operator learns nothing more from a bigger
        # picture, so it is the first thing to lower when the Pi is busy.
        self._preview_max_width = preview_max_width
        self._budget_ms = budget_ms
        # A worker that dies stops the whole application. Without this the
        # window stays up looking healthy and every cycle silently fails.
        self._has_stopped = has_stopped or (lambda: False)
        self._reported_stop = False
        # Tk drops an image the moment nothing references it, so the current
        # one is held here. `_shown_sequence` avoids rescaling an unchanged frame.
        self._photo = None
        self._shown_sequence = -1
        self._preview_width = -1
        # What is currently on screen, so an unchanged frame costs nothing.
        self._timing_text = None
        self._status_text = None
        self._ticks = 0

        self._root = tk.Tk()
        self._root.title("INA700 - AI Pick and Place")
        self._maximise()
        self._root.protocol("WM_DELETE_WINDOW", self._handle_close)

        self._build_widgets()

    # --- construction ------------------------------------------------------

    def _maximise(self) -> None:
        """Fill the screen, whatever window manager is underneath.

        A fixed 1180x640 wasted most of a station monitor and cropped the
        preview on a small one. The ways to maximise differ by platform and
        several of them raise rather than degrade, so each is tried in turn
        and sizing to the screen is the fallback that always works.
        """
        for attempt in (lambda: self._root.state("zoomed"),                  # Windows
                        lambda: self._root.attributes("-zoomed", True)):     # X11
            try:
                attempt()
                return
            except Exception:
                continue
        width = self._root.winfo_screenwidth()
        height = self._root.winfo_screenheight()
        self._root.geometry(f"{width}x{height - 60}+0+0")

    def _build_widgets(self) -> None:
        """Lay out the control row, the live view and the status bar."""
        controls = ttk.Frame(self._root, padding=10)
        controls.pack(fill="x")

        ttk.Label(controls, text="Shape:").grid(row=0, column=0, padx=(0, 4))
        self._shape_var = tk.StringVar(value=ANY)
        ttk.Combobox(
            controls, textvariable=self._shape_var, state="readonly", width=12,
            values=[ANY] + [s.value for s in self._allowed_shapes],
        ).grid(row=0, column=1, padx=(0, 12))

        ttk.Label(controls, text="Colour:").grid(row=0, column=2, padx=(0, 4))
        self._colour_var = tk.StringVar(value=ANY)
        ttk.Combobox(
            controls, textvariable=self._colour_var, state="readonly", width=10,
            # Derived from the enum: adding a colour must not mean editing the
            # view. UNKNOWN is not offered - it is an answer, not a request.
            values=[ANY] + [c.value for c in Colour if c is not Colour.UNKNOWN],
        ).grid(row=0, column=3, padx=(0, 12))

        # "Send" rather than "Start": this button only chooses the object and
        # hands the position to the robot. Nothing moves until the yellow
        # button on the cell is pressed, and a button labelled Start promises
        # otherwise.
        self._cycle_button = ttk.Button(
            controls, text="Send pick to robot", command=self._handle_cycle_click
        )
        self._cycle_button.grid(row=0, column=4, padx=(0, 12))

        self._timing_label = ttk.Label(controls, text="inference: - ms")
        self._timing_label.grid(row=0, column=5)

        # The live view fills the window: the overlay already carries the
        # pose, and the status bar names the object being picked.
        body = ttk.Frame(self._root)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self._preview = ttk.Label(body, text="waiting for the first frame",
                                  anchor="center", relief="sunken", width=40)
        self._preview.pack(fill="both", expand=True)

        self._status_label = ttk.Label(self._root, text="starting up",
                                       relief="sunken", anchor="w", padding=4)
        self._status_label.pack(fill="x", side="bottom")

    # --- events ------------------------------------------------------------

    def _handle_cycle_click(self) -> None:
        """Turn the combobox selections into a PickRequest for the controller."""
        shape_name = self._shape_var.get()
        colour_name = self._colour_var.get()
        request = PickRequest(
            shape=None if shape_name == ANY else Shape.from_name(shape_name),
            colour=None if colour_name == ANY else Colour.from_name(colour_name),
        )
        self._on_cycle_requested(request)

    def _handle_close(self) -> None:
        """Ask the application to stop, then tear the window down."""
        self._on_close()
        self._root.destroy()

    # --- View interface ----------------------------------------------------

    PREVIEW_WIDTH = 640          # fallback only, before the window is mapped
    PREVIEW_MIN_WIDTH = 320      # below this the boxes are unreadable anyway
    # Fallback when no width is configured; gui.preview_max_width overrides it.
    PREVIEW_MAX_WIDTH = 1000
    BOX_COLOUR = (0, 200, 255)   # BGR: amber, readable on both paper and table

    def _render_preview(self, preview) -> None:
        """Draw the newest frame with a box round each detection.

        Shape, colour and confidence are drawn; the millimetre values live in
        the table, and repeating them over the image makes both harder to read.
        Colour belongs here rather than only in the table: seeing the name on
        the object itself is what catches a misread, which reading it off a row
        and matching it back to a box does not.
        """
        if preview is None or preview.image is None:
            return
        if (preview.sequence == self._shown_sequence
                and self._preview.winfo_width() == self._preview_width):
            return                          # same frame, same size: nothing to do
        self._preview_width = self._preview.winfo_width()

        import cv2
        from PIL import Image, ImageTk

        # Shrink FIRST, then draw on the small image. Copying the full frame
        # to draw on it costs 15 MB and a rectangle drawn at 2448 px wide is
        # thrown away by the resize anyway.
        height, width = preview.image.shape[:2]
        available_w = min(self._preview_max_width,
                          max(self.PREVIEW_MIN_WIDTH, self._preview.winfo_width()))
        available_h = max(self.PREVIEW_MIN_WIDTH, self._preview.winfo_height())
        if self._preview.winfo_width() <= 1:              # not yet mapped
            available_w, available_h = self.PREVIEW_WIDTH, self.PREVIEW_WIDTH
        scale = min(available_w / float(width), available_h / float(height))

        small = cv2.resize(preview.image, (max(1, int(width * scale)),
                                           max(1, int(height * scale))),
                           interpolation=cv2.INTER_AREA)

        for detection in preview.detections:
            box = detection.box
            if box is None:
                continue
            top_left = (int(box.u_min * scale), int(box.v_min * scale))
            bottom_right = (int(box.u_max * scale), int(box.v_max * scale))
            cv2.rectangle(small, top_left, bottom_right, self.BOX_COLOUR, 2)
            self._draw_pose(small, detection, scale)
            label = (f"{detection.shape.value.lower()} "
                     f"{detection.colour.value.lower()} "
                     f"{detection.confidence:.2f}")
            cv2.putText(small, label,
                        (top_left[0], max(22, top_left[1] - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.BOX_COLOUR, 1)

        self._photo = ImageTk.PhotoImage(
            Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)))
        self._preview.config(image=self._photo, text="")
        self._shown_sequence = preview.sequence

    def render(self, snapshot: StateSnapshot) -> None:
        """Redraw whatever has changed, and nothing that has not.

        This runs ten times a second. Every widget touched here is work the Tk
        main thread does instead of staying responsive, so each part is guarded
        by what it actually displays.
        """
        self._set_text(self._timing_label, "_timing_text",
                       f"inference: {snapshot.inference_ms:.0f} ms"
                       + ("" if snapshot.inference_ms <= self._budget_ms
                          else "  OVER BUDGET"))
        self._set_text(self._status_label, "_status_text",
                       f"[{'connected' if snapshot.connected else 'no robot'}] "
                       f"cycle {snapshot.cycle_index} - {snapshot.status_text}")

        try:
            self._render_preview(snapshot.preview)
        except Exception as exc:
            # A preview failure must never stop the status line being shown -
            # it is what the operator needs when the picture is the thing
            # that is broken.
            log.debug("Preview failed: %s", exc)

    def _set_text(self, widget, cache_name: str, text: str) -> None:
        """Configure a label only when its text has actually changed."""
        if getattr(self, cache_name, None) != text:
            widget.config(text=text)
            setattr(self, cache_name, text)




    CENTRE_COLOUR = (139, 0, 0)   # BGR: dark blue, visible on paper and table
    ANGLE_COLOUR = (60, 220, 60)      # BGR: green, distinct from the box

    def _draw_pose(self, canvas, detection, scale: float) -> None:
        """Mark where the cup will land, and which way the object is turned.

        A box says an object is there; it says nothing about the two numbers
        the robot actually acts on. Drawn here, a centre that has drifted off
        the object or an angle pointing the wrong way is obvious at a glance,
        which reading 156.5 in a table never is.
        """
        import cv2
        import math

        centre = (int(detection.centre.u * scale), int(detection.centre.v * scale))
        cv2.drawMarker(canvas, centre, self.CENTRE_COLOUR,
                   cv2.MARKER_CROSS, markerSize=11, thickness=2)  # type: ignore[arg-type]

        if detection.shape.is_rotationally_free:
            return          # a circle has no direction to draw

        # One ray per symmetry axis: five for a star, four for a square. All of
        # them are equally valid answers, and showing them makes the symmetry
        # visible instead of implying a single arbitrary heading.
        box = detection.box
        reach = 0.45 * min(box.width, box.height) * scale if box else 20.0
        period = detection.shape.symmetry_period_deg
        arms = detection.shape.symmetry_order or 1
        for index in range(arms):
            angle = math.radians(detection.angle_deg + index * period)
            tip = (int(centre[0] + reach * math.cos(angle)),
                   int(centre[1] + reach * math.sin(angle)))
            cv2.line(canvas, centre, tip, self.ANGLE_COLOUR, 2)

    def _tick(self) -> None:
        """Timer callback: pull a snapshot and reschedule."""
        self._ticks += 1
        if self._has_stopped() and not self._reported_stop:
            self._report_stopped()
        try:
            self.render(self._snapshot_provider())
        except Exception as exc:
            log.exception("GUI refresh failed: %s", exc)
        self._root.after(self._refresh_ms, self._tick)

    def _report_stopped(self) -> None:
        """Say so plainly, once, and stop offering cycles that cannot run."""
        self._reported_stop = True
        self._cycle_button.config(state="disabled")
        self._status_label.config(
            text="STOPPED - a worker thread died. See the log; the camera or "
                 "the robot connection is the usual cause. Restart after fixing it.")
        log.error("A worker thread has stopped; the GUI can no longer run cycles")

    def run(self) -> None:
        """Enter the Tk main loop. Blocks until the window closes."""
        self._root.after(self._refresh_ms, self._tick)
        self._root.mainloop()
