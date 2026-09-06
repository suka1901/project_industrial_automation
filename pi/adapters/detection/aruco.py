"""ArUco marker detection and drawing.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from domain.marker import pixel_mm_ratio_from_perimeter

log = logging.getLogger(__name__)

DEFAULT_DICTIONARY = "DICT_5X5_100"
DEFAULT_MARKER_LENGTH_MM = 100.0  # the length of one side of the square marker, in millimetres


class ArUco:
    """Detects 5x5 ArUco markers and measures the image scale from them."""

    def __init__(
        self,
        dictionary_name: str = DEFAULT_DICTIONARY,
        marker_length_mm: float = DEFAULT_MARKER_LENGTH_MM,
        refine_corners: bool = True,
    ) -> None:
        self._dictionary_name = dictionary_name
        self._marker_length_mm = marker_length_mm
        self._refine_corners = refine_corners
        # Built on first use, so the class can be constructed without OpenCV.
        self._detector: Optional[Any] = None

    # --- set-up ------------------------------------------------------------

    def _ensure_detector(self) -> Any:
        """Build the detector once and return it."""
        if self._detector is not None:
            return self._detector

        import cv2

        if not hasattr(cv2, "aruco"):
            raise RuntimeError(
                "cv2.aruco is missing. Install opencv-contrib-python "
                "(the plain opencv-python package does not include ArUco)."
            )

        # OpenCV's ArUco type stubs vary between releases: some declare the
        # DetectorParameters tuning fields, some do not, so an editor may flag
        # a field that exists perfectly well at runtime. Going through an
        # Any-typed handle keeps the checker quiet and changes no behaviour.
        aruco_api: Any = cv2.aruco

        aruco_dict = aruco_api.getPredefinedDictionary(
            getattr(aruco_api, self._dictionary_name)
        )
        parameters = aruco_api.DetectorParameters()
        if self._refine_corners:
            # Sub-pixel refinement: worth about a millimetre of accuracy for
            # almost no cost, and not something Exercise 2 needed.
            parameters.cornerRefinementMethod = aruco_api.CORNER_REFINE_SUBPIX

        self._detector = aruco_api.ArucoDetector(aruco_dict, parameters)
        log.info("ArUco detector ready (%s)", self._dictionary_name)
        return self._detector

    # --- detection ---------------------------------------------------------

    def detect(self, img: Any) -> Tuple[Any, Any]:
        """Return (corners, ids) for every marker in the image."""
        detector = self._ensure_detector()
        corners, ids, _ = detector.detectMarkers(img)
        return corners, ids

    def draw(self, img: Any, corners: Any, ids: Any = None) -> Any:
        """Draw the detected marker outlines and IDs onto the image."""
        import cv2
        aruco_api: Any = cv2.aruco
        if corners is not None and len(corners) > 0:
            aruco_api.drawDetectedMarkers(img, corners, ids)
        return img

    def corners_for_id(self, corners: Any, ids: Any,
                       marker_id: Optional[int]) -> Any:
        """Return one marker's corners, chosen by ID, or None if absent."""
        if ids is None or len(corners) == 0:
            return None

        if marker_id is None:
            return corners[0]

        detected = [int(value) for value in ids.flatten()]
        if marker_id not in detected:
            return None
        return corners[detected.index(marker_id)]

    def pixel_mm_ratio(self, marker_corners: Any) -> float:
        """Pixels per millimetre from the marker perimeter - Exercise 2's formula."""
        import cv2
        perimeter_px = float(cv2.arcLength(marker_corners, True))
        return pixel_mm_ratio_from_perimeter(perimeter_px, self._marker_length_mm)
