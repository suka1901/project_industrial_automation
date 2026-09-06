"""The server-to-robot wire protocol.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from typing import Optional

from domain.enums import CycleOutcome
from domain.models import DetectedObject

log = logging.getLogger(__name__)

MOVE_COMMAND = "move"
QUIT_COMMAND = "quit"
TERMINATOR = "#"
SEPARATOR = " "
RAPID_MAX_STRING = 80  # hard limit imposed by the robot controller


class ProtocolError(ValueError):
    """Raised when a message cannot be encoded or understood."""


class MessageCodec:
    """Encodes commands for the robot and decodes its replies."""

    # --- server -> robot ---------------------------------------------------

    def encode_pick(self, target: DetectedObject) -> str:
        """Build the move command for one object.

        Rz is the PLACING rotation, not the object's own angle. Colour is not
        sent: matching it is the server's job.
        """
        pose = target.pose
        message = SEPARATOR.join([
            MOVE_COMMAND,
            target.shape.value.lower(),
            f"{pose.x:.2f}",
            f"{pose.y:.2f}",
            f"{pose.rz:.1f}",
        ]) + TERMINATOR

        self._guard_length(message)
        return message

    def encode_quit(self) -> str:
        """Ask the robot to close the connection and stop."""
        return QUIT_COMMAND + TERMINATOR

    def _guard_length(self, message: str) -> None:
        """Fail loudly here rather than debug a truncated string on the robot."""
        if len(message) > RAPID_MAX_STRING:
            raise ProtocolError(
                f"Message is {len(message)} characters, over the RAPID limit of "
                f"{RAPID_MAX_STRING}: {message!r}"
            )

    # --- robot -> server ---------------------------------------------------

    def decode_reply(self, raw: Optional[str]) -> CycleOutcome:
        """Interpret one reply from the robot."""
        if raw is None:
            return CycleOutcome.TIMEOUT

        cleaned = raw.strip().strip(TERMINATOR).upper()
        if not cleaned:
            return CycleOutcome.TIMEOUT

        if cleaned.startswith("DONE"):
            return CycleOutcome.SUCCESS
        if cleaned.startswith("ERROR") or cleaned.startswith("FAILED"):
            return CycleOutcome.FAILED

        log.warning("Unrecognised reply from robot: %r", raw)
        return CycleOutcome.FAILED
