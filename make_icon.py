#!/usr/bin/env python3
# Eclipse Social Core MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Generate icon-512.png — brand system §6: eclipse motif on the navy

"""Generate icon-512.png — brand system §6: eclipse motif on the navy
field (#0d1b2a), one per-product glyph. The Core's glyph is the hub:
one canonical node at the eclipse ring, spokes out to adapter nodes —
one package, many native surfaces. PIL only; deterministic."""
from PIL import Image, ImageDraw

S = 512
NAVY = (13, 27, 42, 255)
STOPS = [(15, 246, 247), (0, 212, 255), (123, 44, 191)]  # cyan->blue->purple


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)


def grad(t):
    return lerp(STOPS[0], STOPS[1], t * 2) if t < 0.5 else \
        lerp(STOPS[1], STOPS[2], (t - 0.5) * 2)


def main():
    img = Image.new("RGBA", (S, S), NAVY)
    d = ImageDraw.Draw(img)
    # Eclipse ring around the hub, upper-left of center.
    box = [86, 86, 286, 286]
    for i in range(72):
        t = i / 72
        d.arc(box, start=i * 5, end=i * 5 + 6, fill=grad(t), width=14)
    d.ellipse([132, 132, 240, 240], fill=NAVY)  # occluding body
    hub = (186, 186)
    d.ellipse([hub[0] - 17, hub[1] - 17, hub[0] + 17, hub[1] + 17],
              fill=grad(0.1))
    # Spokes to adapter nodes.
    nodes = [(392, 128), (424, 256), (392, 384), (268, 424), (140, 400)]
    for j, (x, y) in enumerate(nodes):
        t = 0.25 + j * 0.15
        d.line([hub, (x, y)], fill=grad(t), width=7)
        r = 15
        d.ellipse([x - r, y - r, x + r, y + r], outline=grad(t), width=6)
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=grad(t))
    img.save("icon-512.png")
    print("wrote icon-512.png", img.size, img.mode)


if __name__ == "__main__":
    main()

# Eclipse Social Core MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
