"""The rectangle on the table that objects may be picked from.

The camera sees more than the picking sheet - the jig is in frame too, so
that the slot angles can be measured where the objects actually lie. That
means objects already placed in the jig are detected exactly like objects
waiting on the sheet, and without this they would be offered as picking
candidates.

Pure geometry, in picking work object millimetres.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple


@dataclass(frozen=True)
class Rect:
    """An axis-aligned area in work object millimetres."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @classmethod
    def from_origin_and_span(cls, origin: Tuple[float, float],
                             span: Sequence[float], margin: float = 0.0) -> "Rect":
        """Build from a measured corner and a size, grown by ``margin``.

        The margin is generous rather than tight: it covers camera error near
        the sheet edge, and an object half on the paper is still on the table
        and still pickable. It only has to stay well clear of the jig.
        """
        return cls(origin[0] - margin, origin[1] - margin,
                   origin[0] + span[0] + margin, origin[1] + span[1] + margin)

    def contains(self, x: float, y: float) -> bool:
        return self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y
