"""Tests for the guarded state the GUI reads.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.gui.formatting import (NOT_TRUSTED_MARK, angle_confidence_text,
                                      untrusted_angle_warning)
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
    """The GUI must explain a skipped object rather than just omitting it."""

    def _object(self, shape, angle_confidence, trusted=True):
        from domain.models import DetectedObject, WorldPose
        detection = Detection(shape=shape, colour=Colour.RED, confidence=0.9,
                              centre=PixelPoint(0.0, 0.0), angle_deg=0.0,
                              angle_confidence=angle_confidence)
        return DetectedObject(detection=detection,
                              pose=WorldPose(0.0, 0.0, 0.0, 0.0),
                              angle_trusted=trusted)

    def test_a_circle_has_no_angle_to_report(self):
        text = angle_confidence_text(self._object(Shape.CIRCLE, 0.0), gate=0.10)
        self.assertEqual(text, "n/a")

    def test_a_trusted_angle_shows_the_value_alone(self):
        text = angle_confidence_text(self._object(Shape.STAR, 0.21), gate=0.10)
        self.assertEqual(text, "0.210")

    def test_an_untrusted_angle_is_marked(self):
        # Assert against the constant, not a literal: the marker is deliberately
        # short because the table column truncates anything longer.
        text = angle_confidence_text(
            self._object(Shape.STAR, 0.022, trusted=False), gate=0.10)
        self.assertIn(NOT_TRUSTED_MARK.strip(), text)
        self.assertIn("0.022", text)

    def test_the_marker_is_short_enough_for_the_column(self):
        """A clipped marker reads as nothing, so guard the length here."""
        self.assertLessEqual(len(NOT_TRUSTED_MARK.strip()), 6)


class TestUntrustedAngleWarning(unittest.TestCase):
    """The banner must name the shapes, and vanish when there is nothing wrong."""

    def _object(self, shape, trusted):
        from domain.models import DetectedObject, WorldPose
        detection = Detection(shape=shape, colour=Colour.RED, confidence=0.9,
                              centre=PixelPoint(0.0, 0.0), angle_deg=0.0,
                              angle_confidence=0.02 if not trusted else 0.3)
        return DetectedObject(detection=detection,
                              pose=WorldPose(0.0, 0.0, 0.0, 0.0),
                              angle_trusted=trusted)

    def test_silent_when_every_angle_is_trusted(self):
        objects = [self._object(Shape.STAR, True), self._object(Shape.SQUARE, True)]
        self.assertEqual(untrusted_angle_warning(objects), "")

    def test_names_the_shapes_it_could_not_measure(self):
        objects = [self._object(Shape.STAR, False), self._object(Shape.SQUARE, True)]
        warning = untrusted_angle_warning(objects)
        self.assertIn("STAR", warning)
        self.assertNotIn("SQUARE", warning)
        self.assertIn("UNROTATED", warning.upper())

    def test_silent_with_nothing_on_the_board(self):
        self.assertEqual(untrusted_angle_warning([]), "")

if __name__ == "__main__":
    unittest.main()
