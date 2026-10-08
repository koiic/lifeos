"""T13: scripts/build_icons.py draws the app icons of spec 11.2 from the design tokens (plan 5.1:
no design value outside tokens.json), deterministically, with a --check mode like build_tokens."""

import importlib.util
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "build_icons.py"
ICONS = ROOT / "web" / "public" / "icons"
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text())

# Spec 11.2: the manifest icons and the apple-touch-icon in index.html.
EXPECTED = {
    "icon-192.png": 192,
    "icon-512.png": 512,
    "icon-maskable-512.png": 512,
    "apple-touch-icon-180.png": 180,
}


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_icons", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decode(png: bytes) -> tuple[int, int, list[list[tuple[int, int, int, int]]]]:
    """A minimal PNG reader for the RGBA, non-interlaced files the script writes."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pos, data, width, height = 8, b"", 0, 0
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos : pos + 4])
        kind = png[pos + 4 : pos + 8]
        body = png[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour = struct.unpack(">IIBB", body[:10])
            assert (depth, colour) == (8, 6)  # 8-bit RGBA
        elif kind == b"IDAT":
            data += body
        pos += 12 + length
    raw = zlib.decompress(data)
    rows, stride = [], width * 4
    for y in range(height):
        start = y * (stride + 1)
        assert raw[start] == 0  # filter type None
        line = raw[start + 1 : start + 1 + stride]
        rows.append([tuple(line[x * 4 : x * 4 + 4]) for x in range(width)])  # type: ignore[misc]
    return width, height, rows


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def test_the_four_icons_exist_at_their_sizes() -> None:
    for name, size in EXPECTED.items():
        width, height, _rows = decode((ICONS / name).read_bytes())
        assert (width, height) == (size, size), name


def test_colours_come_from_the_sorbet_tokens() -> None:
    """The background is Sorbet `--bg` (the manifest's background_color), the ring `--accent`
    and the dot `--sun`."""
    light = TOKENS["themes"]["light"]["color"]
    bg = hex_rgb(light["bg"])
    _w, _h, rows = decode((ICONS / "icon-512.png").read_bytes())
    assert rows[4][4][:3] == bg
    assert rows[4][4][3] == 255
    # The ring at its left edge's middle (radius 0.25 of 512 = 128 px left of centre) and the dot
    # (radius 0.25 at -45°: about 90 px right of and 90 px above the centre).
    assert rows[256][256 - 128][:3] == hex_rgb(light["accent"])
    assert rows[256 - 91][256 + 91][:3] == hex_rgb(light["sun"])
    assert rows[256][256][:3] == bg  # the ring's middle is open


def test_the_maskable_icon_keeps_its_mark_inside_the_safe_zone() -> None:
    """Maskable icons may be cropped to a circle of 80 % of the size: everything outside it is
    plain background."""
    bg = hex_rgb(TOKENS["themes"]["light"]["color"]["bg"])
    _w, _h, rows = decode((ICONS / "icon-maskable-512.png").read_bytes())
    radius = 0.4 * 512
    for y in range(0, 512, 4):
        for x in range(0, 512, 4):
            if (x + 0.5 - 256) ** 2 + (y + 0.5 - 256) ** 2 > radius**2:
                assert rows[y][x][:3] == bg, (x, y)


def test_rendering_is_deterministic_and_the_committed_files_are_current() -> None:
    rendered = load().render_all(TOKENS)
    assert set(rendered) == set(EXPECTED)
    for name, data in rendered.items():
        assert (ICONS / name).read_bytes() == data, name


def test_check_exits_0_on_current_files() -> None:
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, check=False
    )
    assert run.returncode == 0, run.stderr
