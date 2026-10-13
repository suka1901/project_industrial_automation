"""The camera must ask for its whole sensor, every time it opens.

A crop stored in the camera survives a power cycle, and a cropped image is
indistinguishable from a longer lens: the table simply looks closer. These
tests stand in for a camera, since pypylon is not installed off the station.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import logging
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.camera.camera import Camera
from tools.preflight import FAIL, PASS, judge_field_of_view


class Node:
    """One camera setting, as pypylon presents it."""

    def __init__(self, value, maximum=None, writable=True):
        self.value = value
        self.maximum = maximum if maximum is not None else value
        self.writable = writable

    def GetValue(self):
        return self.value

    def GetMax(self):
        return self.maximum

    def SetValue(self, value):
        if not self.writable:
            raise RuntimeError("node is locked")
        self.value = value


class FakeCamera:
    """A camera with a crop and binning left behind by somebody else."""

    def __init__(self, **nodes):
        for name, node in nodes.items():
            setattr(self, name, node)

    def __getattr__(self, name):
        # pypylon raises for a node this model does not have, rather than
        # returning None - which is what the code under test has to survive.
        raise RuntimeError(f"no node named {name}")


def cropped_camera():
    return FakeCamera(
        Width=Node(1280, 2448), Height=Node(1024, 2048),
        OffsetX=Node(584), OffsetY=Node(512),
        BinningHorizontal=Node(2), BinningVertical=Node(2),
    )


class TestTheFullSensorIsRequested(unittest.TestCase):
    def test_a_crop_is_undone(self):
        camera = cropped_camera()
        Camera()._use_full_sensor(camera)
        self.assertEqual((camera.Width.value, camera.Height.value), (2448, 2048))

    def test_the_offsets_come_down_first(self):
        """Width cannot grow while the offset still pushes it off the sensor."""
        camera = cropped_camera()
        Camera()._use_full_sensor(camera)
        self.assertEqual((camera.OffsetX.value, camera.OffsetY.value), (0, 0))

    def test_binning_is_reset(self):
        camera = cropped_camera()
        Camera()._use_full_sensor(camera)
        self.assertEqual((camera.BinningHorizontal.value,
                          camera.BinningVertical.value), (1, 1))

    def test_a_model_without_those_nodes_is_fine(self):
        """Models differ; a missing node must not stop the camera opening."""
        camera = FakeCamera(Width=Node(2448, 2448), Height=Node(2048, 2048))
        Camera()._use_full_sensor(camera)       # must not raise
        self.assertEqual(camera.Width.value, 2448)

    def test_a_camera_that_refuses_to_widen_says_so(self):
        camera = FakeCamera(Width=Node(1280, 2448, writable=False),
                            Height=Node(1024, 2048, writable=False),
                            OffsetX=Node(0), OffsetY=Node(0))
        with self.assertLogs("adapters.camera.camera", level=logging.WARNING) as logged:
            Camera()._use_full_sensor(camera)
        self.assertIn("cropped", "\n".join(logged.output))


class TestWhatItReports(unittest.TestCase):
    def test_the_whole_sensor_is_named_as_such(self):
        camera = FakeCamera(Width=Node(2448, 2448), Height=Node(2048, 2048))
        self.assertIn("whole sensor", Camera()._describe_area(camera))

    def test_a_crop_is_called_a_crop(self):
        camera = FakeCamera(Width=Node(1280, 2448), Height=Node(1024, 2048))
        self.assertIn("CROPPED", Camera()._describe_area(camera))

    def test_an_unknown_camera_is_not_guessed_at(self):
        self.assertEqual(Camera()._describe_area(FakeCamera()), "area unknown")


if __name__ == "__main__":
    unittest.main()


class TestTheFieldOfViewIsJudged(unittest.TestCase):
    """What has to fit is the SHEET. The jig is taught on the robot and, being
    a set of angles, can be measured by sliding it into view without turning
    it - so a frame that misses the jig is not a fault."""

    def test_a_frame_that_covers_the_sheet_passes(self):
        status, detail = judge_field_of_view(2448, 2048, 4.65, (337.0, 460.0))
        self.assertEqual(status, PASS)
        self.assertIn("covers", detail)

    def test_the_sheet_may_lie_either_way_round(self):
        status, _ = judge_field_of_view(2048, 2448, 4.65, (337.0, 460.0))
        self.assertEqual(status, PASS)

    def test_a_frame_that_misses_part_of_the_sheet_fails_with_the_shortfall(self):
        status, detail = judge_field_of_view(1280, 1024, 4.65, (337.0, 460.0))
        self.assertEqual(status, FAIL)
        self.assertIn("short by", detail)

    def test_without_a_sheet_size_it_only_reports(self):
        status, detail = judge_field_of_view(2448, 2048, 4.65, None)
        self.assertEqual(status, PASS)
        self.assertIn("mm", detail)
