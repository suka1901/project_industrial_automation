"""Operator window: detections, timing, and the cycle controls.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Sequence

from adapters.gui.formatting import angle_confidence_text, untrusted_angle_warning
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
        place_confidence_gate: float = 0.10,
        has_stopped: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._allowed_shapes = list(allowed_shapes)
        self._on_cycle_requested = on_cycle_requested
        self._on_close = on_close
        self._snapshot_provider = snapshot_provider
        self._refresh_ms = refresh_ms
        self._budget_ms = budget_ms
        # Below this the angle is not trusted and the object is not picked.
        # Showing it explains why an object the camera clearly sees is skipped.
        self._place_gate = place_confidence_gate
        # A worker that dies stops the whole application. Without this the
        # window stays up looking healthy and every cycle silently fails.
        self._has_stopped = has_stopped or (lambda: False)
        self._reported_stop = False
        # Tk drops an image the moment nothing references it, so the current
        # one is held here. `_shown_sequence` avoids rescaling an unchanged frame.
        self._photo = None
        self._shown_sequence = -1
        # Drives the flashing warning. A static banner is easy to look past
        # when the operator is watching the robot rather than the screen.
        self._flash_on = False
        self._ticks = 0

        self._root = tk.Tk()
        self._root.title("INA700 - AI Pick and Place")
        self._root.geometry("1180x640")
        self._root.protocol("WM_DELETE_WINDOW", self._handle_close)

        self._build_widgets()

    # --- construction ------------------------------------------------------

    def _build_widgets(self) -> None:
        """Lay out the control row, the detection table and the status bar."""
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

        self._cycle_button = ttk.Button(
            controls, text="Start cycle", command=self._handle_cycle_click
        )
        self._cycle_button.grid(row=0, column=4, padx=(0, 12))

        self._timing_label = ttk.Label(controls, text="inference: - ms")
        self._timing_label.grid(row=0, column=5)

        # Live view on the left, numbers on the right.
        body = ttk.Frame(self._root)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self._preview = ttk.Label(body, text="waiting for the first frame",
                                  anchor="center", relief="sunken", width=40)
        self._preview.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Detection table: this is the "display position and orientation" part.
        columns = ("shape", "colour", "conf", "angle_conf", "x", "y", "rz")
        self._tree = ttk.Treeview(body, columns=columns,
                                  show="headings", height=10)
        headings = {
            "shape": "Shape", "colour": "Colour", "conf": "Conf.",
            "angle_conf": "Angle |Z|",
            "x": "X (mm)", "y": "Y (mm)", "rz": "Rz (deg)",
        }
        for column in columns:
            self._tree.heading(column, text=headings[column])
            # The angle column carries a value plus a warning word, so it
            # needs room; a truncated warning is worse than none.
            width = 150 if column == "angle_conf" else 86
            self._tree.column(column, width=width, anchor="center")
        self._tree.pack(side="right", fill="y")

        # A banner rather than a line in the status bar: an object placed
        # unrotated is the one failure the operator must not read past.
        self._warning_label = tk.Label(self._root, text="", anchor="w",
                                       padx=8, pady=6, fg="#7A1F1F",
                                       bg="#FFE08A", font=("", 11, "bold"))

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

    PREVIEW_WIDTH = 640          # display only; nothing measures this image
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
        if preview.sequence == self._shown_sequence:
            return                                   # nothing new to show

        import cv2
        from PIL import Image, ImageTk

        image = preview.image.copy()
        for detection in preview.detections:
            box = detection.box
            if box is None:
                continue
            top_left = (int(box.u_min), int(box.v_min))
            bottom_right = (int(box.u_max), int(box.v_max))
            cv2.rectangle(image, top_left, bottom_right, self.BOX_COLOUR, 3)
            label = (f"{detection.shape.value.lower()} "
                     f"{detection.colour.value.lower()} "
                     f"{detection.confidence:.2f}")
            cv2.putText(image, label,
                        (top_left[0], max(18, top_left[1] - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.BOX_COLOUR, 2)

        height, width = image.shape[:2]
        scale = self.PREVIEW_WIDTH / float(width)
        small = cv2.resize(image, (self.PREVIEW_WIDTH, int(height * scale)),
                           interpolation=cv2.INTER_AREA)

        self._photo = ImageTk.PhotoImage(
            Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)))
        self._preview.config(image=self._photo, text="")
        self._shown_sequence = preview.sequence

    def render(self, snapshot: StateSnapshot) -> None:
        """Redraw the preview, the table and the labels from one snapshot."""
        self._timing_label.config(
            text=f"inference: {snapshot.inference_ms:.0f} ms"
                 + ("" if snapshot.inference_ms <= self._budget_ms
                    else "  OVER BUDGET")
        )
        self._status_label.config(
            text=f"[{'connected' if snapshot.connected else 'no robot'}] "
                 f"cycle {snapshot.cycle_index} - {snapshot.status_text}"
        )

        try:
            self._render_preview(snapshot.preview)
        except Exception as exc:
            # A preview failure must never stop the numbers being shown.
            log.debug("Preview failed: %s", exc)

        self._show_warning(untrusted_angle_warning(snapshot.detections))

        self._tree.delete(*self._tree.get_children())
        for obj in snapshot.detections:
            self._tree.insert("", "end", values=(
                obj.shape.value,
                obj.colour.value,
                f"{obj.detection.confidence:.2f}",
                angle_confidence_text(obj, self._place_gate),
                f"{obj.pose.x:.1f}",
                f"{obj.pose.y:.1f}",
                f"{obj.pose.rz:.1f}",
            ))



    FLASH_EVERY_TICKS = 4        # about twice a second at the default refresh
    FLASH_COLOURS = (("#FFE08A", "#7A1F1F"),      # amber on dark red text
                     ("#C62828", "#FFFFFF"))      # red on white

    def _show_warning(self, text: str) -> None:
        """Show a flashing banner while something needs moving.

        Flashing rather than static: during a demo the operator is watching the
        robot, and this has to be caught before the cycle starts, not after the
        object has been placed unrotated.
        """
        if not text:
            if self._warning_label.winfo_ismapped():
                self._warning_label.pack_forget()
            return

        self._warning_label.config(text=text)
        if not self._warning_label.winfo_ismapped():
            self._warning_label.pack(fill="x", side="bottom",
                                     before=self._status_label)

        if self._ticks % self.FLASH_EVERY_TICKS == 0:
            self._flash_on = not self._flash_on
            background, foreground = self.FLASH_COLOURS[self._flash_on]
            self._warning_label.config(bg=background, fg=foreground)

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
