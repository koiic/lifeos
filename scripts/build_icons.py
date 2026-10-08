#!/usr/bin/env python3
"""Draw the app icons of spec 11.2 from the design tokens (plan 5.1: no design value elsewhere).

  python3 scripts/build_icons.py          # write web/public/icons/*.png
  python3 scripts/build_icons.py --check  # exit 1 if the committed icons are stale

The mark is the cycle ring: an `--accent` ring with a `--sun` dot (today) on the Sorbet `--bg`,
the manifest's background colour. It sits inside the maskable safe zone (a centred circle of
80 % of the size) on every icon, so one drawing serves all four. Pure Python (zlib only): the
output is byte-for-byte deterministic. A placeholder until Zee picks the app's name (spec 18).
"""

import argparse
import json
import math
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "design" / "tokens.json"
OUT = ROOT / "web" / "public" / "icons"
SIZES = {
    "icon-192.png": 192,
    "icon-512.png": 512,
    "icon-maskable-512.png": 512,
    "apple-touch-icon-180.png": 180,
}
SUPERSAMPLE = 4  # samples per pixel per axis, for smooth edges

# Geometry as fractions of the icon size (all within the 0.4 safe-zone radius).
RING_RADIUS = 0.25
RING_WIDTH = 0.075
DOT_RADIUS = 0.07
DOT_ANGLE = -math.pi / 4  # upper right on the ring

RGB = tuple[int, int, int]


def hex_rgb(value: str) -> RGB:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def colour_at(x: float, y: float, size: int, bg: RGB, ring: RGB, dot: RGB) -> RGB:
    """The colour of the point (x, y) in pixel units."""
    cx = cy = size / 2
    dx, dy = x - cx, y - cy
    dot_x = cx + RING_RADIUS * size * math.cos(DOT_ANGLE)
    dot_y = cy + RING_RADIUS * size * math.sin(DOT_ANGLE)
    if (x - dot_x) ** 2 + (y - dot_y) ** 2 <= (DOT_RADIUS * size) ** 2:
        return dot
    distance = math.hypot(dx, dy)
    if abs(distance - RING_RADIUS * size) <= RING_WIDTH * size / 2:
        return ring
    return bg


def render(size: int, bg: RGB, ring: RGB, dot: RGB) -> bytes:
    rows = bytearray()
    step = 1 / SUPERSAMPLE
    samples = SUPERSAMPLE * SUPERSAMPLE
    for py in range(size):
        rows.append(0)  # filter: none
        for px in range(size):
            totals = [0, 0, 0]
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    c = colour_at(
                        px + (sx + 0.5) * step,
                        py + (sy + 0.5) * step,
                        size,
                        bg,
                        ring,
                        dot,
                    )
                    totals[0] += c[0]
                    totals[1] += c[1]
                    totals[2] += c[2]
            rows.extend(round(t / samples) for t in totals)
            rows.append(255)
    return png(size, size, bytes(rows))


def png(width: int, height: int, raw: bytes) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def render_all(tokens: dict) -> dict[str, bytes]:  # type: ignore[type-arg]
    light = tokens["themes"]["light"]["color"]
    bg, ring, dot = (
        hex_rgb(light["bg"]),
        hex_rgb(light["accent"]),
        hex_rgb(light["sun"]),
    )
    cache: dict[int, bytes] = {}
    out = {}
    for name, size in SIZES.items():
        if size not in cache:
            cache[size] = render(size, bg, ring, dot)
        out[name] = cache[size]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="fail if the icons are stale"
    )
    args = parser.parse_args()
    icons = render_all(json.loads(TOKENS.read_text()))
    if args.check:
        stale = [
            n
            for n, d in icons.items()
            if not (OUT / n).is_file() or (OUT / n).read_bytes() != d
        ]
        for name in stale:
            print(
                f"STALE: web/public/icons/{name} (run: python3 scripts/build_icons.py)",
                file=sys.stderr,
            )
        if stale:
            return 1
        print("icons: current")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in icons.items():
        (OUT / name).write_bytes(data)
    print(f"wrote {len(icons)} icons to web/public/icons")
    return 0


if __name__ == "__main__":
    sys.exit(main())
