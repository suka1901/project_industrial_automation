"""Turns one camera frame into timed, fully described detections.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

from domain.models import Detection, Frame, InferenceResult
from ports.interfaces import (
    ColourClassifier,
    ObjectDetector,
    OrientationEstimator,
    SceneCalibrator,
)

log = logging.getLogger(__name__)


class VisionPipeline:
    """Runs detection, orientation and colour on a single frame, and times it."""

    def __init__(
        self,
        detector: ObjectDetector,
        orientation: OrientationEstimator,
        colour: ColourClassifier,
        budget_ms: float = 3000.0,
        calibrator: Optional[SceneCalibrator] = None,
    ) -> None:
        self._detector = detector
        self._orientation = orientation
        self._colour = colour
        self._budget_ms = budget_ms
        # Optional: an ArUco marker on the table that re-solves the
        # pixel-to-millimetre mapping from every frame.
        self._calibrator = calibrator

    def warm_up(self) -> None:
        """Pay the one-off model loading cost before the first real cycle."""
        self._detector.warm_up()

    def process(self, frame: Frame) -> InferenceResult:
        """Analyse one frame and return the detections plus elapsed time."""
        started = time.perf_counter()

        # Refresh the calibration first: if the camera has been nudged, the
        # coordinates derived from this very frame must already reflect it.
        if self._calibrator is not None:
            self._calibrator.update(frame)

        enriched: List[Detection] = []
        for raw in self._detector.detect(frame):
            # One pass over the outline gives both the angle and the true
            # centre. The centre is where the cup lands, so it matters as much
            # as the angle - a bounding box centre can sit off the object.
            outline = self._orientation.measure(frame, raw)
            enriched.append(
                Detection(
                    shape=raw.shape,
                    colour=self._colour.classify(frame, raw),
                    confidence=raw.confidence,
                    centre=outline.centre,
                    angle_deg=outline.angle_deg,
                    box=raw.box,
                    angle_confidence=outline.confidence,
                )
            )

        elapsed_ms = (time.perf_counter() - started) * 1000.0

        # The project requires the inference time to be printed every cycle.
        print(f"[vision] inference time: {elapsed_ms:.1f} ms "
              f"({len(enriched)} object(s))")
        if elapsed_ms > self._budget_ms:
            log.warning("Inference took %.1f ms, over the %.0f ms budget",
                        elapsed_ms, self._budget_ms)

        return InferenceResult(
            detections=tuple(enriched),
            elapsed_ms=elapsed_ms,
            frame_sequence=frame.sequence,
        )
