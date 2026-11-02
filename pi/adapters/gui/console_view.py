"""A terminal operator interface, for running with no display.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, List, Optional, Sequence, Tuple

from adapters.gui.formatting import angle_confidence_text
from domain.enums import Colour, Shape
from domain.models import PickRequest, StateSnapshot
from ports.interfaces import View

log = logging.getLogger(__name__)

QUIT_WORDS = ("quit", "exit", "q")
HELP_WORDS = ("help", "?")
STATUS_WORDS = ("status", "s", "")
ANY = "any"


def parse_request(text: str, allowed: Sequence[Shape]) -> Tuple[Optional[PickRequest], str]:
    """Turn a typed line into a PickRequest, or explain why it is not one.

    Order does not matter and either part may be left out, so all of these
    work: "circle red", "red circle", "circle", "red". A bare shape means any
    colour; a bare colour means any of the configured shapes.

    Returns (request, message). Exactly one of them is meaningful.
    """
    words = [w for w in text.strip().lower().split() if w]
    if not words:
        return None, ""

    shape: Optional[Shape] = None
    colour: Optional[Colour] = None
    unknown: List[str] = []

    for word in words:
        if word == ANY:
            continue
        try:
            candidate = Shape.from_name(word)
        except KeyError:
            candidate = None
        if candidate is not None:
            if candidate not in allowed:
                return None, (f"'{word}' is not one of the shapes this cell "
                              f"handles ({', '.join(s.value.lower() for s in allowed)})")
            shape = candidate
            continue
        as_colour = Colour.from_name(word)
        if as_colour is not Colour.UNKNOWN:
            colour = as_colour
            continue
        unknown.append(word)

    if unknown:
        return None, f"did not understand: {' '.join(unknown)}   (try 'help')"
    if shape is None and colour is None:
        return None, "nothing to pick - name a shape, a colour, or both"
    return PickRequest(shape=shape, colour=colour), ""


class ConsoleView(View):
    """Reads pick requests from stdin and prints what the system is doing."""

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
        # Seconds, because that is what time.sleep takes. Floored so a config
        # of 0 cannot turn the watcher into a busy loop on the Pi.
        self._poll_s = max(0.02, refresh_ms / 1000.0)
        self._budget_ms = budget_ms
        self._has_stopped = has_stopped or (lambda: False)
        self._last_status = ""
        self._stop = threading.Event()

    # --- View --------------------------------------------------------------

    def render(self, snapshot: StateSnapshot) -> None:
        """Print the status line only when it changes.

        A terminal is a log, not a canvas: repainting every tick would bury
        what the operator typed under identical lines.
        """
        status = getattr(snapshot, "status_text", "") or ""
        if status and status != self._last_status:
            print(f"    {status}", flush=True)
            self._last_status = status

    def run(self) -> None:
        """Own the main thread, reading commands until told to stop."""
        self._print_banner()
        watcher = threading.Thread(target=self._watch_status, daemon=True,
                                   name="console-status")
        watcher.start()

        try:
            while not self._stop.is_set():
                try:
                    line = input("pick> ")
                except (EOFError, KeyboardInterrupt):
                    print()
                    break

                word = line.strip().lower()
                if word in QUIT_WORDS:
                    break
                if word in HELP_WORDS:
                    self._print_help()
                    continue
                if word in STATUS_WORDS:
                    self._print_scene()
                    continue

                request, problem = parse_request(line, self._allowed_shapes)
                if request is None:
                    if problem:
                        print(f"    {problem}", flush=True)
                    continue

                print(f"    requesting {self._describe(request)}", flush=True)
                self._on_cycle_requested(request)
        finally:
            self._stop.set()
            self._on_close()

    # --- output ------------------------------------------------------------

    def _print_banner(self) -> None:
        shapes = ", ".join(s.value.lower() for s in self._allowed_shapes)
        print("\n" + "=" * 62)
        print("  INA700 - type what to pick, then press the yellow button")
        print("=" * 62)
        print(f"  shapes: {shapes}")
        print("  e.g.  circle red   |   star   |   blue")
        print("  also: status (what the camera sees), help, quit\n", flush=True)

    def _print_help(self) -> None:
        shapes = ", ".join(s.value.lower() for s in self._allowed_shapes)
        colours = ", ".join(c.value.lower() for c in Colour if c is not Colour.UNKNOWN)
        print(f"    shapes  : {shapes}")
        print(f"    colours : {colours}")
        print("    shape and colour in either order; leave one out for 'any'")
        print("    status  : list what the camera sees right now")
        print("    quit    : stop the server\n", flush=True)

    def _print_scene(self) -> None:
        """What the camera sees, in the same terms the GUI table shows."""
        snapshot = self._snapshot_provider()
        objects = list(getattr(snapshot, "detections", ()) or ())
        elapsed = getattr(snapshot, "inference_ms", 0.0) or 0.0

        if not objects:
            print("    nothing on the sheet\n", flush=True)
            return

        print(f"\n    {'shape':<8}{'colour':<9}{'conf':>6}{'fit':>8}"
              f"{'x mm':>9}{'y mm':>9}{'rz deg':>9}")
        print("    " + "-" * 58)
        for o in objects:
            print(f"    {o.shape.value.lower():<8}{o.colour.value.lower():<9}"
                  f"{o.detection.confidence:>6.2f}{angle_confidence_text(o):>8}"
                  f"{o.pose.x:>9.1f}{o.pose.y:>9.1f}{o.pose.rz:>9.1f}")
        over = "  OVER BUDGET" if elapsed > self._budget_ms else ""
        print(f"    inference {elapsed:.0f} ms{over}\n", flush=True)

    def _describe(self, request: PickRequest) -> str:
        shape = request.shape.value.lower() if request.shape else "any shape"
        colour = request.colour.value.lower() if request.colour else "any colour"
        return f"{shape}, {colour}"

    def _watch_status(self) -> None:
        """Poll the shared state so progress appears between prompts.

        A background thread rather than the main one, because the main thread
        is blocked in input() waiting for the operator.

        Waits on the stop event rather than sleeping, so shutdown is immediate
        instead of up to one poll period late.
        """
        while not self._stop.is_set():
            try:
                self.render(self._snapshot_provider())
                if self._has_stopped():
                    print("\n    A worker thread has stopped - the system is no "
                          "longer running. Press Enter to exit.", flush=True)
                    self._stop.set()
                    return
            except Exception as exc:            # never kill the UI thread
                log.debug("status poll failed: %s", exc)
            self._stop.wait(self._poll_s)
