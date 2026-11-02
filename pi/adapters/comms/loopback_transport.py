"""A fake robot, for testing without robot hardware.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ports.interfaces import RobotTransport

log = logging.getLogger(__name__)


class LoopbackTransport(RobotTransport):
    """Answers every pick command with a scripted reply."""

    def __init__(self, replies: Optional[List[str]] = None,
                 default_reply: str = "DONE: ok#") -> None:
        # Queue specific replies to simulate failures and exercise the retries.
        self._replies = list(replies or [])
        self._default_reply = default_reply
        self._connected = False
        self.sent: List[str] = []  # inspected by the tests

    def start(self) -> None:
        self._connected = True
        log.info("Loopback transport started (no real robot)")

    def close(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def send(self, message: str) -> None:
        self.sent.append(message)
        log.debug("(loopback) --> %s", message)

    def receive(self, timeout_s: float) -> Optional[str]:
        reply = self._replies.pop(0) if self._replies else self._default_reply
        log.debug("(loopback) <-- %s", reply)
        return reply
