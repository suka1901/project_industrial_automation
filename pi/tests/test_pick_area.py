"""Tests for keeping jig objects out of the picking candidates.

The jig sits in the camera frame on purpose, so objects already placed in a
slot are detected exactly like objects waiting on the sheet. Nothing else in
the chain can tell them apart - they are the right shape, the right colour and
perfectly confident.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.area import Rect
from domain.enums import Colour, Shape
from domain.models import Detection, DetectedObject, PickRequest, PixelPoint, WorldPose
from application.selectors import PickAreaSelector

SHEET = Rect.from_origin_and_span((0.0, 0.0), (420.0, 297.0), margin=20.0)


def at(x: float, y: float, shape: Shape = Shape.STAR) -> DetectedObject:
    detection = Detection(shape=shape, colour=Colour.RED, confidence=0.95,
                          centre=PixelPoint(0.0, 0.0), angle_deg=0.0)
    return DetectedObject(detection=detection, pose=WorldPose(x, y, 0.0, 0.0))


class TestRect(unittest.TestCase):
    def test_the_margin_grows_the_area_outwards(self):
        self.assertEqual((SHEET.min_x, SHEET.min_y), (-20.0, -20.0))
        self.assertEqual((SHEET.max_x, SHEET.max_y), (440.0, 317.0))

    def test_the_sheet_corners_are_inside(self):
        for x, y in ((0.0, 0.0), (420.0, 0.0), (0.0, 297.0), (420.0, 297.0)):
            self.assertTrue(SHEET.contains(x, y), f"({x}, {y}) should be on the sheet")


class TestPickAreaSelector(unittest.TestCase):
    def setUp(self):
        self.selector = PickAreaSelector(SHEET)

    def _kept(self, *objects):
        return self.selector.select(list(objects), PickRequest())

    def test_an_object_on_the_sheet_is_kept(self):
        self.assertEqual(len(self._kept(at(210.0, 150.0))), 1)

    def test_a_star_sitting_in_the_jig_is_dropped(self):
        """The case from the lab: the jig is in frame, so its contents detect."""
        self.assertEqual(self._kept(at(600.0, 400.0)), [])

    def test_an_object_just_off_the_paper_is_still_picked(self):
        """Half off the sheet is still on the table and still worth picking -
        the margin exists so a camera error at the edge does not refuse it."""
        self.assertEqual(len(self._kept(at(-10.0, 150.0))), 1)

    def test_it_keeps_the_sheet_objects_and_drops_the_jig_ones_together(self):
        kept = self._kept(at(600.0, 400.0), at(100.0, 100.0),
                          at(700.0, 420.0), at(300.0, 200.0))
        self.assertEqual([(o.pose.x, o.pose.y) for o in kept],
                         [(100.0, 100.0), (300.0, 200.0)])

    def test_negative_coordinates_beyond_the_margin_are_dropped(self):
        self.assertEqual(self._kept(at(-100.0, 150.0)), [])

    def test_an_empty_board_stays_empty(self):
        self.assertEqual(self._kept(), [])


if __name__ == "__main__":
    unittest.main()
