"""Tests for reading the camera's exposure without being able to stop preflight.

The bug this closes: getattr(obj, name, None) only falls back to its default
on AttributeError. pypylon raises LogicalErrorException for a node that does
not exist, so the default never applied and the exception escaped - taking
down the whole pre-flight run at the lighting check, on a helper whose entire
job is "tell me the exposure if you happen to know it".

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.preflight import current_exposure_us


class Pylon:
    """A pypylon camera: attribute lookup RAISES for an unknown node."""

    def __getattr__(self, name):
        raise RuntimeError("Node not existing (file 'genicam_wrap.cpp')")


class WrappedPylon:
    """Our Camera adapter, holding one of those underneath."""

    def __init__(self):
        self._device = Pylon()


class Node:
    def __init__(self, value):
        self._value = value

    def GetValue(self):
        return self._value


class RealCamera:
    def __init__(self, value=11000.0):
        self.ExposureTime = Node(value)


class OlderCamera:
    """GigE cameras call it ExposureTimeAbs."""

    def __init__(self, value=9000.0):
        self.ExposureTimeAbs = Node(value)


class PlainAttribute:
    exposure_us = 7000.0


class TestItNeverRaises(unittest.TestCase):

    def test_a_camera_that_raises_on_every_lookup(self):
        self.assertIsNone(current_exposure_us(Pylon()))

    def test_one_nested_inside_our_adapter(self):
        self.assertIsNone(current_exposure_us(WrappedPylon()))

    def test_no_camera_at_all(self):
        self.assertIsNone(current_exposure_us(None))

    def test_an_object_that_knows_nothing(self):
        self.assertIsNone(current_exposure_us(object()))

    def test_a_node_that_raises_when_read(self):
        class Exploding:
            class _Node:
                def GetValue(self):
                    raise RuntimeError("access denied")
            ExposureTime = _Node()
        self.assertIsNone(current_exposure_us(Exploding()))


class TestItStillReadsTheValue(unittest.TestCase):
    """Guarding everything must not mean answering None to everything."""

    def test_a_usb_camera(self):
        self.assertEqual(current_exposure_us(RealCamera()), 11000.0)

    def test_an_older_gige_camera(self):
        self.assertEqual(current_exposure_us(OlderCamera()), 9000.0)

    def test_a_plain_attribute(self):
        self.assertEqual(current_exposure_us(PlainAttribute()), 7000.0)

    def test_one_found_through_a_hostile_wrapper(self):
        class Adapter:
            def __init__(self):
                self._device = RealCamera()
            def __getattr__(self, name):
                raise RuntimeError("Node not existing")
        self.assertEqual(current_exposure_us(Adapter()), 11000.0)


if __name__ == "__main__":
    unittest.main()
