"""Tests for the two ways of asking for a pick that are not the view.

Tk owns the main thread, so on the Pi the terminal prompt cannot also be a
view - it is a source feeding the same queue. Both sources exist so the
window and the terminal can be live at once.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import io
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.enums import Colour, Shape
from adapters.gui.command_sources import (PipeCommandReader,
                                          TerminalCommandReader, dispatch)

ALLOWED = [Shape.CIRCLE, Shape.SQUARE, Shape.STAR]
# A CEILING, not a delay: wait_for returns as soon as the count arrives, so
# a generous value costs a passing run nothing and stops the whole suite going
# red when the machine is loaded. 1.5 s was enough alone and not enough when
# 240 other tests were running beside it.
SETTLE_S = 5.0


def wait_for(seen, count, seconds=SETTLE_S):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and len(seen) < count:
        time.sleep(0.02)
    return len(seen)


class TestBothSourcesRefuseTheSameThings(unittest.TestCase):
    """One dispatch, so a typo is refused identically wherever it was typed."""

    def test_a_valid_line_is_queued(self):
        seen = []
        self.assertTrue(dispatch("circle red", ALLOWED, seen.append, "a test"))
        self.assertEqual(seen[0].shape, Shape.CIRCLE)
        self.assertEqual(seen[0].colour, Colour.RED)

    def test_a_shape_this_cell_does_not_handle_is_refused(self):
        seen = []
        self.assertFalse(dispatch("hexagon", ALLOWED, seen.append, "a test"))
        self.assertEqual(seen, [])

    def test_a_blank_line_queues_nothing(self):
        seen = []
        self.assertFalse(dispatch("   ", ALLOWED, seen.append, "a test"))


class TestTheTerminalStaysLiveBesideTheWindow(unittest.TestCase):

    def reader(self, text, on_close=None):
        seen = []
        source = TerminalCommandReader(ALLOWED, seen.append, on_close=on_close,
                                       stream=io.StringIO(text))
        self.assertTrue(source.start())
        return source, seen

    def test_typed_lines_become_requests(self):
        source, seen = self.reader("circle red\nsquare\n")
        self.assertEqual(wait_for(seen, 2), 2)
        self.assertEqual([r.shape for r in seen], [Shape.CIRCLE, Shape.SQUARE])
        source.stop()

    def test_a_typo_does_not_stop_the_next_command(self):
        source, seen = self.reader("banana\nstar\n")
        self.assertEqual(wait_for(seen, 1), 1)
        self.assertEqual(seen[0].shape, Shape.STAR)
        source.stop()

    def test_quit_closes_the_system(self):
        closed = []
        source, seen = self.reader("quit\ncircle\n",
                                   on_close=lambda: closed.append(True))
        deadline = time.monotonic() + SETTLE_S
        while time.monotonic() < deadline and not closed:
            time.sleep(0.02)
        self.assertEqual(closed, [True])
        self.assertEqual(seen, [], "commands after quit must not run")
        source.stop()

    def test_a_redirected_stdin_is_refused_rather_than_dying_silently(self):
        """Launched from a desktop icon, stdin is not a terminal."""
        source = TerminalCommandReader(ALLOWED, lambda request: None)
        stdin = sys.stdin
        try:
            sys.stdin = io.StringIO("circle\n")      # a StringIO is not a tty
            self.assertFalse(source.start())
        finally:
            sys.stdin = stdin
        source.stop()


@unittest.skipUnless(hasattr(os, "mkfifo"), "named pipes are POSIX only")
class TestCommandsArriveThroughThePipe(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(Path(self.folder.name) / "cmd")
        self.seen = []
        self.reader = PipeCommandReader(self.path, ALLOWED, self.seen.append)
        self.assertTrue(self.reader.start())

    def tearDown(self):
        self.reader.stop()
        self.folder.cleanup()

    def send(self, text):
        with open(self.path, "w", encoding="utf-8") as pipe:
            pipe.write(text + "\n")

    def test_the_pipe_is_created_if_it_does_not_exist(self):
        self.assertTrue(os.path.exists(self.path))

    def test_a_valid_line_becomes_a_request(self):
        self.send("circle red")
        self.assertEqual(wait_for(self.seen, 1), 1)
        self.assertEqual(self.seen[0].shape, Shape.CIRCLE)

    def test_the_writer_closing_does_not_end_the_reader(self):
        """Each echo is a separate writer, so the pipe hits EOF every time."""
        self.send("circle red")
        self.assertEqual(wait_for(self.seen, 1), 1)
        self.send("square blue")
        self.assertEqual(wait_for(self.seen, 2), 2)
        self.assertEqual(self.seen[1].shape, Shape.SQUARE)

    def test_a_bad_line_is_dropped_and_the_next_one_still_works(self):
        self.send("banana")
        time.sleep(0.3)
        self.send("star")
        self.assertEqual(wait_for(self.seen, 1), 1)
        self.assertEqual(self.seen[0].shape, Shape.STAR)

    def test_several_commands_in_one_write_all_arrive(self):
        with open(self.path, "w", encoding="utf-8") as pipe:
            pipe.write("circle\nsquare\nstar\n")
        self.assertEqual(wait_for(self.seen, 3), 3)


@unittest.skipUnless(hasattr(os, "mkfifo"), "named pipes are POSIX only")
class TestItFailsQuietlyRatherThanCrashing(unittest.TestCase):

    def test_an_unwritable_location_reports_false_rather_than_raising(self):
        reader = PipeCommandReader("/proc/definitely/not/here/cmd",
                                   ALLOWED, lambda request: None)
        self.assertFalse(reader.start())
        reader.stop()          # must be safe after a failed start


if __name__ == "__main__":
    unittest.main()
