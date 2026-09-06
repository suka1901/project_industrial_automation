"""TCP server the robot connects to as a client.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Optional

from ports.interfaces import RobotTransport

log = logging.getLogger(__name__)

from adapters.comms.message_codec import TERMINATOR


class TcpServerTransport(RobotTransport):
    """A single-client TCP server speaking the terminated-string protocol."""

    def __init__(
        self,
        host: str = "192.168.125.201",
        port: int = 5000,
        accept_timeout_s: float = 60.0,
        encoding: str = "utf-8",
    ) -> None:
        self._host = host
        self._port = port
        self._accept_timeout_s = accept_timeout_s
        self._encoding = encoding

        self._server: Optional[socket.socket] = None
        self._client: Optional[socket.socket] = None
        self._client_address = None
        self._buffer = ""
        self._lock = threading.Lock()  # one message at a time on the wire

    # --- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Bind, listen and wait for the robot to connect."""
        # A previous attempt may have timed out with the socket still bound;
        # rebinding without closing it fails with "address already in use".
        self.close()

        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allows an immediate restart after a crash instead of "address in use".
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self._host, self._port))
        self._server.listen(1)
        self._server.settimeout(self._accept_timeout_s)

        log.info("Waiting for the robot to connect on %s:%d", self._host, self._port)
        self._client, self._client_address = self._server.accept()
        # Send small control messages immediately rather than coalescing them.
        self._client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        log.info("Robot connected from %s", self._client_address)

    def close(self) -> None:
        """Close both sockets, tolerating a partially started server."""
        for sock in (self._client, self._server):
            if sock is not None:
                try:
                    sock.close()
                except OSError as exc:
                    log.debug("Error closing socket: %s", exc)
        self._client = None
        self._server = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    # --- traffic -----------------------------------------------------------

    def send(self, message: str) -> None:
        """Send one already-encoded protocol string."""
        if self._client is None:
            raise ConnectionError("Robot is not connected")
        with self._lock:
            self._client.sendall(message.encode(self._encoding))
        log.debug("--> %s", message)

    def receive(self, timeout_s: float) -> Optional[str]:
        """Return one complete '#'-terminated message, or None on timeout."""
        if self._client is None:
            raise ConnectionError("Robot is not connected")

        self._client.settimeout(timeout_s)
        while TERMINATOR not in self._buffer:
            try:
                chunk = self._client.recv(1024)
            except socket.timeout:
                return None
            if not chunk:
                log.warning("Robot closed the connection")
                self._client = None
                return None
            # latin-1 never raises on unexpected bytes, which the controller
            # occasionally sends; the protocol itself is pure ASCII.
            self._buffer += chunk.decode("latin-1")

        message, _, self._buffer = self._buffer.partition(TERMINATOR)
        log.debug("<-- %s", message)
        return message
