"""Console and file logging.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(level: str = "INFO", log_file: str | None = None,
                      console_level: str | None = None) -> None:
    """Set up readable logging with the thread name included.

    `console_level` lets the terminal be quieter than the file. The console
    view is a prompt the operator types into, and a 10 fps pipeline logging at
    INFO writes over what they are halfway through typing - so on the Pi the
    terminal carries warnings only while logs/ina700.log keeps everything.
    """
    numeric = getattr(logging, level.upper(), logging.INFO)
    console_numeric = (getattr(logging, console_level.upper(), numeric)
                       if console_level else numeric)

    stream = logging.StreamHandler()
    stream.setLevel(console_numeric)
    handlers: list[logging.Handler] = [stream]

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(numeric)
        handlers.append(file_handler)

    logging.basicConfig(
        # The root has to pass whatever the most permissive handler wants,
        # or that handler never sees the record to filter it.
        level=min(numeric, console_numeric),
        format="%(asctime)s %(levelname)-7s [%(threadName)-16s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )
