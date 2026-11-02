"""Composition root: the only place concrete classes are chosen.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from domain.enums import Shape
from application.coordinate_service import CoordinateService
from application.selectors import (
    AllowedShapeSelector,
    ColourRequestSelector,
    CompositeSelector,
    ConfidenceSelector,
    NearestToOriginSorter,
    PickAreaSelector,
    ShapeRequestSelector,
)
from application.vision_pipeline import VisionPipeline
from ports.interfaces import (
    ColourClassifier,
    CoordinateMapper,
    FrameSource,
    ObjectDetector,
    ObjectSelector,
    OrientationEstimator,
    RobotTransport,
    SceneCalibrator,
)

log = logging.getLogger(__name__)


class Container:
    """Builds the object graph described by a configuration dictionary."""

    def __init__(self, config: Dict[str, Any], base_dir: Path) -> None:
        self._config = config
        self._base = base_dir
        # The mapper is shared between the coordinate service and the live
        # calibrator, so it is built once and cached.
        self._mapper: Optional[CoordinateMapper] = None

    # --- helpers -----------------------------------------------------------

    def _path(self, relative: str) -> str:
        """Resolve a config path relative to the pi/ directory."""
        return str((self._base / relative).resolve())

    @property
    def shapes(self) -> List[Shape]:
        """The three shapes assigned by the instructor, from config."""
        return [Shape.from_name(name) for name in self._config["shapes"]]

    # --- adapters ----------------------------------------------------------

    def build_frame_source(self) -> FrameSource:
        section = self._config["camera"]
        kind = section["kind"].lower()

        if kind == "basler":
            from adapters.camera.camera import Camera
            return Camera(
                serial_number=section.get("serial_number"),
                exposure_us=section.get("exposure_us"),
                gain=section.get("gain"),
                timeout_ms=section.get("timeout_ms", 5000),
                show_window=section.get("show_window", False),
                full_sensor=section.get("full_sensor", True),
            )

        if kind == "file":
            from adapters.camera.file_source import FileFrameSource
            return FileFrameSource(
                directory=self._path(section["directory"]),
                loop=section.get("loop", True),
            )

        if kind == "synthetic":
            from adapters.camera.synthetic_source import SyntheticFrameSource
            return SyntheticFrameSource(fps=section.get("fps", 10.0))

        raise ValueError(f"Unknown camera kind: {kind}")

    def build_detector(self) -> ObjectDetector:
        section = self._config["detector"]
        kind = section["kind"].lower()

        if kind == "yolo":
            from adapters.detection.yolo_detector import YoloDetector
            class_map = {
                int(index): Shape.from_name(name)
                for index, name in section["class_map"].items()
            }
            return YoloDetector(
                model_path=self._path(section["model_path"]),
                class_map=class_map,
                image_size=section.get("image_size", 320),
                confidence=section.get("confidence", 0.5),
            )

        if kind == "ncnn":
            # The Pi's detector: same model, no torch. ultralytics is only the
            # loader, and its torch dependency pulls ~2 GB of CUDA onto a board
            # with no GPU. See adapters/detection/ncnn_detector.py.
            from adapters.detection.ncnn_detector import NcnnDetector
            class_map = {
                int(index): Shape.from_name(name)
                for index, name in section["class_map"].items()
            }
            return NcnnDetector(
                model_dir=self._path(section["model_path"]),
                class_map=class_map,
                image_size=section.get("image_size", 640),
                confidence=section.get("confidence", 0.5),
                iou_threshold=section.get("iou_threshold", 0.45),
                num_threads=section.get("num_threads", 4),
            )

        if kind == "mock":
            from adapters.detection.mock_detector import MockDetector
            return MockDetector(self.shapes)

        raise ValueError(f"Unknown detector kind: {kind}")

    def build_orientation_estimator(self) -> OrientationEstimator:
        """The one estimator there is. `kind` is still read, and still
        refused when it is anything else, because the slot angles record
        which estimator measured them: a config left over from the harmonic
        days must fail here rather than place every object out by the
        difference between the two."""
        section = self._config.get("orientation", {})
        kind = str(section.get("kind", "fitted")).lower()
        if kind != "fitted":
            raise ValueError(
                f"Unknown orientation kind: {kind}. The only estimator is "
                f"'fitted'; re-measure the slot angles with it.")

        from adapters.detection.fitted_orientation_estimator import (
            FittedOrientationEstimator)
        return FittedOrientationEstimator(
            padding_px=section.get("padding_px", 8),
            candidates=section.get("mask_candidates"),
            min_fit=section.get("min_fit", 0.60),
            good_enough_fit=section.get("good_enough_fit", 0.85),
            step_deg=section.get("fit_step_deg", 2.0),
            agreement_deg=section.get("agreement_deg", 4.0),
        )

    def build_colour_classifier(self) -> ColourClassifier:
        section = self._config.get("colour", {})
        from adapters.detection.colour_classifier import (
            HsvColourClassifier,
            PassthroughColourClassifier,
        )

        if section.get("kind", "hsv").lower() == "passthrough":
            return PassthroughColourClassifier()

        return HsvColourClassifier(
            min_saturation=section.get("min_saturation", 80),
            min_value=section.get("min_value", 35),
            min_fraction=section.get("min_fraction", 0.10),
            min_hue_agreement=section.get("min_hue_agreement", 0.85),
            achromatic_max_saturation=section.get("achromatic_max_saturation", 70),
            white_of_paper=section.get("white_of_paper", 0.80),
            black_of_paper=section.get("black_of_paper", 0.45),
        )

    def build_mapper(self) -> CoordinateMapper:
        """Create the mapper, remembering it so the calibrator can refresh it."""
        if self._mapper is not None:
            return self._mapper

        section = self._config["coordinates"]
        kind = section.get("mapper", "identity").lower()

        from adapters.mapping.homography_mapper import (
            IdentityMapper,
            MutableHomographyMapper,
        )

        if kind == "aruco":
            # Solved live from the marker fixed on the table.
            self._mapper = MutableHomographyMapper()
        else:
            self._mapper = IdentityMapper()

        return self._mapper

    def build_calibrator(self) -> Optional[SceneCalibrator]:
        """Build the ArUco calibrator, if the config asks for live calibration."""
        section = self._config["coordinates"]
        if section.get("mapper", "identity").lower() != "aruco":
            return None

        from adapters.mapping.aruco_calibrator import ArucoCalibrator
        from adapters.mapping.homography_mapper import MutableHomographyMapper

        mapper = self.build_mapper()
        if not isinstance(mapper, MutableHomographyMapper):
            raise TypeError("The aruco mapper must be a MutableHomographyMapper")

        marker = self._config["aruco"]
        centre = marker.get("marker_centre_xy_mm", [0.0, 0.0])

        return ArucoCalibrator(
            mapper=mapper,
            marker_length_mm=float(marker["marker_length_mm"]),
            marker_centre_xy_mm=(float(centre[0]), float(centre[1])),
            marker_id=marker.get("marker_id"),
            marker_angle_deg=float(marker.get("marker_angle_deg", 0.0)),
            y_axis_flipped=bool(marker.get("y_axis_flipped", False)),
            dictionary_name=marker.get("dictionary", "DICT_5X5_100"),
            redetect_every_n_frames=int(marker.get("redetect_every_n_frames", 1)),
            hold_last_good=bool(marker.get("hold_last_good", True)),
            scale_tolerance=float(marker.get("scale_tolerance", 0.15)),
        )

    def build_transport(self) -> RobotTransport:
        section = self._config["robot"]
        kind = section.get("transport", "loopback").lower()

        if kind == "tcp":
            from adapters.comms.tcp_server_transport import TcpServerTransport
            return TcpServerTransport(
                host=section["host"],
                port=section["port"],
                accept_timeout_s=section.get("accept_timeout_s", 120.0),
            )

        from adapters.comms.loopback_transport import LoopbackTransport
        return LoopbackTransport()

    # --- use cases ---------------------------------------------------------

    def build_vision_pipeline(self) -> VisionPipeline:
        return VisionPipeline(
            detector=self.build_detector(),
            orientation=self.build_orientation_estimator(),
            colour=self.build_colour_classifier(),
            budget_ms=self._config["vision"].get("inference_budget_ms", 3000.0),
            calibrator=self.build_calibrator(),
        )

    def build_coordinate_service(self) -> CoordinateService:
        section = self._config["coordinates"]
        slot_angles = {
            Shape.from_name(name): float(angle)
            for name, angle in (section.get("place_slot_angles_deg") or {}).items()
        }
        return CoordinateService(
            mapper=self.build_mapper(),
            angle_sign=section.get("angle_sign", 1),
            angle_offset_deg=section.get("angle_offset_deg", 0.0),
            slot_angles_deg=slot_angles,
        )

    @property
    def verify_tolerance_mm(self) -> float:
        """How close a leftover object must be to count as a failed pick."""
        return float(self._config["robot"].get("verify_tolerance_mm", 0.0))

    @property
    def pick_area(self):
        """The sheet, as a rectangle in picking work object millimetres."""
        from domain.area import Rect
        section = self._config.get("sheet", {})
        return Rect.from_origin_and_span(
            tuple(section.get("origin_xy_mm", [0.0, 0.0])),
            section.get("span_xy_mm", [420.0, 297.0]),
            margin=section.get("margin_mm", 20.0),
        )

    def build_selector(self) -> ObjectSelector:
        """Chain the selection rules. Adding a rule = adding one line here."""
        return CompositeSelector([
            AllowedShapeSelector(self.shapes),          # never touch the other two
            PickAreaSelector(self.pick_area),           # the jig is in frame too
            ConfidenceSelector(self._config["vision"].get("min_confidence", 0.5)),
            ShapeRequestSelector(),                      # what the operator chose
            ColourRequestSelector(),                     # colour rule (Level II/III)
            NearestToOriginSorter(),                     # shortest robot travel first
        ])
