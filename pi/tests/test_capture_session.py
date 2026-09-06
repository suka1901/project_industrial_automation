"""Tests for dataset naming and counting.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.capture_session import MIXED, CaptureSession


class TestCaptureSession(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.session = CaptureSession(self.root, ["circle", "star", MIXED])
        self.session.prepare()

    def tearDown(self):
        self._temp.cleanup()

    def test_prepare_creates_one_folder_per_category(self):
        self.assertTrue((self.root / "circle").is_dir())
        self.assertTrue((self.root / "star").is_dir())
        self.assertTrue((self.root / "mixed").is_dir())

    def test_first_photo_is_numbered_one(self):
        self.assertEqual(self.session.next_path("circle").name, "circle_0001.png")

    def test_numbering_resumes_after_existing_photos(self):
        for index in (1, 2, 7):
            (self.root / "circle" / f"circle_{index:04d}.png").touch()
        # Continues from the highest existing number, never overwrites.
        self.assertEqual(self.session.next_path("circle").name, "circle_0008.png")

    def test_categories_are_counted_independently(self):
        (self.root / "circle" / "circle_0001.png").touch()
        (self.root / "circle" / "circle_0002.png").touch()
        (self.root / "star" / "star_0001.png").touch()
        counts = self.session.counts()
        self.assertEqual(counts["circle"], 2)
        self.assertEqual(counts["star"], 1)
        self.assertEqual(counts["mixed"], 0)

    def test_unnumbered_files_do_not_break_numbering(self):
        (self.root / "circle" / "notes.png").touch()
        self.assertEqual(self.session.next_path("circle").name, "circle_0001.png")

    def test_category_names_are_lower_cased(self):
        session = CaptureSession(self.root, ["CIRCLE"])
        self.assertEqual(session.categories, ["circle"])
        self.assertEqual(session.folder_for("CIRCLE"), self.root / "circle")

    def test_mixed_numbering_is_separate_from_the_shapes(self):
        (self.root / "circle" / "circle_0001.png").touch()
        self.assertEqual(self.session.next_path(MIXED).name, "mixed_0001.png")


if __name__ == "__main__":
    unittest.main()
