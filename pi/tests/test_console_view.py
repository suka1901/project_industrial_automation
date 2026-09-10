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
from adapters.gui.console_view import parse_request

ALLOWED = [Shape.CIRCLE, Shape.SQUARE, Shape.STAR]


def ask(text):
    return parse_request(text, ALLOWED)


class TestUnderstandsTheOperator(unittest.TestCase):

    def test_shape_and_colour(self):
        request, _ = ask("circle red")
        self.assertIs(request.shape, Shape.CIRCLE)
        self.assertIs(request.colour, Colour.RED)

    def test_order_does_not_matter(self):
        """Nobody should have to remember which word comes first."""
        a, _ = ask("circle red")
        b, _ = ask("red circle")
        self.assertEqual(a, b)

    def test_case_does_not_matter(self):
        request, _ = ask("Circle RED")
        self.assertIs(request.shape, Shape.CIRCLE)
        self.assertIs(request.colour, Colour.RED)

    def test_a_shape_alone_means_any_colour(self):
        request, _ = ask("star")
        self.assertIs(request.shape, Shape.STAR)
        self.assertIsNone(request.colour)

    def test_a_colour_alone_means_any_shape(self):
        request, _ = ask("blue")
        self.assertIsNone(request.shape)
        self.assertIs(request.colour, Colour.BLUE)

    def test_the_word_any_is_ignored(self):
        request, _ = ask("any red")
        self.assertIsNone(request.shape)
        self.assertIs(request.colour, Colour.RED)

    def test_extra_spaces_are_harmless(self):
        request, _ = ask("   circle    red   ")
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
