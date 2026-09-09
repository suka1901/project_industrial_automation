"""Tests for the pieces ultralytics used to do for us.

The Pi runs the model through ncnn to avoid torch, which means the
letterboxing on the way in and the suppression on the way out are ours to get
right. Both are pure geometry and testable without the model or the runtime.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from domain.enums import Shape
from adapters.detection.ncnn_detector import NcnnDetector, PAD_VALUE

CLASS_MAP = {0: Shape.CIRCLE, 1: Shape.SQUARE, 2: Shape.STAR}


def detector(size=640):
    return NcnnDetector("unused", CLASS_MAP, image_size=size)


class TestLetterbox(unittest.TestCase):
    """Aspect ratio must survive: the orientation estimator reads these
    outlines later, and a stretched star has no five-fold symmetry left."""

    def test_output_is_square_at_the_model_size(self):
        canvas, _, _, _ = detector().letterbox_for_test(np.zeros((1071, 1280, 3), np.uint8))
        self.assertEqual(canvas.shape, (640, 640, 3))

    def test_a_wide_image_is_padded_top_and_bottom(self):
        _, scale, left, top = detector().letterbox_for_test(np.zeros((1071, 1280, 3), np.uint8))
        self.assertAlmostEqual(scale, 640 / 1280, places=4)
        self.assertEqual(left, 0)
        self.assertGreater(top, 0)

    def test_a_tall_image_is_padded_left_and_right(self):
        _, scale, left, top = detector().letterbox_for_test(np.zeros((1280, 640, 3), np.uint8))
        self.assertAlmostEqual(scale, 640 / 1280, places=4)
        self.assertGreater(left, 0)
        self.assertEqual(top, 0)

    def test_a_square_image_needs_no_padding(self):
        _, _, left, top = detector().letterbox_for_test(np.zeros((500, 500, 3), np.uint8))
        self.assertEqual((left, top), (0, 0))

    def test_the_padding_is_the_grey_the_model_was_trained_with(self):
        canvas, _, _, top = detector().letterbox_for_test(np.zeros((1071, 1280, 3), np.uint8))
        self.assertTrue((canvas[0, 0] == PAD_VALUE).all())
        self.assertTrue((canvas[top + 5, 5] == 0).all(), "the image itself must survive")

    def test_the_transform_round_trips_a_point(self):
        """A detection at the centre of the canvas must map to the centre of
        the original frame - this is the arithmetic detect() undoes."""
        image = np.zeros((1071, 1280, 3), np.uint8)
        _, scale, left, top = detector().letterbox_for_test(image)
        x = (320 - left) / scale
        y = (320 - top) / scale
        self.assertAlmostEqual(x, 640.0, delta=1.0)
        self.assertAlmostEqual(y, 535.5, delta=1.0)


class TestSuppression(unittest.TestCase):
    """One object fires several neighbouring anchors. Without suppression the
    cycle picks at a duplicate that is not quite where the object is."""

    def _keep(self, boxes, scores, threshold=0.45):
        return NcnnDetector._suppress(np.array(boxes, float), np.array(scores, float), threshold)

    def test_a_lone_box_survives(self):
        self.assertEqual(self._keep([[0, 0, 10, 10]], [0.9]), [0])

    def test_the_highest_scoring_of_a_cluster_wins(self):
        keep = self._keep([[0, 0, 10, 10], [1, 1, 11, 11], [2, 2, 12, 12]], [0.7, 0.9, 0.6])
        self.assertEqual(keep, [1])

    def test_separate_objects_both_survive(self):
        keep = self._keep([[0, 0, 10, 10], [50, 50, 60, 60]], [0.9, 0.8])
        self.assertEqual(sorted(keep), [0, 1])

    def test_boxes_touching_but_not_overlapping_both_survive(self):
        self.assertEqual(len(self._keep([[0, 0, 10, 10], [10, 0, 20, 10]], [0.9, 0.8])), 2)

    def test_an_empty_frame_keeps_nothing(self):
        self.assertEqual(self._keep([], []), [])

    def test_a_stricter_threshold_removes_more(self):
        # Overlap 6x10=60, union 140, so IoU is 0.43. A box is suppressed when
        # its IoU EXCEEDS the threshold, so 0.45 spares it and 0.30 does not.
        boxes = [[0, 0, 10, 10], [4, 0, 14, 10]]
        self.assertEqual(len(self._keep(boxes, [0.9, 0.8], threshold=0.45)), 2)
        self.assertEqual(len(self._keep(boxes, [0.9, 0.8], threshold=0.30)), 1)


if __name__ == "__main__":
    unittest.main()
