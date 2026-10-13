"""Tests for turning a detection into the pose the robot is sent.

The gap these close: nothing tested angle_sign or to_pose at all, which is how
the placing rotation stayed wrong. The camera measures clockwise-positive
(image v grows downward) and the robot's Rz is counter-clockwise-positive, so
the sense has to be converted - but the SLOT angle is a camera angle too,
measured by the same estimator. Convert the difference, not one term of it.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.coordinate_service import CoordinateService
from domain.enums import Colour, Shape
from domain.models import Detection, PixelPoint
from ports.interfaces import CoordinateMapper


class FixedMapper(CoordinateMapper):
    def is_calibrated(self):
        return True

    def to_world_xy(self, point: PixelPoint):
        return (100.0, 200.0)


def detection(shape, angle_deg, confidence=0.9):
    return Detection(shape=shape, colour=Colour.RED, confidence=0.9,
                     centre=PixelPoint(10.0, 10.0), angle_deg=angle_deg,
                     angle_confidence=confidence, box=None)


def service(sign=1, slot=0.0, offset=0.0):
    return CoordinateService(FixedMapper(), angle_sign=sign,
                             angle_offset_deg=offset,
                             slot_angles_deg={Shape.SQUARE: slot, Shape.STAR: slot},
                             min_angle_confidence=0.10)


class TestThePlacingRotation(unittest.TestCase):

    def test_an_object_already_at_the_slot_angle_needs_no_turn(self):
        """The case that must hold for either sign, so it pins nothing else."""
        for sign in (1, -1):
            with self.subTest(sign=sign):
                pose = service(sign=sign, slot=30.0).to_pose(
                    detection(Shape.SQUARE, 30.0))
                self.assertAlmostEqual(pose.rz, 0.0, places=6)

    def test_the_turn_is_the_difference_not_the_sum(self):
        """The bug: sign on the object alone made this slot + measured.

        Deliberately not slot=45, measured=0: 45 is exactly half a square's
        period, so +45 and -45 are the same rotation and the broken code
        passes. Neither term may be zero either, or sum and difference agree.
        """
        pose = service(sign=-1, slot=30.0).to_pose(detection(Shape.SQUARE, 10.0))
        # camera turn is 30 - 10 = +20; in the robot's opposite sense, -20.
        self.assertAlmostEqual(pose.rz, -20.0, places=6)
        # the old code computed slot - (sign * measured) = 30 + 10 = +40.
        self.assertNotAlmostEqual(pose.rz, 40.0, places=6)

    def test_flipping_the_sign_flips_the_turn(self):
        a = service(sign=1, slot=20.0).to_pose(detection(Shape.SQUARE, 5.0))
        b = service(sign=-1, slot=20.0).to_pose(detection(Shape.SQUARE, 5.0))
        self.assertAlmostEqual(a.rz, -b.rz, places=6)

    def test_the_turn_stays_inside_the_symmetry_period(self):
        for measured in (0.0, 10.0, 44.0, 89.0, 130.0, 250.0):
            with self.subTest(measured=measured):
                rz = service(sign=-1, slot=45.0).to_pose(
                    detection(Shape.SQUARE, measured)).rz
                self.assertLessEqual(abs(rz), 45.0 + 1e-9)

    def test_a_star_folds_at_seventy_two_not_ninety(self):
        """0 - 70 is -70, which on a 72 degree period is the same as +2."""
        rz = service(sign=1, slot=0.0).to_pose(detection(Shape.STAR, 70.0)).rz
        self.assertAlmostEqual(rz, 2.0, places=6)
        square = service(sign=1, slot=0.0).to_pose(detection(Shape.SQUARE, 70.0)).rz
        self.assertAlmostEqual(square, 20.0, places=6)   # 90, not 72

    def test_an_offset_shifts_the_turn(self):
        plain = service(sign=1, slot=10.0).to_pose(detection(Shape.SQUARE, 0.0)).rz
        shifted = service(sign=1, slot=10.0, offset=5.0).to_pose(
            detection(Shape.SQUARE, 0.0)).rz
        self.assertAlmostEqual(shifted - plain, 5.0, places=6)

    def test_a_circle_is_never_rotated(self):
        pose = service(sign=-1, slot=45.0).to_pose(detection(Shape.CIRCLE, 33.0))
        self.assertEqual(pose.rz, 0.0)

    def test_an_untrusted_angle_is_treated_as_zero(self):
        weak = detection(Shape.SQUARE, 30.0, confidence=0.01)
        pose = service(sign=1, slot=45.0).to_pose(weak)
        # measured discarded, so the turn is the slot angle alone
        self.assertAlmostEqual(pose.rz, 45.0, places=6)


class TestTheRestOfThePose(unittest.TestCase):

    def test_z_is_always_zero_because_the_robot_owns_the_height(self):
        self.assertEqual(service().to_pose(detection(Shape.SQUARE, 0.0)).z, 0.0)

    def test_x_and_y_come_from_the_mapper(self):
        pose = service().to_pose(detection(Shape.SQUARE, 0.0))
        self.assertEqual((pose.x, pose.y), (100.0, 200.0))


if __name__ == "__main__":
    unittest.main()
