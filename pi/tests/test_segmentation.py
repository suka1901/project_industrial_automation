"""Tests for separating an object from the paper inside a detection box.

The polarity decision used to read one pixel at the centre of the crop. A
specular highlight landing on that pixel inverted the mask on every star, so
the orientation estimator was handed the paper - a rectangle - and correctly
reported that a rectangle has no five-fold structure. These tests pin the
decision to thousands of pixels instead of one.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from typing import Any
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.detection.segmentation import (covers_whole_crop, gradient_mask,
                                             looks_like_paper, object_mask,
                                             plausibility)

SIZE = 140
CENTRE = SIZE // 2


def star(dark_on_light=True, points=5, speck=None, speck_radius=5):
    """A five-pointed star centred in a crop, with optional specular highlight.

    The highlight is a small disc, not a single pixel: the mask is built from
    a Gaussian-blurred crop, which erases one pixel but not the few-millimetre
    glare a lamp actually leaves on a glossy object.
    """
    paper, ink = (235, 40) if dark_on_light else (40, 235)
    img: Any = np.full((SIZE, SIZE, 3), paper, np.uint8)
    pts = []
    for k in range(2 * points):
        radius = 60.0 if k % 2 == 0 else 27.0
        angle = k * np.pi / points
        pts.append((CENTRE + radius * np.cos(angle),
                    CENTRE + radius * np.sin(angle)))
    cv2.fillPoly(img, [np.array(pts).round().astype(np.int32)], (ink, ink, ink))
    if speck is not None:
        cv2.circle(img, (CENTRE, CENTRE), speck_radius, (speck, speck, speck), -1)
    return img


def object_share(mask):
    """How much of the crop's middle third the mask claims."""
    middle = mask[SIZE // 3:SIZE - SIZE // 3, SIZE // 3:SIZE - SIZE // 3]
    return float(np.count_nonzero(middle)) / middle.size


class TestPicksTheObjectNotThePaper(unittest.TestCase):

    def test_a_dark_object_on_light_paper(self):
        mask = object_mask(star(dark_on_light=True))
        self.assertGreater(object_share(mask), 0.9)

    def test_a_light_object_on_dark_paper(self):
        mask = object_mask(star(dark_on_light=False))
        self.assertGreater(object_share(mask), 0.9)

    def test_the_border_is_paper_either_way(self):
        for dark in (True, False):
            mask = object_mask(star(dark_on_light=dark))
            edges = np.concatenate([mask[0, :], mask[-1, :],
                                    mask[:, 0], mask[:, -1]])
            self.assertLess(np.count_nonzero(edges) / edges.size, 0.05)


class TestOnePixelCannotInvertTheMask(unittest.TestCase):
    """The regression. A highlight at the crop centre used to flip everything."""

    def test_glare_at_the_centre_of_a_dark_object(self):
        mask = object_mask(star(dark_on_light=True, speck=255))
        self.assertGreater(object_share(mask), 0.8,
                           "a highlight at the crop centre inverted the mask")

    def test_a_dark_mark_at_the_centre_of_a_light_object(self):
        mask = object_mask(star(dark_on_light=False, speck=0))
        self.assertGreater(object_share(mask), 0.8,
                           "a dark mark at the crop centre inverted the mask")

    def test_it_survives_glare_large_enough_to_see(self):
        for radius in (3, 5, 8, 12):
            with self.subTest(radius=radius):
                mask = object_mask(star(speck=255, speck_radius=radius))
                self.assertGreater(object_share(mask), 0.7)

    def test_the_five_fold_structure_survives_the_speck(self):
        """What the bug actually cost: the star stopped being a star."""
        from domain.orientation import harmonic_orientation, resample_radial
        import math

        def confidence(image):
            mask = object_mask(image)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_NONE)
            outline = max(contours, key=cv2.contourArea).reshape(-1, 2)
            moments = cv2.moments(max(contours, key=cv2.contourArea))
            cx = moments["m10"] / moments["m00"]
            cy = moments["m01"] / moments["m00"]
            radii = resample_radial([(math.atan2(y - cy, x - cx),
                                      math.hypot(x - cx, y - cy))
                                     for x, y in outline])
            assert radii is not None, "the outline gave no radial signature"
            return harmonic_orientation(radii, 5)[1]

        clean = confidence(star(dark_on_light=True))
        specked = confidence(star(dark_on_light=True, speck=255))
        self.assertGreater(clean, 0.10)
        self.assertGreater(specked, 0.10)
        self.assertAlmostEqual(clean, specked, delta=0.03)


class TestPlausibility(unittest.TestCase):

    def test_an_object_scores_high_and_its_inverse_scores_low(self):
        mask = object_mask(star())
        self.assertGreater(plausibility(mask), 0.8)
        self.assertLess(plausibility(cv2.bitwise_not(mask)), -0.8)

    def test_a_full_mask_is_recognised_as_the_whole_crop(self):
        full = np.full((SIZE, SIZE), 255, np.uint8)
        self.assertTrue(covers_whole_crop(SIZE * SIZE, full))

    def test_a_real_object_is_not(self):
        mask = object_mask(star())
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_NONE)
        area = cv2.contourArea(max(contours, key=cv2.contourArea))
        self.assertFalse(covers_whole_crop(area, mask))


class TestTellingThePaperFromTheObject(unittest.TestCase):
    """The whole-crop test one size smaller, and the one that was missing.

    A mask of the paper does not always reach the corners: clean_mask fills
    the hole the object leaves in it, and what remains can sit comfortably
    under WHOLE_CROP_FRACTION. It is still a rectangle, and a rectangle fits
    an ideal SQUARE well enough to be believed - which is how a wrong angle
    reached the robot with a good score behind it. The crop is the detection
    box plus padding, so only the paper can touch its border.
    """

    def test_a_mask_that_reaches_every_edge_is_paper(self):
        paper = np.full((SIZE, SIZE), 255, np.uint8)
        paper[30:SIZE - 30, 30:SIZE - 30] = 0      # the object's own hole
        self.assertTrue(looks_like_paper(paper))

    def test_it_is_still_paper_once_the_hole_is_filled(self):
        paper = np.full((SIZE, SIZE), 255, np.uint8)
        self.assertTrue(looks_like_paper(paper))

    def test_an_object_inside_its_padding_is_not(self):
        self.assertFalse(looks_like_paper(object_mask(star())))

    def test_nor_is_a_square_that_nearly_fills_its_box(self):
        mask = np.zeros((SIZE, SIZE), np.uint8)
        mask[6:SIZE - 6, 6:SIZE - 6] = 255
        self.assertFalse(looks_like_paper(mask))


class TestTheGradientRouteFindsAPaleObject(unittest.TestCase):
    """The route that has to answer when brightness cannot.

    Thresholding the gradient with Otsu split the magnitudes into halves of
    similar weight, which on a pale object kept only the brightest fraction
    of the border - too little to fill. A percentile names the border's own
    share of the crop instead.
    """

    def test_a_pale_square_is_found_by_its_border(self):
        crop = np.full((SIZE, SIZE, 3), 200, np.uint8)
        crop[20:SIZE - 20, 20:SIZE - 20] = 215     # 15 grey levels, no more
        mask = gradient_mask(crop)
        covered = float(np.count_nonzero(mask)) / float(mask.size)
        self.assertGreater(covered, 0.2)
        self.assertLess(covered, 0.9)
        self.assertFalse(looks_like_paper(mask))


if __name__ == "__main__":
    unittest.main()
