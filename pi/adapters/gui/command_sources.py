"""Ways of asking for a pick that are not the view itself.

Tk has to own the main thread, so the terminal prompt cannot also be a view -
it becomes a command SOURCE instead: a background thread that feeds the same
queue the views feed. That is what lets the window and the terminal both be
live on the Pi at once.

Two sources, one dispatch:

    terminal   type "circle red" in the window's own terminal
    pipe       echo "circle red" > /tmp/ina700.cmd, from any other terminal

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Callable, Optional, Sequence, TextIO

from domain.enums import Shape
from adapters.gui.console_view import QUIT_WORDS, parse_request

log = logging.getLogger(__name__)

# A writer closing gives the reader EOF, so the pipe is reopened for the next
# command. The wait keeps that from becoming a spin if the path is an ordinary
# file rather than a pipe.
REOPEN_WAIT_S = 0.2


def dispatch(text: str, allowed: Sequence[Shape],
             on_cycle_requested: Callable[[object], None], source: str) -> bool:
    """Parse one line and queue it. False if there was nothing to queue.

    Shared by both sources on purpose: a typo should be refused the same way
    and in the same words wherever it was typed.
    """
    text = text.strip()
    if not text:
        return False
    request, message = parse_request(text, allowed)
    if request is None:
        # A warning, so it reaches the terminal even when the terminal is
        # quietened - otherwise a typo sent down the pipe vanishes silently.
        log.warning("Ignored %r from %s: %s", text, source, message)
        return False
    log.info("Command from %s: %s", source, text)
    on_cycle_requested(request)
    return True


class TerminalCommandReader:
    """Reads commands from stdin while another view owns the screen."""

    def __init__(self, allowed_shapes: Sequence[Shape],
                 on_cycle_requested: Callable[[object], None],
                 on_close: Optional[Callable[[], None]] = None,
                 stream: Optional[TextIO] = None) -> None:
        self._allowed = list(allowed_shapes)
        self._on_cycle_requested = on_cycle_requested
        self._on_close = on_close
        self._stream = stream
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Begin reading. False when there is no terminal to read from."""
        stream = self._stream if self._stream is not None else sys.stdin
        if self._stream is None and not (stream and stream.isatty()):
            # Launched from a desktop icon or with stdin redirected: reading
            # would hit EOF at once and the thread would quietly disappear.
            log.warning("gui.terminal_input is on, but stdin is not a "
                        "terminal - typing is disabled; the pipe still works")
            return False
        self._thread = threading.Thread(target=self._read_forever, args=(stream,),
                                        daemon=True, name="terminal-commands")
        self._thread.start()
        shapes = ", ".join(s.value for s in self._allowed)
        # print, not log: operator-facing text, and the terminal may be
        # carrying warnings only.
        print(f'    type a shape and colour here, for example "circle red"\n'
              f'    shapes: {shapes}   |   "quit" closes the system',
              flush=True)
        return True

    def stop(self) -> None:
        """Stop reading. The thread is a daemon, so a blocked read cannot hang
        shutdown - there is no way to interrupt a pending stdin read."""
        self._stop.set()

    def _read_forever(self, stream: TextIO) -> None:
        for line in stream:
            if self._stop.is_set():
                return
            if line.strip().lower() in QUIT_WORDS:
                if self._on_close is not None:
                    self._on_close()
                return
            dispatch(line, self._allowed, self._on_cycle_requested, "the terminal")


class PipeCommandReader:
    """Turns lines written to a named pipe into pick requests.

    The pipe separates typing from output: the system keeps its own terminal
    and commands arrive from any other one. It works with either view.
    """

    def __init__(self, path: str, allowed_shapes: Sequence[Shape],
                 on_cycle_requested: Callable[[object], None]) -> None:
        self._path = str(path)
        self._allowed = list(allowed_shapes)
        self._on_cycle_requested = on_cycle_requested
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Create the pipe if needed and begin reading. False if unavailable."""
        if not self._ensure_pipe():
            return False
        self._thread = threading.Thread(target=self._read_forever, daemon=True,
                                        name="pipe-commands")
        self._thread.start()
        print(f'    commands also accepted from {self._path} - for example:\n'
              f'        echo "circle red" > {self._path}', flush=True)
        return True

    def stop(self) -> None:
        """Stop reading. Safe to call when start() returned False."""
        self._stop.set()
        self._nudge()

    # --- internals ---------------------------------------------------------

    def _ensure_pipe(self) -> bool:
        if os.path.exists(self._path):
            return True
        if not hasattr(os, "mkfifo"):
            log.warning("gui.command_pipe is set, but this platform has no "
                        "named pipes - ignoring %s", self._path)
            return False
        try:
            os.mkfifo(self._path, 0o666)  # pyright: ignore[reportAttributeAccessIssue]
        except OSError as exc:
            log.warning("Could not create the command pipe %s: %s", self._path, exc)
            return False
        return True

    def _nudge(self) -> None:
        """Unblock a reader waiting for a writer, so shutdown is not delayed."""
        try:
            handle = os.open(self._path, os.O_WRONLY | getattr(os, "O_NONBLOCK", 0))
            os.close(handle)
        except OSError:
            pass            # nobody reading, or not a pipe - nothing to unblock

    def _read_forever(self) -> None:
        while not self._stop.is_set():
            try:
                with open(self._path, "r", encoding="utf-8") as pipe:
                    for line in pipe:
                        if self._stop.is_set():
                            return
                        dispatch(line, self._allowed,
                                 self._on_cycle_requested, "the pipe")
            except OSError as exc:
                log.warning("Command pipe %s could not be read: %s",
                            self._path, exc)
            self._stop.wait(REOPEN_WAIT_S)
