"""Tests for the submission builder.

The course does not forgive a malformed hand-in: wrong pattern, not assessed,
no resubmission. So the rules that decide what goes in - and the refusals that
stop a zip going out incomplete - are pinned here rather than trusted.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import make_submission as builder


class TestWhatIsShipped(unittest.TestCase):
    def test_build_leftovers_are_not_shipped(self):
        for junk in ("pi/__pycache__/main.cpython-310.pyc", "pi/main.pyc",
                     "pi/logs/ina700.log", "model/dataset/raw/star_0001.png"):
            with self.subTest(junk=junk):
                self.assertFalse(builder.is_wanted(ROOT / junk))

    def test_the_program_and_the_model_are(self):
        files = builder.wanted_files()
        shipped = {path.as_posix() for path in files}
        self.assertIn("pi/main.py", shipped)
        self.assertIn("robot/MainModule.mod", shipped)
        self.assertIn("model/best.pt", shipped)
        self.assertIn("LAB.md", shipped)

    def test_the_dataset_stays_out(self):
        """2.1 GB of camera frames is not a program file."""
        self.assertFalse([p for p in builder.wanted_files() if "dataset" in p.parts])


class TestItRefusesAnIncompleteHandIn(unittest.TestCase):
    def test_a_missing_pack_and_go_is_named(self):
        missing = builder.missing_requirements(builder.wanted_files(), None)
        self.assertTrue(any("Pack-and-Go" in item for item in missing))

    def test_a_missing_model_is_named(self):
        files = [Path("pi/main.py"), Path("robot/MainModule.mod")]
        missing = builder.missing_requirements(files, Path("station.pgz"))
        self.assertTrue(any("model" in item for item in missing))

    def test_a_complete_build_has_nothing_missing(self):
        self.assertEqual(
            builder.missing_requirements(builder.wanted_files(), Path("station.pgz")),
            [])

    def test_the_file_name_is_not_negotiable(self):
        """A wrong name is reported as failed, so it is refused here instead."""
        argv = sys.argv
        sys.argv = ["make_submission.py", "--allow-missing", "--skip-tests",
                    "--out", str(ROOT / "INA700_final.zip")]
        try:
            self.assertEqual(builder.main(), 1)
        finally:
            sys.argv = argv
        self.assertFalse((ROOT / "INA700_final.zip").exists())


class TestThePackAndGoIsFound(unittest.TestCase):
    def test_an_explicit_file_is_used(self):
        self.assertEqual(builder.find_pack_and_go(str(ROOT / "LAB.md")),
                         ROOT / "LAB.md")

    def test_a_path_that_is_not_there_is_not_invented(self):
        self.assertIsNone(builder.find_pack_and_go(str(ROOT / "no_such.pgz")))

    def test_the_newest_in_the_folder_wins(self):
        """Re-exporting during the exam and running again must ship the new one."""
        import tempfile, time
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / builder.PACK_AND_GO_FOLDER
            folder.mkdir()
            (folder / "morning.pgz").write_text("old")
            time.sleep(0.01)
            (folder / "after_the_exam.pgz").write_text("new")
            self.assertEqual(builder.find_pack_and_go(None, root).name,
                             "after_the_exam.pgz")


if __name__ == "__main__":
    unittest.main()
