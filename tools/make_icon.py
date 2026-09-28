#!/usr/bin/env python3
"""Draw the app icon: a cat's head under a prohibition sign.

Not decoration. The icon is the one place the gnome states what it is for, and
"no cats here" said plainly is more honest than anything softer -- this is a
device that squirts water at an animal, and the person installing it should be
reminded of that every time they look at their home screen.

Drawn rather than drafted in SVG so it has no toolchain: Pillow is already
present for the model export.

    .venv-model/bin/python tools/make_icon.py
"""

from pathlib import Path
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
DESTINATION = REPO / "ios" / "DwarfApp" / "App" / "Assets.xcassets" / "AppIcon.appiconset"

SIDE = 1024
CREAM = (244, 240, 232)
CHARCOAL = (38, 38, 42)
RED = (206, 38, 38)

# iOS wants these; the 1024 is the one the App Store and Settings use.
SIZES = [40, 58, 60, 80, 87, 120, 180, 1024]


def draw() -> Image.Image:
    image = Image.new("RGB", (SIDE, SIDE), CREAM)
    d = ImageDraw.Draw(image)
    c = SIDE / 2

    # --- the cat, built from a head and two ears ---
    # Wider than tall: a round head reads as an owl, and the ears are what carry
    # the species at 40 px, so they are upright triangles standing on the skull
    # rather than horns coming out of its sides.
    head_w, head_h = 500, 420
    head = (c - head_w / 2, c - head_h / 2 + 70,
            c + head_w / 2, c + head_h / 2 + 70)
    d.ellipse(head, fill=CHARCOAL)

    for side in (-1, 1):
        inner_x = c + side * 55
        outer_x = c + side * 235
        d.polygon([
            (inner_x, c + 40),          # inner base, well inside the skull
            (outer_x, c + 30),          # outer base, well inside the skull
            (c + side * 195, c - 262),  # tip, up and slightly out
        ], fill=CHARCOAL)

    # Eyes: leaning ellipses rather than polygons. Drawn on their own layer and
    # rotated, because an almond built from straight edges reads as a diamond,
    # which was the other half of the owl problem.
    for side in (-1, 1):
        eye = Image.new("RGBA", (SIDE, SIDE), (0, 0, 0, 0))
        ImageDraw.Draw(eye).ellipse(
            (c - 33, c + 16, c + 33, c + 128), fill=CREAM + (255,))
        eye = eye.rotate(side * -26, resample=Image.BICUBIC, center=(c, c + 72))
        image.paste(eye, (int(side * 100), 0), eye)

    # A muzzle, so the lower half is not a blank disc.
    d.polygon([(c - 30, c + 152), (c + 30, c + 152), (c, c + 190)], fill=CREAM)

    # --- the prohibition sign, over the top ---
    ring = 78
    inset = 96
    d.ellipse((inset, inset, SIDE - inset, SIDE - inset), outline=RED, width=ring)

    # The bar, drawn corner to corner along the ring's own diameter so it meets
    # the circle cleanly rather than crossing it at a guess.
    from math import cos, sin, radians
    radius = (SIDE - 2 * inset) / 2 - ring / 2
    angle = radians(45)
    dx, dy = cos(angle) * radius, sin(angle) * radius
    d.line((c - dx, c + dy, c + dx, c - dy), fill=RED, width=ring)

    return image


def main() -> None:
    icon = draw()
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        icon.resize((size, size), Image.LANCZOS).save(DESTINATION / f"icon-{size}.png")
    print(f"wrote {len(SIZES)} icons to {DESTINATION}")


if __name__ == "__main__":
    main()
