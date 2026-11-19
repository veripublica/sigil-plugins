#!/usr/bin/env python3
# kepubverto for Sigil — the plugin icon, and the one place its geometry lives
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Write the Sigil plugin's icon: a **k** on the family's Sigil sheet.

    python3 kepubverto/icon.py

It writes two files, which must be the same drawing:

    kepubverto/plugin.svg        Sigil prefers the SVG
    kepubverto/plugin.png        and falls back to the PNG

**The container says which program, the glyph says which tool.** The sheet,
its ink outline and its turned corner are epubveri for Sigil's, unchanged
(`epubveri/icon.py`): the outline is there because Sigil can have any theme
colours, and the pair of yellow and ink is legible on all of them (DiapDealer,
MobileRead 374939 #22). The glyph is kepubverto for calibre's k
(`make_icon.py` in calibre-plugins), which at 16 and 24 px was the only one of
three variants still legible. The k is knocked out of the sheet in ink, where
epubveri's tick sits.

**The k is KF Libron Bold's**, by Nico Verbruggen, from
https://github.com/nicoverbruggen/libron (SIL Open Font License 1.1; "Libron
(c) 2026 Nico Verbruggen, with Reserved Font Name Libron"). Only the outline
of one glyph is kept below as data; no font is shipped or derived.

stdlib only and deterministic: the same script writes the same bytes, and a
test holds the shipped files to it.
"""

import math
import os
import struct
import sys
import zlib

#: This file sits in the plugin folder it draws for.
SIGIL = os.path.dirname(os.path.abspath(__file__))

#: Everything is described on a 64 grid, which is the SVG's viewBox. The mark
#: fills 44x60 of it: as tall as a full-bleed tile would be, so it does not
#: read small beside one, and narrow enough to still be a page.
GRID = 64.0

PAGE = (0xf5, 0xc5, 0x18)     #: the sheet body
INK = (0x11, 0x11, 0x11)      #: every outline, and the glyph knocked out of it
FOLD = (0xc9, 0x93, 0x0c)     #: the turned-back corner, a shade down
GLYPH = INK                   #: the k, knocked out of the body

#: How far the ink runs outside each sheet. It is what makes the silhouette
#: survive a light ground, so it may not go below about 2.5: at 16 px this is
#: already only 0.65 px and antialiasing is carrying it.
OUTLINE = 2.6

RECT = (10.0, 2.0, 54.0, 62.0)                        #: x0, y0, x1, y1
RADIUS = 4.0
#: The page keeps `x - y - CUT <= 0`, which removes the corner above the
#: diagonal from (41, 2) to (54, 15). The fold triangle is then drawn *inside*
#: the page, below the same diagonal — cut plus tint is what reads as a fold.
CUT = 39.0
FOLD_TRI = [(41.0, 2.0), (54.0, 15.0), (41.0, 15.0)]
#: Where the k sits on the sheet and how tall it is, in the sheet's own
#: units: centred in the body below the turned corner, and as tall as
#: calibre's, so the strokes stay above about 1 px at 16 px.
K_CENTRE = (31.0, 36.0)
K_HEIGHT = 30.0

#: KF Libron Bold, glyph "k": one TrueType contour in font units (2000 per
#: em, y up), as `(x, y, on_curve)`. Off-curve points are quadratic controls.
K_BBOX = (3, 0, 1355, 1591)
K_POINTS = [
    (504, 141, 1), (634, 98, 1), (634, 0, 1), (51, 0, 1), (51, 98, 1),
    (187, 141, 1), (187, 1283, 1), (175, 1294, 0), (117, 1331, 0),
    (41, 1374, 0), (3, 1395, 1), (3, 1493, 1), (455, 1591, 1),
    (524, 1591, 1), (504, 1328, 1), (504, 684, 1), (657, 684, 1),
    (911, 940, 1), (769, 977, 1), (769, 1071, 1), (1280, 1071, 1),
    (1280, 977, 1), (1132, 939, 1), (870, 695, 1), (1241, 147, 1),
    (1355, 91, 1), (1355, 0, 1), (984, 0, 1), (639, 500, 1), (504, 500, 1),
]


def _flatten(points, steps=8):
    """The contour as a polygon: quadratic segments cut into `steps` lines,
    with the on-curve point TrueType implies between two off-curve ones."""
    full = []
    n = len(points)
    for i in range(n):
        p, q = points[i], points[(i + 1) % n]
        full.append(p)
        if not p[2] and not q[2]:
            full.append(((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0, 1))
    while not full[0][2]:
        full = full[1:] + full[:1]
    out = []
    n = len(full)
    i = 0
    while i < n:
        p, q = full[i], full[(i + 1) % n]
        if q[2]:
            out.append((p[0], p[1]))
            i += 1
            continue
        r = full[(i + 2) % n]
        for s in range(steps):
            t = s / float(steps)
            out.append(((1 - t) ** 2 * p[0] + 2 * (1 - t) * t * q[0] + t * t * r[0],
                        (1 - t) ** 2 * p[1] + 2 * (1 - t) * t * q[1] + t * t * r[1]))
        i += 2
    return out


def _k_polygon():
    """The k on the 64 grid (y down), centred on `K_CENTRE`."""
    x0, y0, x1, y1 = K_BBOX
    scale = K_HEIGHT / (y1 - y0)
    cx, cy = K_CENTRE
    return [(cx + (x - (x0 + x1) / 2.0) * scale,
             cy - (y - (y0 + y1) / 2.0) * scale)
            for x, y in _flatten(K_POINTS)]


K_POLYGON = _k_polygon()


def _in_k(x, y):
    """Non-zero winding, as TrueType fills."""
    winding = 0
    n = len(K_POLYGON)
    for i in range(n):
        ax, ay = K_POLYGON[i]
        bx, by = K_POLYGON[(i + 1) % n]
        if ay <= y < by or by <= y < ay:
            if ax + (y - ay) * (bx - ax) / (by - ay) > x:
                winding += 1 if by > ay else -1
    return winding != 0


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


_SVG_SCALE = 0.92
_SVG_ORIGIN = (2.6, 2.5)
_PAGE_PATH = ("M14 2h27l13 13v43a4 4 0 0 1-4 4H14a4 4 0 0 1-4-4V6a4 4 0 0 1 "
              "4-4z")
_K_PATH = "M" + " L".join("%.2f %.2f" % p for p in K_POLYGON) + "Z"


SVG = '''<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by icon.py — edit the geometry there, not this file. -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64"
     height="64" role="img" aria-label="kepubverto">
  <title>kepubverto</title>
  <g transform="translate(%(ox)s %(oy)s) scale(%(scale)s)">
    <path d="%(page)s" fill="none" stroke="%(ink)s" stroke-width="%(stroke).3f"
          stroke-linejoin="round"/>
    <path d="%(page)s" fill="%(body)s"/>
    <path d="M41 2l13 13H41z" fill="%(fold)s"/>
    <path d="%(k)s" fill="%(ink)s"/>
  </g>
</svg>
''' % {
    "ox": _SVG_ORIGIN[0], "oy": _SVG_ORIGIN[1], "scale": _SVG_SCALE,
    "page": _PAGE_PATH, "ink": _hex(INK), "body": _hex(PAGE),
    "fold": _hex(FOLD), "stroke": 2.0 * OUTLINE / _SVG_SCALE, "k": _K_PATH,
}


def _in_round_rect(x, y):
    x0, y0, x1, y1 = RECT
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2 - RADIUS, (y1 - y0) / 2 - RADIUS
    qx, qy = abs(x - cx) - hx, abs(y - cy) - hy
    if qx <= 0 or qy <= 0:
        return max(qx, qy) <= RADIUS
    return math.hypot(qx, qy) <= RADIUS


def _in_page(x, y):
    return _in_round_rect(x, y) and (x - y - CUT) <= 0


def _in_fold(x, y):
    def side(a, b):
        return (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])
    a, b, c = FOLD_TRI
    s = (side(a, b), side(b, c), side(c, a))
    return all(v >= 0 for v in s) or all(v <= 0 for v in s)


def _page(scale, origin, grow=0.0):
    """The sheet silhouette, optionally grown by `grow` grid units.

    Exact rather than approximate, which matters because the growth *is* the
    outline: a rounded rectangle dilated by r is the same rectangle inset by r
    with radius r larger, and a half-plane `x - y - CUT <= 0` dilated by r is
    the same half-plane with CUT moved out by r*sqrt(2). Sampling a distance
    field would round the corners differently from the body and the outline
    would thin where it is most visible.
    """
    x0, y0, x1, y1 = RECT
    r = grow / scale
    X0, Y0, X1, Y1 = x0 - r, y0 - r, x1 + r, y1 + r
    radius = RADIUS + r
    cut = CUT + r * math.sqrt(2)
    dx, dy = origin

    def at(x, y):
        u, v = (x - dx) / scale, (y - dy) / scale
        cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
        hx, hy = (X1 - X0) / 2 - radius, (Y1 - Y0) / 2 - radius
        qx, qy = abs(u - cx) - hx, abs(v - cy) - hy
        if qx <= 0 or qy <= 0:
            inside = max(qx, qy) <= radius
        else:
            inside = math.hypot(qx, qy) <= radius
        return inside and (u - v - cut) <= 0

    return at


def _sheet(scale, origin):
    """The outlined sheet with its corner and the k, as a
    `(x, y) -> colour or None` layer."""
    body = _page(scale, origin)
    outline = _page(scale, origin, OUTLINE)
    dx, dy = origin

    def at(x, y):
        if body(x, y):
            u, v = (x - dx) / scale, (y - dy) / scale
            if _in_k(u, v):
                return GLYPH
            if _in_fold(u, v):
                return FOLD
            return PAGE
        return INK if outline(x, y) else None

    return at


#: The same placement as the SVG's group transform.
MARK = [_sheet(_SVG_SCALE, _SVG_ORIGIN)]


def _pixels(mark, size, samples=6):
    """RGBA rows with a leading PNG filter byte, straight-alpha."""
    out = bytearray()
    step = GRID / size
    sub = step / samples
    total = float(samples * samples)
    for row in range(size):
        out.append(0)                                  # filter: none
        for col in range(size):
            r = g = b = hits = 0.0
            for sy in range(samples):
                y = row * step + (sy + 0.5) * sub
                for sx in range(samples):
                    x = col * step + (sx + 0.5) * sub
                    c = None
                    for layer in reversed(mark):
                        c = layer(x, y)
                        if c is not None:
                            break
                    if c is None:
                        continue
                    r += c[0]; g += c[1]; b += c[2]; hits += 1
            if hits:
                out += bytes((int(r / hits + .5), int(g / hits + .5),
                              int(b / hits + .5), int(255 * hits / total + .5)))
            else:
                out += b"\x00\x00\x00\x00"
    return bytes(out)


def write_png(path, size=128, mark=None):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    head = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    blob = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head)
            + chunk(b"IDAT", zlib.compress(_pixels(mark or MARK, size), 9))
            + chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(blob)
    return len(blob)


def main():
    svg = os.path.join(SIGIL, "plugin.svg")
    with open(svg, "w", encoding="utf-8") as handle:
        handle.write(SVG)
    print("%s  (%d bytes)" % (svg, len(SVG.encode("utf-8"))))
    png = os.path.join(SIGIL, "plugin.png")
    print("%s  (%d bytes)" % (png, write_png(png)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
