"""Generate the report figure explaining the harmonic orientation method.

Panels (a) and (b) and the recovered angle in the footer are computed by the
same arithmetic as domain/orientation.py, so the picture cannot quietly drift
away from the code - if the method broke, the figure's own self-check would
say so. Panels (c) and (d) show the five tip directions as representative
vectors rather than all 180 bins: the same sum, drawn with five terms instead
of a hundred and eighty, because that is what makes it explainable.

Run:  python tools/make_orientation_figure.py -o ../docs/orientation_method.svg
"""

from __future__ import annotations

import argparse
import math
from typing import List, Tuple

ORDER = 5  # a five-pointed star
TRUE_ANGLE_DEG = 18.0  # the star is drawn deliberately off-axis
INNER = 0.45

W, H = 1140, 880
INK = "#1c2024"
MUTED = "#6b7280"
FAINT = "#d4d8dd"
ACCENT = "#1f6feb"
WARM = "#c2410c"
FONT = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
        "'Helvetica Neue', Arial, sans-serif")


# --- the actual maths ------------------------------------------------------

def star_outline(angle_deg: float, radius: float) -> List[Tuple[float, float]]:
    a = math.radians(angle_deg)
    pts = []
    for k in range(2 * ORDER):
        r = radius if k % 2 == 0 else radius * INNER
        t = a + k * math.pi / ORDER
        pts.append((r * math.cos(t), r * math.sin(t)))
    return pts


def radial_profile(angle_deg: float, radius: float, bins: int = 360) -> List[float]:
    """Distance from the centre to the outline, in every direction."""
    outline = star_outline(angle_deg, radius)
    out = []
    for i in range(bins):
        theta = 2.0 * math.pi * i / bins
        dx, dy = math.cos(theta), math.sin(theta)
        best = 0.0
        for j in range(len(outline)):
            x1, y1 = outline[j]
            x2, y2 = outline[(j + 1) % len(outline)]
            # ray from origin against segment (x1,y1)-(x2,y2)
            ex, ey = x2 - x1, y2 - y1
            den = dx * ey - dy * ex
            if abs(den) < 1e-12:
                continue
            t = (x1 * ey - y1 * ex) / den
            if t <= 0:
                continue
            # t*d - u*E = A, crossed with d, gives u = -(A x d) / (E x d)
            u = -(x1 * dy - y1 * dx) / (ex * dy - ey * dx)
            if -1e-9 <= u <= 1 + 1e-9:
                best = max(best, t)
        out.append(best)
    return out


def harmonic(profile: List[float]) -> Tuple[float, float]:
    """Orientation in degrees and confidence, exactly as domain/orientation.py."""
    n = len(profile)
    step = 2.0 * math.pi / n
    re = sum(r * math.cos(ORDER * i * step) for i, r in enumerate(profile))
    im = sum(r * math.sin(ORDER * i * step) for i, r in enumerate(profile))
    return math.degrees(math.atan2(im, re) / ORDER), math.hypot(re, im) / sum(profile)


# --- svg helpers -----------------------------------------------------------

def poly(points, **kw) -> str:
    pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())
    return f'<polygon points="{pts}" {attrs}/>'


def line(x1, y1, x2, y2, **kw) -> str:
    attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())
    return f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" {attrs}/>'


def text(x, y, s, size=14, fill=INK, anchor="start", weight="400", style="normal") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" '
            f'font-style="{style}">{s}</text>')


def arrow(x0, y0, x1, y1, colour, width=2.4, head=9.0) -> str:
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return ""
    ux, uy = dx / length, dy / length
    bx, by = x1 - ux * head, y1 - uy * head
    px, py = -uy, ux
    tip = [(x1, y1), (bx + px * head * 0.45, by + py * head * 0.45),
           (bx - px * head * 0.45, by - py * head * 0.45)]
    return (line(x0, y0, bx, by, stroke=colour, stroke_width=width,
                 stroke_linecap="round")
            + poly(tip, fill=colour))


def panel(x, y, w, h, tag, title) -> str:
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" '
            f'fill="#ffffff" stroke="{FAINT}" stroke-width="1"/>'
            + text(x + 18, y + 30, tag, 15, ACCENT, weight="700")
            + text(x + 44, y + 30, title, 15, INK, weight="600"))


# --- the four panels -------------------------------------------------------

def panel_a(x, y, w, h) -> str:
    cx, cy, R = x + w / 2, y + h / 2 + 18, 118.0
    out = [panel(x, y, w, h, "a", "Measure the outline in every direction")]
    pts = [(cx + px, cy - py) for px, py in star_outline(TRUE_ANGLE_DEG, R)]
    out.append(poly(pts, fill="#eef4ff", stroke=ACCENT, stroke_width=2,
                    stroke_linejoin="round"))

    fan = radial_profile(TRUE_ANGLE_DEG, R, 72)
    for i, r in enumerate(fan):  # a fan of sample rays
        t = 2 * math.pi * i / 72
        out.append(line(cx, cy, cx + r * math.cos(t), cy - r * math.sin(t),
                        stroke=MUTED, stroke_width=0.5, opacity="0.45"))

    for k in range(ORDER):  # the five tips
        t = math.radians(TRUE_ANGLE_DEG) + k * 2 * math.pi / ORDER
        out.append(arrow(cx, cy, cx + R * math.cos(t), cy - R * math.sin(t),
                         WARM, 2.2, 8))
    out.append(f'<circle cx="{cx}" cy="{cy}" r="3.5" fill="{INK}"/>')
    out.append(text(x + 18, y + h - 44,
                    "Five tips, each 72° from the next. Every one is an",
                    13, MUTED))
    out.append(text(x + 18, y + h - 26,
                    "equally correct answer to “which way is it turned?”",
                    13, MUTED))
    return "".join(out)


def panel_b(x, y, w, h) -> str:
    out = [panel(x, y, w, h, "b", "That gives a wave with five peaks per turn")]
    profile = radial_profile(TRUE_ANGLE_DEG, 1.0, 360)
    px0, px1 = x + 62, x + w - 30
    py0, py1 = y + h - 104, y + 62
    lo, hi = min(profile), max(profile)

    for frac, lab in ((0.0, "0°"), (0.25, "90°"), (0.5, "180°"),
                      (0.75, "270°"), (1.0, "360°")):
        gx = px0 + (px1 - px0) * frac
        out.append(line(gx, py0, gx, py1, stroke=FAINT, stroke_width=1))
        out.append(text(gx, py0 + 19, lab, 12, MUTED, anchor="middle"))
    out.append(line(px0, py0, px1, py0, stroke=MUTED, stroke_width=1.2))
    out.append(text(x + 20, (py0 + py1) / 2, "r", 14, MUTED, style="italic"))

    pts = []
    for i, r in enumerate(profile):
        gx = px0 + (px1 - px0) * i / (len(profile) - 1)
        gy = py0 - (py0 - py1) * (r - lo) / (hi - lo)
        pts.append(f"{gx:.2f},{gy:.2f}")
    out.append(f'<polyline points="{" ".join(pts)}" fill="none" '
               f'stroke="{ACCENT}" stroke-width="2.2" stroke-linejoin="round"/>')

    for k in range(ORDER):
        deg = (TRUE_ANGLE_DEG + k * 72.0) % 360.0
        gx = px0 + (px1 - px0) * deg / 360.0
        out.append(line(gx, py1 - 6, gx, py0, stroke=WARM, stroke_width=1.2,
                        stroke_dasharray="3 3"))
        out.append(f'<circle cx="{gx:.2f}" cy="{py1 - 6:.2f}" r="3.5" fill="{WARM}"/>')

    out.append(text(x + 18, y + h - 44,
                    "The peaks are the tips. Five per revolution, so the shape",
                    13, MUTED))
    out.append(text(x + 18, y + h - 26,
                    "repeats every 72° — this is the N = 5 in the formula.",
                    13, MUTED))
    return "".join(out)


def _vector_panel(x, y, w, h, tag, title, multiply, caption1, caption2) -> str:
    cx, cy, R = x + w / 2, y + h / 2 + 10, 92.0
    out = [panel(x, y, w, h, tag, title)]
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" '
               f'stroke="{FAINT}" stroke-width="1" stroke-dasharray="4 4"/>')

    sx = sy = 0.0
    for k in range(ORDER):
        deg = TRUE_ANGLE_DEG + k * 72.0
        t = math.radians(deg * (ORDER if multiply else 1))
        arm = R * 0.52
        ex, ey = arm * math.cos(t), arm * math.sin(t)
        sx += ex
        sy += ey
        jitter = (k - 2) * (4.0 if multiply else 0.0)  # fan the coincident ones
        out.append(arrow(cx + jitter, cy, cx + ex + jitter, cy - ey, WARM, 2.0, 8))

    out.append(f'<circle cx="{cx}" cy="{cy}" r="3.5" fill="{INK}"/>')
    total = math.hypot(sx, sy)
    if total > 6:
        scale = min(1.0, (R + 14) / total)
        out.append(arrow(cx, cy, cx + sx * scale, cy - sy * scale, ACCENT, 4.0, 13))
    else:
        out.append(f'<circle cx="{cx}" cy="{cy}" r="10" fill="#ffffff" '
                   f'stroke="{ACCENT}" stroke-width="3"/>')
        out.append(f'<rect x="{cx + 18}" y="{cy - 12}" width="74" height="24" '
                   f'rx="6" fill="#ffffff" opacity="0.92"/>')
        out.append(text(cx + 24, cy + 5, "sum = 0", 13, ACCENT, weight="700"))

    if multiply:
        out.append(text(cx + 26, cy - R - 4,
                        f"sum points at 5 × {TRUE_ANGLE_DEG:.0f}° = "
                        f"{ORDER * TRUE_ANGLE_DEG:.0f}°", 13, ACCENT, weight="600"))
        out.append(text(cx + 26, cy - R + 16,
                        f"÷ 5  →  {TRUE_ANGLE_DEG:.0f}°", 13, INK, weight="700"))
    out.append(text(x + 18, y + h - 44, caption1, 13, MUTED))
    out.append(text(x + 18, y + h - 26, caption2, 13, MUTED))
    return "".join(out)


def build() -> str:
    profile = radial_profile(TRUE_ANGLE_DEG, 1.0, 360)
    angle, conf = harmonic(profile)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}">',
             f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
             text(40, 44, "Measuring the orientation of a symmetric shape", 22,
                  INK, weight="700"),
             text(40, 70,
                  "Five answers that all disagree by 72°, turned into one answer "
                  "— by counting five times faster.", 14, MUTED)]

    parts.append(panel_a(40, 96, 520, 350))
    parts.append(panel_b(580, 96, 520, 350))
    parts.append(_vector_panel(
        40, 470, 520, 320, "c", "Averaging them directly fails",
        False,
        "Draw each tip as an arrow and add them up. Five arrows",
        "72° apart cancel exactly: the average is nothing at all."))
    parts.append(_vector_panel(
        580, 470, 520, 320, "d", "Multiply every angle by five first",
        True,
        "×5 turns 72° gaps into 360° gaps — the arrows land on top of "
        "each other.",
        "Now the sum is long and its direction, divided by five, is the answer."))

    parts.append(text(40, H - 52, "Z = Σ rₖ · exp(i · N · θₖ)", 15, INK,
                      weight="700"))
    parts.append(text(268, H - 52, "so", 14, MUTED))
    parts.append(text(300, H - 52, "orientation = arg(Z) / N", 15, INK,
                      weight="700"))
    parts.append(text(40, H - 26,
                      f"|Z| is the confidence, free of charge: {conf:.2f} for "
                      f"this star, and ≈ 0 for a circle, which has no peaks to "
                      f"stack — which is where the weak-angle warning comes from.",
                      13, MUTED))
    parts.append(text(W - 40, H - 52,
                      f"figure generated from the estimator itself: "
                      f"recovered {angle:.2f}° from a true {TRUE_ANGLE_DEG:.2f}°",
                      12, MUTED, anchor="end"))
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default="orientation_method.svg")
    args = ap.parse_args()
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(build())
    profile = radial_profile(TRUE_ANGLE_DEG, 1.0, 360)
    angle, conf = harmonic(profile)
    print(f"wrote {args.output}")
    print(f"check: recovered {angle:.3f} deg against a true {TRUE_ANGLE_DEG} deg, "
          f"confidence {conf:.3f}")


if __name__ == "__main__":
    main()
