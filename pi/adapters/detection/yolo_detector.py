"""Object detection with a trained YOLO model.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from domain.enums import Colour, Shape
from domain.models import BoundingBox, Detection, Frame
from ports.interfaces import ObjectDetector

log = logging.getLogger(__name__)


class YoloDetector(ObjectDetector):
    """Runs a trained YOLO model and converts its output into Detections."""

    def __init__(
        self,
        model_path: str,
        class_map: Dict[int, Shape],
        image_size: int = 320,
        confidence: float = 0.5,
    ) -> None:
        self._model_path = model_path
        self._class_map = dict(class_map)
        self._image_size = image_size
        self._confidence = confidence
        # Loaded on first use; _ensure_loaded returns a non-None model.
        self._model: Optional[Any] = None

    def _ensure_loaded(self) -> Any:
        """Load the model on first use and return it."""
        if self._model is None:
            from ultralytics import YOLO  # lazy import keeps startup light
            log.info("Loading YOLO model from %s", self._model_path)
            self._model = YOLO(self._model_path, task="detect")
        return self._model

    def warm_up(self) -> None:
        """Load and run one dummy inference so cycle 1 is not the slow one."""
        import numpy as np
        model = self._ensure_loaded()
        blank = np.zeros((self._image_size, self._image_size, 3), dtype="uint8")
        model.predict(blank, imgsz=self._image_size, verbose=False)
        log.info("YOLO warm-up complete")

    def detect(self, frame: Frame) -> Sequence[Detection]:
        """Return one Detection per accepted object in the frame."""
        model = self._ensure_loaded()

        results = model.predict(
            frame.image,
            imgsz=self._image_size,
            conf=self._confidence,
            verbose=False,
        )

        detections: List[Detection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                class_id = int(box.cls.item())
                shape = self._class_map.get(class_id)
                if shape is None:
                    # A class the config does not map is silently ignored.
                    continue

                u_min, v_min, u_max, v_max = (float(v) for v in box.xyxy[0].tolist())
                bounds = BoundingBox(u_min, v_min, u_max, v_max)

                detections.append(
                    Detection(
                        shape=shape,
                        colour=Colour.UNKNOWN,
                        confidence=float(box.conf.item()),
                        centre=bounds.centre,
                        angle_deg=0.0,
                        box=bounds,
                    )
                )
        return detections
