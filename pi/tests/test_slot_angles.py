"""Tests for restricting the slot-angle measurement to one slot.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from calibration.slot_angles import largest_object_box


def scene() -> np.ndarray:
    """A big bright block on the left, a small one on the right, dark ground."""
    image = np.zeros((400, 600, 3), dtype=np.uint8)
    image[100:300, 50:250] = 240      # the jig plate: biggest thing in frame
    image[180:240, 400:460] = 240     # the object in its slot
    return image


class TestRegionRestriction(unittest.TestCase):
    def test_without_a_region_the_biggest_thing_wins(self):
        """Which is the jig plate, not the object - hence the region."""
        box = largest_object_box(scene())
        self.assertLess(box.u_min, 260)

    def test_a_region_selects_the_object_in_that_slot(self):
        box = largest_object_box(scene(), region=(380, 160, 120, 120))
        self.assertGreater(box.u_min, 380)

    def test_coordinates_come_back_in_full_frame_space(self):
        """The crop offset must be added back, or every angle is measured on
        the right shape at the wrong place."""
        box = largest_object_box(scene(), region=(380, 160, 120, 120))
        self.assertAlmostEqual(box.u_min, 400, delta=2)
        self.assertAlmostEqual(box.v_min, 180, delta=2)
        self.assertAlmostEqual(box.u_max, 460, delta=2)
        self.assertAlmostEqual(box.v_max, 240, delta=2)

    def test_an_empty_region_finds_nothing(self):
        self.assertIsNone(largest_object_box(scene(), region=(500, 300, 50, 50)))

    def test_a_region_off_the_frame_does_not_crash(self):
        self.assertIsNone(largest_object_box(scene(), region=(900, 900, 50, 50)))


if __name__ == "__main__":
    unittest.main()
