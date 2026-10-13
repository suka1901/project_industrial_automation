"""Print-ready A3 sheet with a 100 mm ArUco marker at the exact centre.

The point of printing the marker onto the sheet is that its position stops
being something to measure: the sheet corner is wobj1's origin, the sheet
edges are wobj1's axes, so the marker centre is (210.0, 148.5) mm by
construction and marker_angle_deg is exactly 0.

Page 1  the working A3 sheet: the marker, plus verification marks confined
        to the outer 20 mm border so they sit outside the picking area.
Page 2  the same marker again, to cut out and glue to a 10 mm spacer if the
        marker has to sit level with the tops of the objects.

Needs reportlab (a tooling dependency, not a Pi runtime one):
    pip install reportlab

Run:  python tools/make_marker_sheet.py -o ../docs/marker_sheet_a3.pdf
"""

from __future__ import annotations

import argparse

import cv2
import numpy as np
from reportlab.lib.colors import Color, black
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

SHEET_W_MM = 420.0  # A3 long edge  -> wobj1 +X
SHEET_H_MM = 297.0  # A3 short edge -> wobj1 +Y
MARKER_MM = 100.0  # side of the OUTER BLACK SQUARE, which is what cv2 detects
DICTIONARY = cv2.aruco.DICT_5X5_100
MARKER_ID = 0
MODULES = 7  # 5 data bits + 1 border module on each side

CENTRE_X_MM = SHEET_W_MM / 2.0  # 210.0
CENTRE_Y_MM = SHEET_H_MM / 2.0  # 148.5

BORDER_MM = 20.0  # keep every extra mark outside this, i.e. config margin_mm
GREY = Color(0.45, 0.45, 0.45)


def marker_bits() -> np.ndarray:
    """The 7x7 module pattern: True where the module is black."""
    dictionary = cv2.aruco.getPredefinedDictionary(DICTIONARY)
    image = cv2.aruco.generateImageMarker(dictionary, MARKER_ID, MODULES, 1)
    return image < 128


def draw_marker(pdf: canvas.Canvas, centre_x_mm: float, centre_y_mm: float) -> None:
    """Draw the marker as vector squares so it prints at exact size."""
    bits = marker_bits()
    module = MARKER_MM / MODULES  # 14.285714... mm
    left = centre_x_mm - MARKER_MM / 2.0
    bottom = centre_y_mm - MARKER_MM / 2.0
    pdf.setFillColor(black)
    for row in range(MODULES):
        for col in range(MODULES):
            if not bits[row, col]:
                continue
            # row 0 is the TOP row of the marker image, so flip for PDF's y-up
            x = left + col * module
            y = bottom + (MODULES - 1 - row) * module
            # +0.02 mm overlap stops hairline white seams between modules
            pdf.rect((x - 0.01) * mm, (y - 0.01) * mm,
                     (module + 0.02) * mm, (module + 0.02) * mm,
                     stroke=0, fill=1)


def draw_verification(pdf: canvas.Canvas) -> None:
    """Marks that prove the print was not scaled or shifted.

    All of it lives in the outer 20 mm border, outside the picking area, so
    the detector never sees it.
    """
    pdf.setStrokeColor(GREY)
    pdf.setFillColor(GREY)
    pdf.setLineWidth(0.2 * mm)

    # crosses whose centres are exactly 10 mm in from each edge
    arm = 4.0
    for cx, cy in ((10.0, 10.0), (SHEET_W_MM - 10.0, 10.0),
                   (10.0, SHEET_H_MM - 10.0),
                   (SHEET_W_MM - 10.0, SHEET_H_MM - 10.0)):
        pdf.line((cx - arm) * mm, cy * mm, (cx + arm) * mm, cy * mm)
        pdf.line(cx * mm, (cy - arm) * mm, cx * mm, (cy + arm) * mm)

    # a 100 mm scale bar with end ticks, centred along the bottom border
    bar_y = 12.0
    x0 = CENTRE_X_MM - 50.0
    x1 = CENTRE_X_MM + 50.0
    pdf.line(x0 * mm, bar_y * mm, x1 * mm, bar_y * mm)
    for x in (x0, x1):
        pdf.line(x * mm, (bar_y - 2.5) * mm, x * mm, (bar_y + 2.5) * mm)
    pdf.setFont("Helvetica", 6)
    pdf.drawCentredString(CENTRE_X_MM * mm, (bar_y + 4.0) * mm,
                          "this bar must measure 100.0 mm - if it does not, "
                          "the print was scaled")

    pdf.setFont("Helvetica", 5)
    pdf.drawString(20.0 * mm, 5.0 * mm,
                   "A3 420 x 297 mm | ArUco DICT_5X5_100 id 0 | outer black "
                   "square 100.0 mm | centre 210.0, 148.5 mm from the "
                   "bottom-left corner | corner crosses 10.0 mm in from "
                   "each edge")


def draw_cutout_page(pdf: canvas.Canvas) -> None:
    """The marker again, with a cut line, for mounting on a 10 mm spacer."""
    draw_marker(pdf, CENTRE_X_MM, CENTRE_Y_MM)

    pdf.setStrokeColor(GREY)
    pdf.setFillColor(GREY)
    pdf.setLineWidth(0.2 * mm)
    pdf.setDash(3, 3)
    half = MARKER_MM / 2.0 + 20.0  # cut 20 mm clear of the black square
    pdf.rect((CENTRE_X_MM - half) * mm, (CENTRE_Y_MM - half) * mm,
             2 * half * mm, 2 * half * mm, stroke=1, fill=0)
    pdf.setDash()

    pdf.setFont("Helvetica", 8)
    lines = (
        "SPARE / SPACER COPY - only needed if the marker must sit level with "
        "the tops of the objects.",
        "Cut on the dashed line and glue to a 10 mm spacer, then set the "
        "spacer down on the marker printed on page 1",
        "so its black square covers that one exactly. The centre stays "
        "210.0, 148.5 mm and nothing needs measuring.",
        "The 20 mm white margin around the black square is the quiet zone - "
        "do not trim inside it.",
    )
    y = CENTRE_Y_MM - half - 12.0
    for line in lines:
        pdf.drawCentredString(CENTRE_X_MM * mm, y * mm, line)
        y -= 5.0


def build(path: str) -> None:
    pdf = canvas.Canvas(path, pagesize=(SHEET_W_MM * mm, SHEET_H_MM * mm))
    pdf.setTitle("INA700 A3 sheet - 100 mm ArUco DICT_5X5_100 id 0 at centre")

    draw_marker(pdf, CENTRE_X_MM, CENTRE_Y_MM)
    draw_verification(pdf)
    pdf.showPage()

    draw_cutout_page(pdf)
    pdf.showPage()

    pdf.save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", default="marker_sheet_a3.pdf")
    args = parser.parse_args()
    build(args.output)
    print(f"wrote {args.output}")
    print(f"marker centre {CENTRE_X_MM} , {CENTRE_Y_MM} mm from the sheet corner")


if __name__ == "__main__":
    main()
