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
    angle_deg: float                  # measured in the image frame, CCW positive
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
    # False when the outline was too weak to measure an angle from. The object
    # is still picked - a refused pick fails the assignment outright, while a
    # wrong angle costs one of the six placements - but the operator is told.
    angle_trusted: bool = True

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
    """One frame and the detections found in it, kept together.

    Bundling them means the GUI cannot draw one frame's boxes over another
    frame's image, which is what happens when they are stored separately and
    updated a moment apart.
    """

    image: Any
    detections: Sequence[Detection] = field(default_factory=tuple)
    sequence: int = 0


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
