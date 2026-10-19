"""Tests for profile loading and the deep merge.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.config_loader import load_config, merge


class TestMerge(unittest.TestCase):
    def test_override_wins(self):
        self.assertEqual(merge({"a": 1}, {"a": 2}), {"a": 2})

    def test_nested_keys_survive(self):
        """A profile changing one key must not wipe its siblings."""
        base = {"camera": {"kind": "basler", "exposure_us": 3000, "gain": 0.0}}
        got = merge(base, {"camera": {"kind": "file"}})
        self.assertEqual(got["camera"],
                         {"kind": "file", "exposure_us": 3000, "gain": 0.0})

    def test_inputs_are_not_modified(self):
        base = {"a": {"b": 1}}
        merge(base, {"a": {"b": 2}})
        self.assertEqual(base, {"a": {"b": 1}})


class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def _write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_profile_extends_the_base(self):
        self._write("config.yaml", "camera:\n  kind: basler\n  gain: 0.0\nrobot:\n  transport: tcp\n")
        profile = self._write("profiles/p.yaml",
                              "extends: ../config.yaml\ncamera:\n  kind: file\n")
        config = load_config(profile)
        self.assertEqual(config["camera"], {"kind": "file", "gain": 0.0})
        self.assertEqual(config["robot"]["transport"], "tcp")
        self.assertNotIn("extends", config)

    def test_a_file_with_no_extends_loads_alone(self):
        base = self._write("config.yaml", "a: 1\n")
        self.assertEqual(load_config(base), {"a": 1})

    def test_circular_extends_is_rejected(self):
        self._write("a.yaml", "extends: b.yaml\n")
        b = self._write("b.yaml", "extends: a.yaml\n")
        with self.assertRaises(ValueError):
            load_config(b)


if __name__ == "__main__":
    unittest.main()


class TestTheProfilesAgreeWithTheHardwareTheyRunOn(unittest.TestCase):
    """Settings that are right on the station and wrong off it.

    The camera check after a pick is the clearest: on the bench it is what
    makes a retry real, and against a saved photo - where nothing the robot
    "picks" ever leaves the board - it would call every pick a failure and
    break the one test you run before setting off.
    """

    CONFIG = Path(__file__).resolve().parents[1] / "config"

    def _robot(self, profile):
        return load_config(self.CONFIG / profile).get("robot", {})

    def test_the_lab_config_verifies_the_pick(self):
        self.assertGreaterEqual(self._robot("config.yaml")["verify_tolerance_mm"], 5.0)

    def test_the_still_photo_profiles_do_not(self):
        for profile in ("profiles/mock.yaml", "profiles/offline.yaml"):
            with self.subTest(profile=profile):
                self.assertEqual(self._robot(profile)["verify_tolerance_mm"], 0.0)

    def test_the_pi_profiles_keep_the_lab_setting(self):
        """pi.yaml overrides the detector and the view, not the cell."""
        for profile in ("profiles/pi.yaml", "profiles/pi-gui.yaml"):
            with self.subTest(profile=profile):
                self.assertGreaterEqual(
                    self._robot(profile)["verify_tolerance_mm"], 5.0)
