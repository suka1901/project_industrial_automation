"""Tests for the split between what the terminal shows and what the file keeps.

The console view is a prompt the operator types into. A 10 fps pipeline
logging at INFO writes over their half-typed command, so on the Pi the
terminal has to be quieter than the log file.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import logging
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.logging_setup import configure_logging


def handlers():
    stream = [h for h in logging.getLogger().handlers
              if isinstance(h, logging.StreamHandler)
              and not isinstance(h, logging.FileHandler)]
    files = [h for h in logging.getLogger().handlers
             if isinstance(h, logging.FileHandler)]
    return stream[0], (files[0] if files else None)


def release_handlers():
    """Close and detach every root handler.

    Windows will not delete a file another handle still holds open, and
    configure_logging leaves a FileHandler on the log. On Linux the temporary
    directory cleans up regardless; on Windows it fails with WinError 32 and
    the test goes red for a reason that has nothing to do with logging levels.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        try:
            handler.close()
        except Exception:
            pass
        root.removeHandler(handler)


class TestTheTerminalCanBeQuieterThanTheFile(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()

    def tearDown(self):
        # Order matters: release the file before the directory is removed.
        release_handlers()
        logging.basicConfig(force=True)
        release_handlers()
        self.folder.cleanup()

    def test_without_a_console_level_both_match(self):
        configure_logging(level="INFO")
        stream, _ = handlers()
        self.assertEqual(stream.level, logging.INFO)

    def test_the_console_can_be_raised_on_its_own(self):
        configure_logging(level="INFO",
                          log_file=str(Path(self.folder.name) / "a.log"),
                          console_level="WARNING")
        stream, file_handler = handlers()
        self.assertEqual(stream.level, logging.WARNING)
        self.assertEqual(file_handler.level, logging.INFO)

    def test_the_root_still_passes_info_through_to_the_file(self):
        """The trap: set the root to WARNING and the file never sees INFO."""
        path = Path(self.folder.name) / "b.log"
        configure_logging(level="INFO", log_file=str(path),
                          console_level="WARNING")
        logging.getLogger("probe").info("kept in the file")
        release_handlers()
        self.assertIn("kept in the file", path.read_text(encoding="utf-8"))

    def test_a_console_quieter_than_the_file_does_not_silence_warnings(self):
        configure_logging(level="INFO",
                          log_file=str(Path(self.folder.name) / "c.log"),
                          console_level="WARNING")
        stream, _ = handlers()
        record = logging.LogRecord("x", logging.WARNING, "", 1, "hi", None, None)
        self.assertTrue(stream.filter(record))
        self.assertGreaterEqual(logging.WARNING, stream.level)


class TestTheLogFileIsReleased(unittest.TestCase):
    """Windows cannot delete a file another handle holds open.

    This is the portable half of that: assert the handler's stream is actually
    closed. On Linux the temporary directory would clean up either way, so
    without this the bug is invisible until someone runs the suite on Windows.
    """

    def tearDown(self):
        release_handlers()
        logging.basicConfig(force=True)
        release_handlers()

    def test_closing_the_handlers_closes_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            configure_logging(level="INFO",
                              log_file=str(Path(folder) / "held.log"))
            _, file_handler = handlers()
            # Hold the stream: close() sets handler.stream to None, so asking
            # the handler afterwards tells you nothing about the file.
            stream = file_handler.stream
            self.assertFalse(stream.closed)
            release_handlers()
            self.assertTrue(stream.closed,
                            "the log file is still open - Windows will refuse "
                            "to delete the directory holding it")
            self.assertIsNone(file_handler.stream)

    def test_nothing_is_left_attached_to_the_root(self):
        with tempfile.TemporaryDirectory() as folder:
            configure_logging(level="INFO",
                              log_file=str(Path(folder) / "held.log"))
            release_handlers()
            self.assertEqual(logging.getLogger().handlers, [])


if __name__ == "__main__":
    unittest.main()
