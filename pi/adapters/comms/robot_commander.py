"""Sends one pick command and waits for the robot's reply.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging

from domain.enums import CycleOutcome
from domain.models import DetectedObject
from adapters.comms.message_codec import MessageCodec
from ports.interfaces import RobotTransport

log = logging.getLogger(__name__)


class RobotCommander:
    """Callable that asks the robot to pick one object and reports the outcome."""

    def __init__(
        self,
        transport: RobotTransport,
        codec: MessageCodec,
        reply_timeout_s: float = 60.0,
    ) -> None:
        self._transport = transport
        self._codec = codec
        self._reply_timeout_s = reply_timeout_s

    def __call__(self, target: DetectedObject) -> CycleOutcome:
        """Send the pick command and block until the robot answers."""
        if not self._transport.is_connected:
            log.error("Cannot command the robot - not connected")
            return CycleOutcome.FAILED

        try:
            message = self._codec.encode_pick(target)
        except Exception as exc:
            log.exception("Failed to build the pick command: %s", exc)
            return CycleOutcome.FAILED

        # The exact bytes, not a summary. 
        log.warning("-> %s", message)

        try:
            self._transport.send(message)
        except Exception as exc:
            log.exception("Failed to send pick command: %s", exc)
            return CycleOutcome.FAILED

        # The robot answers once, the motion has finished.
        raw = self._transport.receive(self._reply_timeout_s)
        log.warning("<- %s", raw if raw is not None else "(no reply - timed out)")
        return self._codec.decode_reply(raw)
