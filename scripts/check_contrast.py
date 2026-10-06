#!/usr/bin/env python3
"""Check every contrast pair in design/tokens.json for both themes (WCAG 2.x ratio).

Exit 1 if any pair is below its minimum. Plan section 5.1; spec 5.3, NFR-4. Stdlib only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "design" / "tokens.json"


def _channel(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected #RRGGBB, got {hex_color}")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def ratio(fg: str, bg: str) -> float:
    a, b = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def main() -> int:
    tokens = json.loads(SRC.read_text())
    failures = 0
    for theme_key, theme in tokens["themes"].items():
        colors = theme["color"]
        for pair in tokens["contrast_pairs"]:
            r = ratio(colors[pair["fg"]], colors[pair["bg"]])
            ok = r >= pair["min"]
            failures += not ok
            mark = "ok  " if ok else "FAIL"
            print(f"{mark} {theme['name']:<13} {pair['fg']:>13} on {pair['bg']:<13} {r:5.2f} (min {pair['min']}) - {pair['use']}")
    if failures:
        print(f"\n{failures} contrast pair(s) below minimum", file=sys.stderr)
        return 1
    print("\ncontrast: all pairs pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
