"""Raster versions of streamhub/static/brand/logo-mark.svg: PNG favicon, Apple touch icon and favicon.ico.

Run after changing the mark: `python deploy/brand/make_icons.py` (needs Pillow). Writes into
streamhub/static/brand/ (favicon.ico into streamhub/static/), or into the folder given as the first argument.

Same geometry as the SVG (64-unit grid), drawn at 1024 px and downscaled for smooth edges. Each stream (line
plus its source dot) is drawn opaque on its own layer, then given its opacity, like an SVG <g opacity>.
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "streamhub" / "static" / "brand"
SIZE = 1024
S = SIZE / 64  # SVG units -> pixels
A, B = (0x63, 0x66, 0xF1), (0x06, 0xB6, 0xD4)
W = 3.2  # stroke width


def gradient():
    img = Image.new("RGBA", (SIZE, SIZE))
    px = img.load()
    for y in range(SIZE):
        for x in range(SIZE):
            t = (x + y) / (2 * (SIZE - 1))
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(A, B)) + (255,)
    return img


def cubic(p0, p1, p2, p3, steps=400):
    for i in range(steps + 1):
        t = i / steps
        yield tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
                    for a, b, c, d in zip(p0, p1, p2, p3))


def line(p0, p1, steps=400):
    for i in range(steps + 1):
        t = i / steps
        yield (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)


def disc(draw, cx, cy, r):
    draw.ellipse(((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S), fill=255)


def stream(path, dot=None, alpha=1.0):
    """An opaque white stroke (round caps, stamped for smooth curves) and dot, at `alpha` as a whole."""
    mask = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(mask)
    for x, y in path:
        disc(draw, x, y, W / 2)
    if dot:
        disc(draw, *dot)
    layer = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    layer.putalpha(mask.point(lambda v: round(v * alpha)))
    return layer


def mark(rounded=True):
    base = gradient()
    if rounded:
        shape = Image.new("L", (SIZE, SIZE), 0)
        ImageDraw.Draw(shape).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=round(16 * S), fill=255)
        base.putalpha(shape)
    layers = [
        stream(cubic((14, 18), (24, 18), (24, 32), (32, 32)), (14, 18, 3.4), .78),
        stream(line((14, 32), (32, 32)), (14, 32, 3.4), .9),
        stream(cubic((14, 46), (24, 46), (24, 32), (32, 32)), (14, 46, 3.4), .78),
        stream(line((32, 32), (44, 32)), (32, 32, 6.5)),
    ]
    ring = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(ring)
    disc(draw, 50, 32, 4.6 + W / 2)
    hole = Image.new("L", (SIZE, SIZE), 0)
    disc(ImageDraw.Draw(hole), 50, 32, 4.6 - W / 2)
    ring_layer = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    ring_layer.putalpha(ImageChops.subtract(ring, hole))
    for layer in layers + [ring_layer]:
        base = Image.alpha_composite(base, layer)
    if rounded:  # keep the rounded corners transparent
        base.putalpha(ImageChops.multiply(base.getchannel("A"), shape))
    return base


icon = mark()
icon.resize((32, 32), Image.LANCZOS).save(OUT / "favicon-32.png")
icon.resize((192, 192), Image.LANCZOS).save(OUT / "icon-192.png")
# /favicon.ico: Tornado serves it from the root of static_path
icon.resize((256, 256), Image.LANCZOS).save(OUT.parent / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
mark(rounded=False).resize((180, 180), Image.LANCZOS).save(OUT / "apple-touch-icon.png")  # iOS rounds it
if len(sys.argv) > 2:
    icon.resize((512, 512), Image.LANCZOS).save(sys.argv[2])
print("written to", OUT)
