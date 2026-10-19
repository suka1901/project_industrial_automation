"""Tests for the terminal operator interface.

The Pi is reached over SSH, where Tk cannot open a window at all. Typing
"circle red" has to work, and has to fail clearly when it cannot.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.enums import Colour, Shape
from domain.models import PickRequest, StateSnapshot
import threading
import time

from adapters.gui.console_view import ConsoleView, parse_request

ALLOWED = [Shape.CIRCLE, Shape.SQUARE, Shape.STAR]


def ask(text):
    return parse_request(text, ALLOWED)


def understood(text) -> PickRequest:
    """What the operator's words came to, for the words that parse.

    The refusal tests below use `ask` and look at the message instead.
    """
    request, _ = ask(text)
    assert request is not None
    return request


class TestUnderstandsTheOperator(unittest.TestCase):

    def test_shape_and_colour(self):
        request = understood("circle red")
        self.assertIs(request.shape, Shape.CIRCLE)
        self.assertIs(request.colour, Colour.RED)

    def test_order_does_not_matter(self):
        """Nobody should have to remember which word comes first."""
        a, _ = ask("circle red")
        b, _ = ask("red circle")
        self.assertEqual(a, b)

    def test_case_does_not_matter(self):
        request = understood("Circle RED")
        self.assertIs(request.shape, Shape.CIRCLE)
        self.assertIs(request.colour, Colour.RED)

    def test_a_shape_alone_means_any_colour(self):
        request = understood("star")
        self.assertIs(request.shape, Shape.STAR)
        self.assertIsNone(request.colour)

    def test_a_colour_alone_means_any_shape(self):
        request = understood("blue")
        self.assertIsNone(request.shape)
        self.assertIs(request.colour, Colour.BLUE)

    def test_the_word_any_is_ignored(self):
        request = understood("any red")
        self.assertIsNone(request.shape)
        self.assertIs(request.colour, Colour.RED)

    def test_extra_spaces_are_harmless(self):
        request = understood("   circle    red   ")
        self.assertIs(request.shape, Shape.CIRCLE)


class TestRefusesClearly(unittest.TestCase):
    """A refusal has to say what was wrong, or the operator retypes blindly."""

    def test_a_shape_this_cell_does_not_handle(self):
        request, message = ask("hexagon")
        self.assertIsNone(request)
        self.assertIn("hexagon", message)
        self.assertIn("circle", message, "it should say what IS handled")

    def test_a_word_that_is_neither(self):
        request, message = ask("banana")
        self.assertIsNone(request)
        self.assertIn("banana", message)

    def test_an_empty_line_is_not_an_error(self):
        """Pressing Enter should not scold you."""
        request, message = ask("   ")
        self.assertIsNone(request)
        self.assertEqual(message, "")

    def test_a_line_with_nothing_to_pick(self):
        request, message = ask("any")
        self.assertIsNone(request)
        self.assertIn("shape", message)

    def test_one_bad_word_rejects_the_whole_line(self):
        """Half-understanding 'circle banana' as 'circle' would pick the wrong
        thing while looking like it worked."""
        request, message = ask("circle banana")
        self.assertIsNone(request)
        self.assertIn("banana", message)


if __name__ == "__main__":
    unittest.main()


def idle() -> StateSnapshot:
    """What the watcher sees when nothing is happening."""
    return StateSnapshot(status_text="idle")


class TestTheRefreshSettingIsActuallyWired(unittest.TestCase):
    """gui.refresh_ms used to be accepted here and then ignored.

    The watcher slept a hard-coded 0.2 s, so on the Pi - which runs the console
    view - turning that config knob did nothing at all. These tests fail if it
    ever goes back to being decorative.
    """

    def _watch_for(self, refresh_ms, seconds):
        """Run the status watcher briefly and count how often it polled."""
        calls = []

        def provider():
            calls.append(time.monotonic())
            return idle()

        view = ConsoleView(
            allowed_shapes=ALLOWED,
            on_cycle_requested=lambda request: None,
            on_close=lambda: None,
            snapshot_provider=provider,
            refresh_ms=refresh_ms,
        )
        thread = threading.Thread(target=view._watch_status, daemon=True)
        thread.start()
        time.sleep(seconds)
        view._stop.set()
        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive(), "watcher did not stop")
        return len(calls)

    def test_a_short_interval_polls_more_often_than_a_long_one(self):
        fast = self._watch_for(20, 0.4)
        slow = self._watch_for(200, 0.4)
        # Deliberately loose: this asserts the setting is read at all, not that
        # the scheduler is precise.
        self.assertGreater(fast, slow)
        self.assertGreaterEqual(fast, 5)
        self.assertLessEqual(slow, 4)

    def test_stopping_does_not_wait_out_the_interval(self):
        """Waiting on the event, not sleeping, is what makes shutdown prompt."""
        view = ConsoleView(
            allowed_shapes=ALLOWED,
            on_cycle_requested=lambda request: None,
            on_close=lambda: None,
            snapshot_provider=idle,
            refresh_ms=5000,
        )
        thread = threading.Thread(target=view._watch_status, daemon=True)
        thread.start()
        time.sleep(0.05)
        started = time.monotonic()
        view._stop.set()
        thread.join(timeout=2.0)
        self.assertFalse(thread.is_alive(), "watcher slept through the stop")
        # Well under the old hard-coded 0.2 s sleep, so this fails if the
        # watcher ever goes back to sleeping instead of waiting on the event.
        self.assertLess(time.monotonic() - started, 0.1)

    def test_a_silly_interval_cannot_become_a_busy_loop(self):
        view = ConsoleView(
            allowed_shapes=ALLOWED,
            on_cycle_requested=lambda request: None,
            on_close=lambda: None,
            snapshot_provider=idle,
            refresh_ms=0,
        )
        self.assertGreaterEqual(view._poll_s, 0.02)
