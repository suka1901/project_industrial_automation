"""Tests for the guarded state the GUI reads.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.gui.formatting import NO_ANGLE, angle_confidence_text
from application.shared_state import SharedState
from domain.enums import Colour, Shape
from domain.models import BoundingBox, Detection, PixelPoint


def detection() -> Detection:
    return Detection(shape=Shape.STAR, colour=Colour.RED, confidence=0.9,
                     centre=PixelPoint(10.0, 10.0), angle_deg=12.0,
                     box=BoundingBox(0.0, 0.0, 20.0, 20.0))


class TestPreview(unittest.TestCase):
    def test_frame_and_its_detections_travel_together(self):
        """They are one value, so the GUI cannot mix frames and boxes."""
        state = SharedState()
        state.set_preview("frame-7", [detection()], sequence=7)
        preview = state.snapshot().preview
        self.assertEqual(preview.image, "frame-7")
        self.assertEqual(preview.sequence, 7)
        self.assertEqual(len(preview.detections), 1)

    def test_detections_are_a_tuple_the_gui_cannot_mutate(self):
        state = SharedState()
        state.set_preview("frame", [detection()], sequence=1)
        self.assertIsInstance(state.snapshot().preview.detections, tuple)

    def test_snapshots_are_immutable_so_a_reader_is_never_half_updated(self):
        state = SharedState()
        state.set_preview("first", [], sequence=1)
        held = state.snapshot()
        state.set_preview("second", [], sequence=2)
        self.assertEqual(held.preview.image, "first")
        self.assertEqual(state.snapshot().preview.image, "second")

    def test_no_preview_before_the_first_frame(self):
        self.assertIsNone(SharedState().snapshot().preview)


class TestAngleConfidenceText(unittest.TestCase):
    """The fit is information, not a warning: no object is ever refused on it."""

    def _object(self, shape, angle_confidence):
        from domain.models import DetectedObject, WorldPose
        measured = Detection(shape=shape, colour=Colour.RED, confidence=0.9,
                             centre=PixelPoint(0.0, 0.0), angle_deg=0.0,
                             angle_confidence=angle_confidence)
        return DetectedObject(detection=measured,
                              pose=WorldPose(0.0, 0.0, 0.0, 0.0))

    def test_a_circle_has_nothing_to_fit(self):
        self.assertEqual(angle_confidence_text(self._object(Shape.CIRCLE, 0.0)),
                         NO_ANGLE)

    def test_the_fit_is_shown_as_a_number(self):
        self.assertEqual(angle_confidence_text(self._object(Shape.STAR, 0.91)),
                         "0.910")

    def test_a_poor_fit_is_still_just_a_number(self):
        """It is placed at the best angle available, so there is nothing to warn
        about - only a reading to report."""
        text = angle_confidence_text(self._object(Shape.STAR, 0.42))
        self.assertEqual(text, "0.420")
        self.assertNotIn("WEAK", text.upper())


if __name__ == "__main__":
    unittest.main()
