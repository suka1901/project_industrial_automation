"""Shapes and colours, with the symmetry each shape has.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from enum import Enum


class Shape(Enum):
    """The five object shapes used in the course."""

    CIRCLE = "CIRCLE"
    SQUARE = "SQUARE"
    TRIANGLE = "TRIANGLE"
    STAR = "STAR"
    HEXAGON = "HEXAGON"

    @property
    def symmetry_period_deg(self) -> float:
        """Smallest rotation, in degrees, that maps the shape onto itself."""
        return {
            Shape.CIRCLE: 0.0,     # infinite symmetry - any angle fits
            Shape.SQUARE: 90.0,    # 4-fold
            Shape.TRIANGLE: 120.0,  # 3-fold
            Shape.STAR: 72.0,      # 5-fold (five-pointed star)
            Shape.HEXAGON: 60.0,   # 6-fold
        }[self]

    @property
    def symmetry_order(self) -> int:
        """How many times the shape maps onto itself in a full turn."""
        return {
            Shape.CIRCLE: 0,
            Shape.SQUARE: 4,
            Shape.TRIANGLE: 3,
            Shape.STAR: 5,
            Shape.HEXAGON: 6,
        }[self]

    @property
    def is_rotationally_free(self) -> bool:
        """True when the shape can be placed at any angle (the circle)."""
        return self.symmetry_period_deg == 0.0

    @classmethod
    def from_name(cls, name: str) -> "Shape":
        """Build a Shape from a case-insensitive string, as used in config files."""
        return cls[name.strip().upper()]


class Colour(Enum):
    """Object colours the vision system can distinguish."""

    RED = "RED"
    GREEN = "GREEN"
    BLUE = "BLUE"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_name(cls, name: str) -> "Colour":
        """Build a Colour from a case-insensitive string, defaulting to UNKNOWN."""
        try:
            return cls[name.strip().upper()]
        except KeyError:
            return cls.UNKNOWN


class CycleOutcome(Enum):
    """Result reported back by the robot after it attempts a pick and place."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
