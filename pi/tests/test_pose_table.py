"""Tests for the window's numeric pose readout.

The course asks the GUI to display each object's position and orientation,
so what is tested is that both reach the screen, in the units they are
measured in, and that a circle is not given an orientation it does not have.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.gui.pose_table import MAX_ROWS, NOTHING, pose_table
from domain.enums import Colour, Shape
from domain.models import (BoundingBox, Detection, DetectedObject, PixelPoint,
                           WorldPose)


def seen(shape=Shape.STAR, colour=Colour.RED, x=182.4, y=96.1,
         angle=40.7, rz=-31.6, fit=0.85):
    detection = Detection(shape=shape, colour=colour, confidence=0.9,
                          centre=PixelPoint(100.0, 100.0), angle_deg=angle,
                          box=BoundingBox(0.0, 0.0, 10.0, 10.0),
                          angle_confidence=fit)
    return DetectedObject(detection=detection,
                          pose=WorldPose(x=x, y=y, z=0.0, rz=rz))


class TestWhatReachesTheScreen(unittest.TestCase):

    def test_an_empty_table_says_so_rather_than_showing_a_header(self):
        self.assertEqual(pose_table(()), NOTHING)

    def test_the_position_is_shown_in_millimetres(self):
        row = pose_table([seen(x=182.4, y=96.1)]).splitlines()[1]
        self.assertIn("182.4", row)
        self.assertIn("96.1", row)

    def test_both_angles_are_shown(self):
        # The measured angle and the commanded turn are different numbers,
        # and seeing both is what separates a misread from a bad slot angle.
        row = pose_table([seen(angle=40.7, rz=-31.6)]).splitlines()[1]
        self.assertIn("40.7", row)
        self.assertIn("-31.6", row)

    def test_the_shape_and_colour_are_named(self):
        row = pose_table([seen(shape=Shape.SQUARE, colour=Colour.BLUE)]).splitlines()[1]
        self.assertIn("SQUARE", row)
        self.assertIn("BLUE", row)

    def test_the_fit_travels_with_the_angle(self):
        self.assertIn("0.85", pose_table([seen(fit=0.85)]).splitlines()[1])


class TestACircleHasNoOrientation(unittest.TestCase):

    def test_it_is_marked_rather_than_given_zeros(self):
        row = pose_table([seen(shape=Shape.CIRCLE, angle=0.0, rz=0.0,
                               fit=0.0)]).splitlines()[1]
        self.assertIn("CIRCLE", row)
        self.assertNotIn("0.00", row)      # a fit of zero would look measured

    def test_its_position_is_still_shown(self):
        row = pose_table([seen(shape=Shape.CIRCLE, x=12.5, y=34.5)]).splitlines()[1]
        self.assertIn("12.5", row)
        self.assertIn("34.5", row)


class TestTheWindowDoesNotGrowWithoutLimit(unittest.TestCase):

    def test_a_crowded_table_is_cut_off_and_says_how_many_are_missing(self):
        text = pose_table([seen() for _ in range(MAX_ROWS + 3)])
        self.assertEqual(len(text.splitlines()), MAX_ROWS + 2)   # header + note
        self.assertIn("3 more", text)

    def test_a_full_table_needs_no_note(self):
        text = pose_table([seen() for _ in range(MAX_ROWS)])
        self.assertNotIn("more", text)


class TestTheColumnsStayStill(unittest.TestCase):
    """Fixed width, or the numbers dance as they change and nothing can be
    read at a glance - which is the only way this is ever read."""

    def test_every_row_is_the_same_width(self):
        text = pose_table([seen(x=1.0, y=2.0),
                           seen(x=-123.4, y=410.9, angle=-179.9, rz=179.9),
                           seen(shape=Shape.CIRCLE)])
        widths = {len(line) for line in text.splitlines()}
        self.assertEqual(len(widths), 1)


if __name__ == "__main__":
    unittest.main()
