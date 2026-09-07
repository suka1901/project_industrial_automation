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
        has_stopped: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._allowed_shapes = list(allowed_shapes)
        self._on_cycle_requested = on_cycle_requested
        self._on_close = on_close
        self._snapshot_provider = snapshot_provider
        self._refresh_ms = refresh_ms
        self._budget_ms = budget_ms
        # A worker that dies stops the whole application. Without this the
        # window stays up looking healthy and every cycle silently fails.
        self._has_stopped = has_stopped or (lambda: False)
        self._reported_stop = False

        self._root = tk.Tk()
        self._root.title("INA700 - AI Pick and Place")
        self._root.geometry("760x460")
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

        # Detection table: this is the "display position and orientation" part.
        columns = ("shape", "colour", "conf", "x", "y", "rz")
        self._tree = ttk.Treeview(self._root, columns=columns,
                                  show="headings", height=10)
        headings = {
            "shape": "Shape", "colour": "Colour", "conf": "Conf.",
            "x": "X (mm)", "y": "Y (mm)", "rz": "Rz (deg)",
        }
        for column in columns:
            self._tree.heading(column, text=headings[column])
            self._tree.column(column, width=110, anchor="center")
        self._tree.pack(fill="both", expand=True, padx=10, pady=(0, 8))

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

    def render(self, snapshot: StateSnapshot) -> None:
        """Redraw the table and labels from an immutable snapshot."""
        self._timing_label.config(
            text=f"inference: {snapshot.inference_ms:.0f} ms"
                 + ("" if snapshot.inference_ms <= self._budget_ms
                    else "  OVER BUDGET")
        )
        self._status_label.config(
            text=f"[{'connected' if snapshot.connected else 'no robot'}] "
                 f"cycle {snapshot.cycle_index} - {snapshot.status_text}"
        )

        self._tree.delete(*self._tree.get_children())
        for obj in snapshot.detections:
            self._tree.insert("", "end", values=(
                obj.shape.value,
                obj.colour.value,
                f"{obj.detection.confidence:.2f}",
                f"{obj.pose.x:.1f}",
                f"{obj.pose.y:.1f}",
                f"{obj.pose.rz:.1f}",
            ))

    def _tick(self) -> None:
        """Timer callback: pull a snapshot and reschedule."""
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
