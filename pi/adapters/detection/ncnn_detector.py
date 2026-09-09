"""YOLO detection through ncnn, without torch.

The Raspberry Pi runs the same model as the PC, but ultralytics - which is
only the LOADER - drags in torch, and torch's aarch64 wheel bundles about
2 GB of CUDA libraries for a board that has no NVIDIA GPU. It filled the Pi's
disk before it finished installing.

ncnn runs the exported model in 12 MB. What ultralytics did for free, and what
this class therefore has to do by hand, is the letterboxing on the way in and
the decoding, thresholding and non-maximum suppression on the way out.

The exported graph ends at one blob, `out0`, shaped (4 + classes, 8400):
rows 0-3 are cx, cy, w, h in LETTERBOXED pixels, and the remaining rows are
per-class scores already through a sigmoid. There is no objectness row - v8
dropped it - so the class score is the confidence.

The export must come from a pnnx matching the installed ncnn. A mismatched one
builds the wrong graph, and it segfaults in Slice two layers before the output
rather than reporting anything.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from domain.enums import Colour, Shape
from domain.models import BoundingBox, Detection, Frame
from ports.interfaces import ObjectDetector

log = logging.getLogger(__name__)

INPUT_BLOB = "in0"
OUTPUT_BLOB = "out0"
PAD_VALUE = 114          # the grey ultralytics letterboxes with


class NcnnDetector(ObjectDetector):
    """Runs the exported NCNN model directly, with no torch in the process."""

    def __init__(
        self,
        model_dir: str,
        class_map: Dict[int, Shape],
        image_size: int = 640,
        confidence: float = 0.5,
        iou_threshold: float = 0.45,
        num_threads: int = 4,
    ) -> None:
        self._model_dir = str(model_dir).rstrip("/\\")
        self._class_map = dict(class_map)
        self._image_size = image_size
        self._confidence = confidence
        self._iou_threshold = iou_threshold
        self._num_threads = num_threads
        self._net: Optional[Any] = None

    # --- model -------------------------------------------------------------

    def _ensure_loaded(self) -> Any:
        """Load the net once. ncnn keeps the weights mapped, so this is cheap."""
        if self._net is None:
            import ncnn
            net = ncnn.Net()
            net.opt.use_vulkan_compute = False      # no GPU on the Pi
            net.opt.num_threads = self._num_threads
            param = f"{self._model_dir}/model.ncnn.param"
            weights = f"{self._model_dir}/model.ncnn.bin"
            if net.load_param(param) != 0 or net.load_model(weights) != 0:
                raise RuntimeError(
                    f"ncnn could not load {self._model_dir}. Both "
                    f"model.ncnn.param and model.ncnn.bin must be present."
                )
            log.info("NCNN model loaded from %s", self._model_dir)
            self._net = net
        return self._net

    def warm_up(self) -> None:
        """One pass on a blank frame, so the first real cycle is not the slow one."""
        import numpy as np
        blank = np.full((self._image_size, self._image_size, 3), PAD_VALUE, dtype="uint8")
        self._infer(blank)
        log.info("NCNN warm-up complete")

    # --- the pieces ultralytics used to do ---------------------------------

    def _letterbox(self, image: Any) -> Tuple[Any, float, int, int]:
        """Scale to fit the square input and pad, preserving aspect ratio.

        Returns the canvas and the transform needed to undo it. Stretching
        instead would distort every shape, and the orientation estimator reads
        those outlines later.
        """
        import cv2
        import numpy as np

        height, width = image.shape[:2]
        scale = min(self._image_size / width, self._image_size / height)
        new_w, new_h = int(round(width * scale)), int(round(height * scale))

        canvas = np.full((self._image_size, self._image_size, 3), PAD_VALUE, dtype="uint8")
        left, top = (self._image_size - new_w) // 2, (self._image_size - new_h) // 2
        canvas[top:top + new_h, left:left + new_w] = cv2.resize(
            image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        return np.ascontiguousarray(canvas), scale, left, top

    def letterbox_for_test(self, image: Any):
        """The letterbox and its inverse transform, exposed for the tests.

        Named rather than reaching into _letterbox from outside, so the test
        is written against something the class means to offer.
        """
        return self._letterbox(image)

    def _infer(self, canvas: Any) -> Any:
        """Run the net on a prepared canvas and return the raw (rows, 8400) output."""
        import ncnn
        import numpy as np

        net = self._ensure_loaded()
        mat = ncnn.Mat.from_pixels(canvas, ncnn.Mat.PixelType.PIXEL_BGR2RGB,
                                   self._image_size, self._image_size)
        # The model was trained on 0-1 inputs; ncnn takes 0-255 pixels.
        mat.substract_mean_normalize([], [1 / 255.0] * 3)

        extractor = net.create_extractor()
        extractor.input(INPUT_BLOB, mat)
        code, out = extractor.extract(OUTPUT_BLOB)
        if code != 0:
            raise RuntimeError(f"ncnn extract('{OUTPUT_BLOB}') failed with {code}")
        return np.array(out)

    @staticmethod
    def _suppress(boxes: Any, scores: Any, threshold: float) -> List[int]:
        """Greedy non-maximum suppression. Boxes are xyxy.

        One object fires several neighbouring anchors, so without this every
        object is reported three or four times and the cycle picks at a
        duplicate that is not quite where the object is.
        """
        import numpy as np

        if len(boxes) == 0:
            return []
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]

        keep: List[int] = []
        while order.size > 0:
            best = int(order[0])
            keep.append(best)
            if order.size == 1:
                break
            rest = order[1:]
            xx1 = np.maximum(x1[best], x1[rest])
            yy1 = np.maximum(y1[best], y1[rest])
            xx2 = np.minimum(x2[best], x2[rest])
            yy2 = np.minimum(y2[best], y2[rest])
            overlap = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
            union = areas[best] + areas[rest] - overlap
            iou = np.where(union > 0, overlap / union, 0.0)
            order = rest[iou <= threshold]
        return keep

    # --- ObjectDetector ----------------------------------------------------

    def detect(self, frame: Frame) -> Sequence[Detection]:
        """Return one Detection per accepted object, in original image pixels."""
        import numpy as np

        if frame.image is None:
            return []

        canvas, scale, pad_left, pad_top = self._letterbox(frame.image)
        raw = self._infer(canvas)                       # (4 + classes, 8400)
        if raw.ndim != 2 or raw.shape[0] < 5:
            log.error("Unexpected NCNN output shape %s", raw.shape)
            return []

        boxes_xywh = raw[:4]
        class_scores = raw[4:]

        best_class = class_scores.argmax(axis=0)
        best_score = class_scores.max(axis=0)
        accepted = np.nonzero(best_score >= self._confidence)[0]
        if accepted.size == 0:
            return []

        cx, cy, w, h = (boxes_xywh[i][accepted] for i in range(4))
        # Undo the letterbox: remove the padding, then the scale.
        half_w, half_h = w / 2.0, h / 2.0
        xyxy = np.stack([(cx - half_w - pad_left) / scale,
                         (cy - half_h - pad_top) / scale,
                         (cx + half_w - pad_left) / scale,
                         (cy + half_h - pad_top) / scale], axis=1)

        height, width = frame.image.shape[:2]
        xyxy[:, 0::2] = xyxy[:, 0::2].clip(0, width)
        xyxy[:, 1::2] = xyxy[:, 1::2].clip(0, height)

        scores = best_score[accepted]
        classes = best_class[accepted]

        detections: List[Detection] = []
        # Suppress per class: a square overlapping a star is two objects, and
        # suppressing across classes would silently drop one of them.
        for class_id in np.unique(classes):
            shape = self._class_map.get(int(class_id))
            if shape is None:
                continue                    # a class config does not map
            mine = np.nonzero(classes == class_id)[0]
            for index in self._suppress(xyxy[mine], scores[mine], self._iou_threshold):
                u_min, v_min, u_max, v_max = (float(v) for v in xyxy[mine][index])
                bounds = BoundingBox(u_min, v_min, u_max, v_max)
                detections.append(Detection(
                    shape=shape,
                    colour=Colour.UNKNOWN,
                    confidence=float(scores[mine][index]),
                    centre=bounds.centre,
                    angle_deg=0.0,
                    box=bounds,
                ))
        return detections
