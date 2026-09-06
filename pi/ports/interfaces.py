"""Abstract interfaces (ports) implemented by the adapters.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from domain.enums import Colour
from domain.models import (
    Detection,
    DetectedObject,
    Frame,
    OutlineMeasurement,
    PickRequest,
    PixelPoint,
    StateSnapshot,
)


class FrameSource(ABC):
    """Anything that can hand us images: a Basler camera, a webcam, a folder."""

    @abstractmethod
    def open(self) -> None:
        """Acquire the device. Safe to call once, before the first read."""

    @abstractmethod
    def read(self) -> Optional[Frame]:
        """Return the next frame, or None if no image is currently available."""

    @abstractmethod
    def close(self) -> None:
        """Release the device. Must be safe to call even if open() failed."""

    def __enter__(self) -> "FrameSource":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class ObjectDetector(ABC):
    """Finds and classifies objects in an image."""

    @abstractmethod
    def detect(self, frame: Frame) -> Sequence[Detection]:
        """Return every accepted object found in the frame."""

    @abstractmethod
    def warm_up(self) -> None:
        """Run a throwaway inference so the first real cycle is not the slow one."""


class OrientationEstimator(ABC):
    """Measures an object's outline: its angle and its true centre."""

    @abstractmethod
    def measure(self, frame: Frame, detection: Detection) -> OutlineMeasurement:
        """Trace the outline once and report angle, centre and confidence."""


class ColourClassifier(ABC):
    """Decides the colour of an already-detected object."""

    @abstractmethod
    def classify(self, frame: Frame, detection: Detection) -> Colour:
        """Return the dominant colour of the object, or Colour.UNKNOWN."""


class CoordinateMapper(ABC):
    """Converts image coordinates into the robot's work object coordinates."""

    @abstractmethod
    def to_world_xy(self, point: PixelPoint) -> tuple[float, float]:
        """Map a pixel to work-object X and Y in millimetres."""

    @abstractmethod
    def is_calibrated(self) -> bool:
        """False until a valid calibration has been loaded or computed."""


class SceneCalibrator(ABC):
    """Derives the pixel-to-millimetre mapping from the live image itself."""

    @abstractmethod
    def update(self, frame: Frame) -> bool:
        """Look for the reference marker and refresh the mapping."""

    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """True once a usable calibration exists."""


class RobotTransport(ABC):
    """Moves protocol strings between the Pi and the robot."""

    @abstractmethod
    def start(self) -> None:
        """Begin listening and block until the robot connects (or time out)."""

    @abstractmethod
    def send(self, message: str) -> None:
        """Send one already-encoded protocol string."""

    @abstractmethod
    def receive(self, timeout_s: float) -> Optional[str]:
        """Return one protocol string from the robot, or None on timeout."""

    @abstractmethod
    def close(self) -> None:
        """Shut the connection down cleanly."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True while the robot is attached."""


class ObjectSelector(ABC):
    """Chooses which detected object the robot should pick next."""

    @abstractmethod
    def select(
        self,
        objects: Sequence[DetectedObject],
        request: PickRequest,
    ) -> Sequence[DetectedObject]:
        """Return the matching objects, best candidate first."""


class View(ABC):
    """A user interface that displays state and produces pick requests."""

    @abstractmethod
    def render(self, snapshot: StateSnapshot) -> None:
        """Show the latest system state."""

    @abstractmethod
    def run(self) -> None:
        """Enter the UI event loop. Blocks until the window is closed."""
