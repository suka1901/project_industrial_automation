"""Tests for the wire protocol.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest

from domain.enums import Colour, CycleOutcome, Shape
from domain.models import Detection, DetectedObject, PixelPoint, WorldPose
from adapters.comms.message_codec import MessageCodec, ProtocolError, RAPID_MAX_STRING


def make_object(shape=Shape.STAR, colour=Colour.RED,
                x=123.456, y=-45.3, z=12.0, rz=37.55):
    detection = Detection(
        shape=shape, colour=colour, confidence=0.9,
        centre=PixelPoint(100.0, 200.0), angle_deg=rz,
    )
    return DetectedObject(detection=detection, pose=WorldPose(x, y, z, rz))


class TestEncoding(unittest.TestCase):
    def setUp(self):
        self.codec = MessageCodec()

    def test_pick_message_format(self):
        message = self.codec.encode_pick(make_object())
        self.assertEqual(message, "move star 123.46 -45.30 37.5#")

    def test_shape_name_is_lower_case_for_the_robot_catalogue(self):
        message = self.codec.encode_pick(make_object(shape=Shape.TRIANGLE))
        self.assertIn(" triangle ", message)

    def test_colour_never_reaches_the_robot(self):
        # The operator types "circle red", but matching the colour is the
        # server's job - the robot only needs position and destination.
        message = self.codec.encode_pick(make_object(colour=Colour.RED))
        self.assertNotIn("RED", message.upper())

    def test_every_shape_fits_the_rapid_limit_at_extreme_values(self):
        for shape in Shape:
            message = self.codec.encode_pick(
                make_object(shape=shape, x=-1234.56, y=-1234.56, rz=-179.9)
            )
            self.assertLessEqual(len(message), RAPID_MAX_STRING, message)

    def test_quit(self):
        self.assertEqual(self.codec.encode_quit(), "quit#")


class TestDecoding(unittest.TestCase):
    def setUp(self):
        self.codec = MessageCodec()

    def test_success(self):
        self.assertIs(self.codec.decode_reply("DONE: circle#"), CycleOutcome.SUCCESS)
        self.assertIs(self.codec.decode_reply("done: circle"), CycleOutcome.SUCCESS)

    def test_unknown_shape_is_a_failure(self):
        self.assertIs(
            self.codec.decode_reply("ERROR: unknown shape 'blob'#"),
            CycleOutcome.FAILED,
        )

    def test_timeout_on_none(self):
        self.assertIs(self.codec.decode_reply(None), CycleOutcome.TIMEOUT)


if __name__ == "__main__":
    unittest.main()
