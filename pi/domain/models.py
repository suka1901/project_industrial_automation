"""Immutable value objects passed between threads.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from domain.enums import Colour, CycleOutcome, Shape


@dataclass(frozen=True)
class PixelPoint:
    """A point in image coordinates (u = column, v = row), sub-pixel capable."""

    u: float
    v: float


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned bounding box in image coordinates."""

    u_min: float
    v_min: float
    u_max: float
    v_max: float

    @property
    def centre(self) -> PixelPoint:
        """Geometric centre of the box (a coarse fallback for the centroid)."""
        return PixelPoint((self.u_min + self.u_max) / 2.0,
                          (self.v_min + self.v_max) / 2.0)

    @property
    def width(self) -> float:
        return self.u_max - self.u_min

    @property
    def height(self) -> float:
        return self.v_max - self.v_min


@dataclass(frozen=True)
class Frame:
    """One captured image plus the metadata needed to trace it through the pipeline."""

    image: Any
    sequence: int
    captured_at: float  # time.monotonic() at grab time


@dataclass(frozen=True)
class Detection:
    """One object as seen by the camera, still entirely in image coordinates."""

    shape: Shape
    colour: Colour
    confidence: float
    centre: PixelPoint
    # Measured in the IMAGE frame, where v grows downward - so a positive
    # angle turns clockwise on screen, the opposite of the robot's Rz.
    # coordinates.angle_sign converts the sense. (This said CCW, which
    # was simply wrong, and it is the sort of wrong that costs a day.)
    angle_deg: float
    box: Optional[BoundingBox] = None
    # How clearly the outline showed its N-fold symmetry. Separate from
    # `confidence`, which is the detector's. A circle is legitimately 0.
    angle_confidence: float = 0.0


@dataclass(frozen=True)
class OutlineMeasurement:
    """What one pass over an object's outline yields."""

    angle_deg: float
    centre: PixelPoint
    confidence: float


@dataclass(frozen=True)
class WorldPose:
    """A pose expressed in the robot's work object coordinate system (millimetres/degrees)."""

    x: float
    y: float
    z: float
    rz: float


@dataclass(frozen=True)
class DetectedObject:
    """A detection that has been translated into robot coordinates - ready to send."""

    detection: Detection
    pose: WorldPose

    @property
    def shape(self) -> Shape:
        return self.detection.shape

    @property
    def colour(self) -> Colour:
        return self.detection.colour


@dataclass(frozen=True)
class InferenceResult:
    """Everything one pass of the vision pipeline produced, including its timing."""

    detections: Sequence[Detection]
    elapsed_ms: float
    frame_sequence: int


@dataclass(frozen=True)
class MappedScene:
    """One analysed frame with every object already in work object coordinates.

    Produced by the coordinate-translation thread, consumed by the cycle.
    Carrying the timing along means the cycle can still report how long the
    model took for the very frame it is acting on.
    """

    objects: Sequence[DetectedObject]
    elapsed_ms: float
    frame_sequence: int


@dataclass(frozen=True)
class PickRequest:
    """What the operator asked for in this cycle, chosen through the GUI."""

    shape: Optional[Shape] = None    # None means "any of the configured shapes"
    colour: Optional[Colour] = None  # None means "any colour"


@dataclass(frozen=True)
class CycleReport:
    """Outcome of a single pick-and-place cycle, shown in the GUI and logged."""

    cycle_index: int
    request: PickRequest
    target: Optional[DetectedObject]
    outcome: CycleOutcome
    attempts: int
    message: str = ""


@dataclass(frozen=True)
class Preview:
    """What the window draws: a frame, and the boxes to draw on it.

    The image is refreshed by the CAPTURE thread, at ten to fifteen frames a
    second; the boxes come from inference, which manages two or three. So the
    two are deliberately NOT the same age, and `detections_sequence` says
    which frame the boxes were measured in - the difference is how stale the
    overlay is.

    They still travel as one value, so the window can never draw half of one
    update and half of the next. What it cannot do is pretend the boxes were
    measured in the frame they are drawn over: on a still table they match,
    and while the arm is sweeping through they visibly do not.
    """

    image: Any
    detections: Sequence[Detection] = field(default_factory=tuple)
    sequence: int = 0
    detections_sequence: int = 0


@dataclass(frozen=True)
class StateSnapshot:
    """An immutable view of the system, produced for the GUI to render."""

    connected: bool = False
    cycle_index: int = 0
    inference_ms: float = 0.0
    detections: Sequence[DetectedObject] = field(default_factory=tuple)
    preview: Optional[Preview] = None
    last_report: Optional[CycleReport] = None
    status_text: str = "starting up"
